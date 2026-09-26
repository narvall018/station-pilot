"""Stockage atomique de fichiers dans une branche GitHub.

Ce module utilise uniquement l'API REST GitHub et la bibliothèque standard.
Le jeton reste fourni par l'environnement d'exécution et n'est jamais écrit
dans le dépôt.
"""

from __future__ import annotations

import base64
import json
import time
from collections.abc import Mapping, Sequence
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen


class GitHubStorageError(RuntimeError):
    """Erreur lisible liée au stockage GitHub."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class GitHubStorageConflictError(GitHubStorageError):
    """La branche a changé pendant une sauvegarde."""


class GitHubStoragePublicRepoError(GitHubStorageError):
    """Le dépôt de données est public : les saisies seraient visibles de tous."""


class GitHubStorage:
    """Lit et valide plusieurs fichiers dans un unique commit GitHub."""

    api_root = "https://api.github.com"
    # Dépôts déjà vérifiés privés, partagés par toutes les sessions du processus.
    _verified_private_repos: set[str] = set()
    # Dernier commit connu de chaque branche : (commit, arbre ou None, instant
    # de la dernière confirmation), partagé par toutes les sessions du processus.
    _known_heads: dict[str, tuple[str, str | None, float]] = {}

    def __init__(
        self,
        *,
        token: str,
        owner: str,
        repo: str,
        branch: str = "data",
        source_branch: str = "main",
        timeout: int = 20,
    ) -> None:
        if not token.strip():
            raise ValueError("Un jeton GitHub est requis.")
        self.token = token.strip()
        self.owner = owner.strip()
        self.repo = repo.strip()
        self.branch = branch.strip()
        self.source_branch = source_branch.strip()
        self.timeout = timeout
        self.repo_path = f"/repos/{quote(self.owner)}/{quote(self.repo)}"

    def _request(
        self,
        method: str,
        path: str,
        payload: Mapping[str, Any] | None = None,
        *,
        allow_not_found: bool = False,
    ) -> Any:
        body = None if payload is None else json.dumps(payload).encode("utf-8")
        request = Request(
            f"{self.api_root}{path}",
            data=body,
            method=method,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {self.token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "station-pilot-streamlit",
                "Content-Type": "application/json",
            },
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                raw = response.read()
        except HTTPError as exc:
            if allow_not_found and exc.code == 404:
                return None
            raw_error = exc.read().decode("utf-8", errors="replace")
            try:
                details = json.loads(raw_error).get("message", raw_error)
            except json.JSONDecodeError:
                details = raw_error
            raise GitHubStorageError(
                f"GitHub a refusé l'opération ({exc.code}) : {details}",
                status=exc.code,
            ) from exc
        except URLError as exc:
            raise GitHubStorageError(
                "Connexion à GitHub impossible. Vérifiez le réseau puis réessayez."
            ) from exc

        if not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubStorageError("Réponse GitHub illisible.") from exc

    def _read_ref(self, branch: str) -> dict[str, Any] | None:
        encoded_branch = quote(branch, safe="/")
        return self._request(
            "GET",
            f"{self.repo_path}/git/ref/heads/{encoded_branch}",
            allow_not_found=True,
        )

    def ensure_private(self) -> None:
        """Refuse de lire ou d'écrire des données métier dans un dépôt public."""
        if self.repo_path in self._verified_private_repos:
            return
        repository = self._request("GET", self.repo_path, allow_not_found=True)
        if repository is None:
            raise GitHubStorageError(
                f"Dépôt « {self.owner}/{self.repo} » introuvable, ou le token n'y a "
                "pas accès."
            )
        if not repository.get("private"):
            raise GitHubStoragePublicRepoError(
                f"Le dépôt « {self.owner}/{self.repo} » est public : les saisies "
                "seraient visibles par tout le monde. Indiquez un dépôt privé dans "
                "la clé `repo` des Secrets."
            )
        self._verified_private_repos.add(self.repo_path)

    def ensure_branch(self) -> str:
        """Crée la branche de données si nécessaire et renvoie son commit courant."""
        self.ensure_private()
        current = self._read_ref(self.branch)
        if current is not None:
            return str(current["object"]["sha"])

        source = self._read_ref(self.source_branch)
        if source is None:
            raise GitHubStorageError(
                f"La branche source « {self.source_branch} » est introuvable."
            )
        source_sha = str(source["object"]["sha"])
        try:
            created = self._request(
                "POST",
                f"{self.repo_path}/git/refs",
                {"ref": f"refs/heads/{self.branch}", "sha": source_sha},
            )
            return str(created["object"]["sha"])
        except GitHubStorageError as exc:
            # Deux instances peuvent tenter la création au même moment.
            if exc.status != 422:
                raise
            current = self._read_ref(self.branch)
            if current is None:
                raise
            return str(current["object"]["sha"])

    @property
    def _head_key(self) -> str:
        return f"{self.repo_path}@{self.branch}"

    def _remember_head(self, commit_sha: str, tree_sha: str | None = None) -> None:
        known = self._known_heads.get(self._head_key)
        if tree_sha is None and known is not None and known[0] == commit_sha:
            tree_sha = known[1]
        self._known_heads[self._head_key] = (commit_sha, tree_sha, time.monotonic())

    def forget_head(self) -> None:
        """Oublie le commit mémorisé : la prochaine lecture interrogera GitHub."""
        self._known_heads.pop(self._head_key, None)

    def head_sha(self) -> str:
        head = self.ensure_branch()
        self._remember_head(head)
        return head

    def cached_head_sha(self, max_age: float) -> str:
        """Commit courant, relu sur GitHub au plus une fois toutes les ``max_age`` s.

        Une valeur un peu ancienne reste sans danger : un commit construit sur
        un parent périmé est refusé par GitHub (mise à jour non fast-forward).
        """
        known = self._known_heads.get(self._head_key)
        if known is not None and time.monotonic() - known[2] < max_age:
            return known[0]
        return self.head_sha()

    def _tree_entry(self, path: str, content: bytes) -> dict[str, str]:
        entry = {"path": path.strip("/"), "mode": "100644", "type": "blob"}
        try:
            # Un texte UTF-8 est envoyé directement dans l'arbre : GitHub crée
            # le blob lui-même, ce qui évite une requête par fichier.
            entry["content"] = content.decode("utf-8")
        except UnicodeDecodeError:
            blob = self._request(
                "POST",
                f"{self.repo_path}/git/blobs",
                {
                    "content": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                },
            )
            entry["sha"] = str(blob["sha"])
        return entry

    def download_files(
        self, paths: Sequence[str]
    ) -> tuple[dict[str, bytes | None], str]:
        """Télécharge un instantané cohérent et renvoie aussi son commit."""
        for _ in range(3):
            head_before = self.head_sha()
            files: dict[str, bytes | None] = {}
            for path in paths:
                encoded_path = quote(path.strip("/"), safe="/")
                encoded_ref = quote(self.branch, safe="")
                response = self._request(
                    "GET",
                    f"{self.repo_path}/contents/{encoded_path}?ref={encoded_ref}",
                    allow_not_found=True,
                )
                if response is None:
                    files[path] = None
                    continue
                if response.get("type") != "file" or response.get("encoding") != "base64":
                    raise GitHubStorageError(f"Le chemin GitHub « {path} » n'est pas un fichier.")
                try:
                    files[path] = base64.b64decode(response["content"], validate=False)
                except (KeyError, ValueError) as exc:
                    raise GitHubStorageError(
                        f"Le fichier GitHub « {path} » est illisible."
                    ) from exc
            head_after = self.head_sha()
            if head_before == head_after:
                return files, head_after
        raise GitHubStorageConflictError(
            "Les données GitHub changent trop rapidement. Actualisez puis réessayez."
        )

    def commit_files(
        self,
        files: Mapping[str, bytes],
        *,
        message: str,
        expected_head: str | None = None,
    ) -> str:
        """Enregistre tous les fichiers dans un seul commit atomique."""
        if not files:
            return self.head_sha()

        self.ensure_private()
        # Avec expected_head, inutile de relire la branche : si elle a bougé
        # entre-temps, la mise à jour finale (non forcée) est refusée.
        head = expected_head or self.head_sha()
        known = self._known_heads.get(self._head_key)
        if known is not None and known[0] == head and known[1] is not None:
            base_tree = known[1]
        else:
            commit = self._request("GET", f"{self.repo_path}/git/commits/{head}")
            base_tree = str(commit["tree"]["sha"])

        tree = self._request(
            "POST",
            f"{self.repo_path}/git/trees",
            {
                "base_tree": base_tree,
                "tree": [self._tree_entry(path, content) for path, content in files.items()],
            },
        )
        new_commit = self._request(
            "POST",
            f"{self.repo_path}/git/commits",
            {"message": message, "tree": tree["sha"], "parents": [head]},
        )
        try:
            self._request(
                "PATCH",
                f"{self.repo_path}/git/refs/heads/{quote(self.branch, safe='/')}",
                {"sha": new_commit["sha"], "force": False},
            )
        except GitHubStorageError as exc:
            self.forget_head()
            if exc.status in {409, 422}:
                raise GitHubStorageConflictError(
                    "Les données ont été modifiées dans une autre session. "
                    "Actualisez la page avant de recommencer."
                ) from exc
            raise
        self._remember_head(str(new_commit["sha"]), str(tree["sha"]))
        return str(new_commit["sha"])
