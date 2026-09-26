"""Tests du stockage GitHub sans réseau : GitHub est simulé en mémoire."""

import pytest

from github_storage import (
    GitHubStorage,
    GitHubStorageConflictError,
    GitHubStorageError,
    GitHubStoragePublicRepoError,
)

REPO = "/repos/owner/data-repo"


class FakeGitHub:
    """Imite les quelques routes de l'API GitHub utilisées par le stockage."""

    def __init__(self, *, private: bool = True) -> None:
        self.private = private
        self.head = "c1"
        self.trees = {"c1": "t1"}
        self.calls: list[tuple[str, str]] = []
        self.payloads: dict[str, dict] = {}
        self.reject_update = False
        self._next = 1

    def __call__(self, method, path, payload=None, *, allow_not_found=False):
        route = path.removeprefix(REPO) or "/"
        self.calls.append((method, route))
        if payload is not None:
            self.payloads[route] = payload
        if method == "GET" and route == "/":
            return {"private": self.private}
        if method == "GET" and route == "/git/ref/heads/data":
            return {"object": {"sha": self.head}}
        if method == "GET" and route.startswith("/git/commits/"):
            return {"tree": {"sha": self.trees[route.rsplit("/", 1)[1]]}}
        if method == "POST" and route == "/git/blobs":
            return {"sha": "blob"}
        if method == "POST" and route == "/git/trees":
            self._next += 1
            return {"sha": f"t{self._next}"}
        if method == "POST" and route == "/git/commits":
            sha = f"c{self._next}"
            self.trees[sha] = payload["tree"]
            return {"sha": sha}
        if method == "PATCH" and route == "/git/refs/heads/data":
            if self.reject_update:
                raise GitHubStorageError("Update is not a fast forward", status=422)
            self.head = payload["sha"]
            return {}
        raise AssertionError(f"Route inattendue : {method} {route}")

    def count(self, method: str, route: str) -> int:
        return sum(1 for call in self.calls if call == (method, route))


@pytest.fixture(autouse=True)
def reset_shared_caches():
    GitHubStorage._known_heads.clear()
    GitHubStorage._verified_private_repos.clear()
    yield
    GitHubStorage._known_heads.clear()
    GitHubStorage._verified_private_repos.clear()


def make_storage(fake: FakeGitHub) -> GitHubStorage:
    storage = GitHubStorage(token="t", owner="owner", repo="data-repo", branch="data")
    storage._request = fake
    return storage


def test_public_repository_is_refused():
    storage = make_storage(FakeGitHub(private=False))
    with pytest.raises(GitHubStoragePublicRepoError):
        storage.head_sha()


def test_head_is_reread_only_after_max_age():
    fake = FakeGitHub()
    storage = make_storage(fake)
    assert storage.cached_head_sha(max_age=30) == "c1"
    assert storage.cached_head_sha(max_age=30) == "c1"
    assert fake.count("GET", "/git/ref/heads/data") == 1
    # Partagé entre instances : une nouvelle session profite du même suivi.
    assert make_storage(fake).cached_head_sha(max_age=30) == "c1"
    assert fake.count("GET", "/git/ref/heads/data") == 1
    storage.cached_head_sha(max_age=0)
    assert fake.count("GET", "/git/ref/heads/data") == 2


def test_consecutive_saves_skip_redundant_requests():
    fake = FakeGitHub()
    storage = make_storage(fake)
    head = storage.cached_head_sha(max_age=30)

    first = storage.commit_files({"data/a.csv": b"x"}, message="1", expected_head=head)
    second = storage.commit_files({"data/a.csv": b"y"}, message="2", expected_head=first)

    assert fake.head == second
    # Arbre du premier commit lu une fois ; celui du second est déjà connu.
    assert fake.count("GET", "/git/commits/c1") == 1
    assert fake.count("GET", f"/git/commits/{first}") == 0
    assert fake.payloads["/git/trees"]["base_tree"] == fake.trees[first]
    # Après un enregistrement, la navigation n'interroge plus GitHub.
    refs_before = fake.count("GET", "/git/ref/heads/data")
    assert storage.cached_head_sha(max_age=30) == second
    assert fake.count("GET", "/git/ref/heads/data") == refs_before


def test_text_is_sent_inline_and_binary_as_blob():
    fake = FakeGitHub()
    storage = make_storage(fake)
    csv_with_bom = "﻿id,client\n1,Hakim\n".encode("utf-8")

    storage.commit_files({"data/a.csv": csv_with_bom, "data/b.bin": b"\xff\xfe"}, message="m")

    entries = {entry["path"]: entry for entry in fake.payloads["/git/trees"]["tree"]}
    assert entries["data/a.csv"]["content"].encode("utf-8") == csv_with_bom
    assert entries["data/b.bin"]["sha"] == "blob"
    assert fake.count("POST", "/git/blobs") == 1


def test_stale_head_raises_conflict_and_forgets_cache():
    fake = FakeGitHub()
    storage = make_storage(fake)
    storage.cached_head_sha(max_age=30)
    fake.head = "c-other"  # enregistrement fait ailleurs (autre appareil)
    fake.trees["c-other"] = "t-other"
    fake.reject_update = True

    with pytest.raises(GitHubStorageConflictError):
        storage.commit_files({"data/a.csv": b"x"}, message="m", expected_head="c1")

    fake.reject_update = False
    assert storage.cached_head_sha(max_age=30) == "c-other"
