"""Deterministic Git snapshot compilation without acquisition or credential authority."""

from __future__ import annotations

import ast
import base64
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from urllib.parse import quote

from echo_masque.knowledge_fabric_git_policy import (
    deterministic_git_snapshot_idempotency_key,
    git_object_identifier_is_valid,
    git_snapshot_identifiers_are_compatible,
    git_snapshot_path_is_safe,
)
from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    CanonicalSectionInput,
)
from echo_masque.persistence.knowledge_fabric_models import KnowledgeSourceVersionRecord


class GitSnapshotError(ValueError):
    """The trusted acquisition boundary supplied an invalid immutable Git snapshot."""


class GitSnapshotHasNoEligibleFiles(GitSnapshotError):
    """No safe decodable text file can form a source-addressable Git snapshot."""


@dataclass(frozen=True, slots=True)
class GitFileSnapshot:
    """One path and its bytes supplied by an already-authorized Git acquisition boundary."""

    path: str
    content: bytes


@dataclass(frozen=True, slots=True)
class GitRepositorySnapshot:
    """An immutable repository tree; this type deliberately has no path or credential fields."""

    source_id: str
    canonical_base_locator: str
    commit_id: str
    tree_id: str
    files: Sequence[GitFileSnapshot]
    parent_commit_id: str | None = None
    committed_at: datetime | None = None


class KnowledgeFabricGitAdapter:
    """Compile a sanitized immutable Git tree into the existing Source snapshot contract."""

    def build_snapshot(self, value: GitRepositorySnapshot) -> SourceSnapshotIngestionRequest:
        """Create a request that atomically makes this Git revision current when published."""

        self._validate_snapshot(value)
        files = self._eligible_files(value.files)
        if not files:
            raise GitSnapshotHasNoEligibleFiles("Git snapshot has no eligible text files.")
        documents = tuple(
            self._document_from_file(
                file,
                canonical_base_locator=value.canonical_base_locator,
                commit_id=value.commit_id,
            )
            for file in files
        )
        return SourceSnapshotIngestionRequest(
            source_id=value.source_id,
            version_key=value.commit_id,
            idempotency_key=deterministic_git_snapshot_idempotency_key(
                source_id=value.source_id,
                commit_id=value.commit_id,
                tree_id=value.tree_id,
            ),
            artifact_content=_sanitized_tree_artifact(
                commit_id=value.commit_id,
                tree_id=value.tree_id,
                parent_commit_id=value.parent_commit_id,
                files=files,
            ),
            artifact_content_type="application/vnd.echo-masque.git-snapshot+json",
            documents=documents,
            published_at=value.committed_at,
            metadata={
                "adapter": "git_snapshot",
                "commit_id": value.commit_id,
                "tree_id": value.tree_id,
                "parent_commit_id": value.parent_commit_id or "",
                "file_count": len(files),
            },
            activate_git_version=True,
        )

    def ingest(
        self,
        *,
        service: KnowledgeFabricIngestionService,
        snapshot: GitRepositorySnapshot,
    ) -> KnowledgeSourceVersionRecord:
        """Publish through the existing private storage/job service, never a direct R2/S3 call."""

        return service.ingest_snapshot(self.build_snapshot(snapshot))

    @staticmethod
    def _validate_snapshot(value: GitRepositorySnapshot) -> None:
        if not value.source_id.strip() or not value.canonical_base_locator.strip():
            raise GitSnapshotError("Git snapshot source identity is required.")
        if not git_snapshot_identifiers_are_compatible(
            commit_id=value.commit_id,
            tree_id=value.tree_id,
        ):
            raise GitSnapshotError("Git commit and tree identities are invalid.")
        if (
            value.parent_commit_id is not None
            and (
                not git_object_identifier_is_valid(value.parent_commit_id)
                or len(value.parent_commit_id) != len(value.commit_id)
            )
        ):
            raise GitSnapshotError("Git parent commit identity is invalid.")

    @staticmethod
    def _eligible_files(files: Sequence[GitFileSnapshot]) -> tuple[GitFileSnapshot, ...]:
        eligible: list[GitFileSnapshot] = []
        paths: set[str] = set()
        for item in sorted(files, key=lambda candidate: candidate.path):
            if not git_snapshot_path_is_safe(item.path):
                continue
            if item.path in paths:
                raise GitSnapshotError("Git snapshot has duplicate file paths.")
            try:
                item.content.decode("utf-8")
            except UnicodeDecodeError:
                continue
            paths.add(item.path)
            eligible.append(item)
        return tuple(eligible)

    @staticmethod
    def _document_from_file(
        value: GitFileSnapshot,
        *,
        canonical_base_locator: str,
        commit_id: str,
    ) -> CanonicalDocumentInput:
        decoded = value.content.decode("utf-8")
        language = _language_for_path(value.path)
        blocks, sections, metadata = _structured_blocks(
            path=value.path,
            content=decoded,
            language=language,
        )
        return CanonicalDocumentInput(
            canonical_locator=(
                f"{canonical_base_locator.rstrip('/')}/blob/{commit_id}/"
                f"{quote(value.path, safe='/')}"
            ),
            title=value.path.rsplit("/", maxsplit=1)[-1],
            mime_type=_mime_type_for_path(value.path),
            language=language,
            metadata=metadata,
            sections=sections,
            blocks=blocks,
        )


def _sanitized_tree_artifact(
    *,
    commit_id: str,
    tree_id: str,
    parent_commit_id: str | None,
    files: Sequence[GitFileSnapshot],
) -> bytes:
    """Serialize only accepted text files so deny-listed bytes never enter object storage."""

    payload = {
        "commit_id": commit_id,
        "files": [
            {
                "content_base64": base64.b64encode(item.content).decode("ascii"),
                "content_sha256": sha256(item.content).hexdigest(),
                "path": item.path,
            }
            for item in files
        ],
        "parent_commit_id": parent_commit_id or "",
        "tree_id": tree_id,
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _structured_blocks(
    *,
    path: str,
    content: str,
    language: str | None,
) -> tuple[
    tuple[CanonicalBlockInput, ...],
    tuple[CanonicalSectionInput, ...],
    dict[str, object],
]:
    if language == "python":
        return _python_structure(path=path, content=content)
    lines = content.splitlines()
    return (
        (
            CanonicalBlockInput(
                structural_path="file:0",
                block_type="code_file",
                ordinal=0,
                text_content=content,
                coordinates={"line_start": 1, "line_end": max(1, len(lines)), "path": path},
            ),
        ),
        (),
        {"path": path},
    )


def _python_structure(
    *,
    path: str,
    content: str,
) -> tuple[
    tuple[CanonicalBlockInput, ...],
    tuple[CanonicalSectionInput, ...],
    dict[str, object],
]:
    try:
        tree = ast.parse(content)
    except SyntaxError:
        fallback_blocks, fallback_sections, metadata = _structured_blocks(
            path=path,
            content=content,
            language=None,
        )
        return fallback_blocks, fallback_sections, {**metadata, "language_parse_error": True}
    imports = _python_imports(tree)
    symbols = [
        item
        for item in tree.body
        if isinstance(item, ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef)
    ]
    if not symbols:
        fallback_blocks, fallback_sections, _metadata = _structured_blocks(
            path=path,
            content=content,
            language=None,
        )
        return fallback_blocks, fallback_sections, {"imports": imports, "path": path}
    lines = content.splitlines(keepends=True)
    sections: list[CanonicalSectionInput] = []
    blocks: list[CanonicalBlockInput] = []
    for ordinal, symbol in enumerate(symbols):
        kind = "class" if isinstance(symbol, ast.ClassDef) else "function"
        section_path = f"symbol:{ordinal}"
        line_start = symbol.lineno
        line_end = symbol.end_lineno or line_start
        sections.append(
            CanonicalSectionInput(
                structural_path=section_path,
                heading=symbol.name,
                ordinal=ordinal,
                coordinates={
                    "kind": kind,
                    "line_end": line_end,
                    "line_start": line_start,
                    "path": path,
                },
            )
        )
        blocks.append(
            CanonicalBlockInput(
                structural_path=f"{section_path}:body",
                block_type=f"python_{kind}",
                ordinal=ordinal,
                text_content="".join(lines[line_start - 1 : line_end]).strip(),
                section_path=section_path,
                coordinates={
                    "kind": kind,
                    "line_end": line_end,
                    "line_start": line_start,
                    "path": path,
                    "symbol": symbol.name,
                },
            )
        )
    return tuple(blocks), tuple(sections), {"imports": imports, "path": path}


def _python_imports(tree: ast.Module) -> list[str]:
    values: list[str] = []
    for node in tree.body:
        if isinstance(node, ast.Import):
            values.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            values.append(("." * node.level) + (node.module or ""))
    return sorted(set(values))


def _language_for_path(path: str) -> str | None:
    if path.casefold().endswith(".py"):
        return "python"
    if path.casefold().endswith((".md", ".markdown")):
        return "markdown"
    return None


def _mime_type_for_path(path: str) -> str:
    lower_path = path.casefold()
    if lower_path.endswith((".md", ".markdown")):
        return "text/markdown"
    if lower_path.endswith(".py"):
        return "text/x-python"
    if lower_path.endswith(".json"):
        return "application/json"
    return "text/plain"


__all__ = [
    "GitFileSnapshot",
    "GitRepositorySnapshot",
    "GitSnapshotError",
    "GitSnapshotHasNoEligibleFiles",
    "KnowledgeFabricGitAdapter",
]
