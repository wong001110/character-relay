"""Pure safety and identity rules for Phase 8b Git snapshots."""

from __future__ import annotations

import re
from hashlib import sha256

GIT_SOURCE_TYPE = "git_snapshot"

_GIT_OBJECT_ID = re.compile(r"^(?:[0-9a-fA-F]{40}|[0-9a-fA-F]{64})$")
_WINDOWS_DRIVE_PATH = re.compile(r"^[a-zA-Z]:")
_DENIED_PATH_DIRECTORIES = frozenset(
    {
        ".cache",
        ".mypy_cache",
        ".pytest_cache",
        ".venv",
        "__pycache__",
        "build",
        "dist",
        "node_modules",
        "vendor",
        "venv",
    }
)
_DENIED_CREDENTIAL_FILENAMES = frozenset(
    {
        ".netrc",
        ".npmrc",
        ".pypirc",
        "auth.json",
        "credential",
        "credential.json",
        "credentials",
        "credentials.json",
        "id_dsa",
        "id_ecdsa",
        "id_ed25519",
        "id_rsa",
        "id_xmss",
        "private-key",
        "private_key",
        "secret",
        "secret.json",
        "secret.yaml",
        "secret.yml",
        "secrets",
        "secrets.json",
        "secrets.yaml",
        "secrets.yml",
        "service-account.json",
        "service_account.json",
        "token",
        "token.json",
    }
)
_DENIED_CREDENTIAL_SUFFIXES = (
    ".jks",
    ".kdb",
    ".kdbx",
    ".key",
    ".keystore",
    ".p12",
    ".pem",
    ".pfx",
    ".secret",
)


def git_object_identifier_is_valid(identifier: str) -> bool:
    """Accept only a complete SHA-1 or SHA-256 Git object identifier."""

    return _GIT_OBJECT_ID.fullmatch(identifier) is not None


def git_commit_identifier_is_valid(commit_id: str) -> bool:
    """Commit identifiers use the same complete Git object-id syntax."""

    return git_object_identifier_is_valid(commit_id)


def git_tree_identifier_is_valid(tree_id: str) -> bool:
    """Tree identifiers use the same complete Git object-id syntax."""

    return git_object_identifier_is_valid(tree_id)


def git_snapshot_identifiers_are_compatible(*, commit_id: str, tree_id: str) -> bool:
    """A snapshot cannot mix SHA-1 and SHA-256 object databases."""

    return (
        git_commit_identifier_is_valid(commit_id)
        and git_tree_identifier_is_valid(tree_id)
        and len(commit_id) == len(tree_id)
    )


def git_snapshot_path_is_safe(path: str) -> bool:
    """Allow only safe repository-relative files under the approved deny policy."""

    if not path or not path.strip() or "\\" in path or _WINDOWS_DRIVE_PATH.match(path):
        return False
    if any(ord(character) < 32 for character in path):
        return False

    path_parts = path.split("/")
    if any(part in {"", ".", ".."} for part in path_parts):
        return False

    normalized_parts = tuple(part.casefold() for part in path_parts)
    if ".git" in normalized_parts or any(
        part in _DENIED_PATH_DIRECTORIES for part in normalized_parts[:-1]
    ):
        return False

    filename = normalized_parts[-1]
    if filename == ".env" or filename.startswith(".env."):
        return False
    if filename in _DENIED_CREDENTIAL_FILENAMES:
        return False
    return not filename.endswith(_DENIED_CREDENTIAL_SUFFIXES)


def git_snapshot_path_is_allowed(path: str) -> bool:
    """Alias the explicit allow decision for callers that phrase it positively."""

    return git_snapshot_path_is_safe(path)


def deterministic_git_snapshot_idempotency_key(
    *, source_id: str, commit_id: str, tree_id: str
) -> str:
    """Derive a stable retry key without accepting a Git locator or credentials."""

    if not source_id.strip():
        raise ValueError("Git snapshot source identity is required.")
    if not git_snapshot_identifiers_are_compatible(
        commit_id=commit_id, tree_id=tree_id
    ):
        raise ValueError("Git snapshot commit and tree identities are invalid.")
    digest_input = "\0".join(
        (source_id, commit_id.casefold(), tree_id.casefold())
    ).encode()
    return f"{GIT_SOURCE_TYPE}:{sha256(digest_input).hexdigest()}"


__all__ = [
    "GIT_SOURCE_TYPE",
    "deterministic_git_snapshot_idempotency_key",
    "git_commit_identifier_is_valid",
    "git_object_identifier_is_valid",
    "git_snapshot_identifiers_are_compatible",
    "git_snapshot_path_is_allowed",
    "git_snapshot_path_is_safe",
    "git_tree_identifier_is_valid",
]
