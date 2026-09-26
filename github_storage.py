"""Stockage atomique de fichiers dans une branche GitHub.

Ce module utilise uniquement l'API REST GitHub et la bibliothèque standard.
Le jeton reste fourni par l'environnement d'exécution et n'est jamais écrit
dans le dépôt.
"""

from __future__ import annotations

import base64
import json
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


class GitHubStorage:
    """Lit et valide plusieurs fichiers dans un unique commit GitHub."""

    api_root = "https://api.github.com"

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

    def ensure_branch(self) -> str:
        """Crée la branche de données si nécessaire et renvoie son commit courant."""
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

    def head_sha(self) -> str:
        return self.ensure_branch()

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

        head = self.head_sha()
        if expected_head is not None and head != expected_head:
            raise GitHubStorageConflictError(
                "Les données ont été modifiées dans une autre session. "
                "Actualisez la page avant de recommencer."
            )

        commit = self._request("GET", f"{self.repo_path}/git/commits/{head}")
        tree_entries: list[dict[str, str]] = []
        for path, content in files.items():
            blob = self._request(
                "POST",
                f"{self.repo_path}/git/blobs",
                {
                    "content": base64.b64encode(content).decode("ascii"),
                    "encoding": "base64",
                },
            )
            tree_entries.append(
                {
                    "path": path.strip("/"),
                    "mode": "100644",
                    "type": "blob",
                    "sha": str(blob["sha"]),
                }
            )

        tree = self._request(
            "POST",
            f"{self.repo_path}/git/trees",
            {"base_tree": commit["tree"]["sha"], "tree": tree_entries},
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
            if exc.status in {409, 422}:
                raise GitHubStorageConflictError(
                    "Une autre sauvegarde a été effectuée en même temps. "
                    "Actualisez la page avant de recommencer."
                ) from exc
            raise
        return str(new_commit["sha"])
