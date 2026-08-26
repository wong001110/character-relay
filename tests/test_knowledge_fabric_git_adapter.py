from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path

import pytest
from sqlalchemy import func, select

from echo_masque.knowledge_fabric_git_adapter import (
    GitFileSnapshot,
    GitRepositorySnapshot,
    GitSnapshotError,
    KnowledgeFabricGitAdapter,
)
from echo_masque.knowledge_fabric_git_policy import (
    GIT_SOURCE_TYPE,
    deterministic_git_snapshot_idempotency_key,
    git_snapshot_identifiers_are_compatible,
    git_snapshot_path_is_allowed,
    git_snapshot_path_is_safe,
)
from echo_masque.knowledge_fabric_ingestion import KnowledgeFabricIngestionService
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_index_repository import (
    KnowledgeFabricIndexRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeEvidenceRetrievalEntryRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


@dataclass
class FakeObjectStorage:
    objects: dict[str, tuple[bytes, str, dict[str, str]]]
    put_calls: int = 0

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        self.put_calls += 1
        self.objects.setdefault(object_key, (content, content_type, dict(metadata)))
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key][0]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


def _service(
    tmp_path: Path,
) -> tuple[
    Database,
    FakeObjectStorage,
    KnowledgeFabricRepository,
    KnowledgeFabricContentRepository,
    KnowledgeFabricIngestionService,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'git-adapter.db'}")
    database.initialize()
    storage = FakeObjectStorage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Git Fabric",
        description="",
        default_authority_profile="standard",
        status="active",
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type=GIT_SOURCE_TYPE,
        locator="https://github.com/example/character-relay",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    return (
        database,
        storage,
        fabric,
        content,
        KnowledgeFabricIngestionService(content, storage, object_key_prefix="knowledge-fabric"),
        source.id,
    )


def _snapshot(
    *,
    source_id: str,
    commit_id: str,
    tree_id: str,
    files: Sequence[GitFileSnapshot],
    parent_commit_id: str | None = None,
) -> GitRepositorySnapshot:
    return GitRepositorySnapshot(
        source_id=source_id,
        canonical_base_locator="https://github.com/example/character-relay",
        commit_id=commit_id,
        tree_id=tree_id,
        parent_commit_id=parent_commit_id,
        files=files,
    )


def test_git_policy_validates_immutable_identity_safe_paths_and_retry_keys() -> None:
    sha1_commit = "A" * 40
    sha1_tree = "b" * 40
    sha256_tree = "c" * 64

    assert git_snapshot_identifiers_are_compatible(
        commit_id=sha1_commit,
        tree_id=sha1_tree,
    )
    assert not git_snapshot_identifiers_are_compatible(
        commit_id=sha1_commit,
        tree_id=sha256_tree,
    )
    assert not git_snapshot_identifiers_are_compatible(
        commit_id="short",
        tree_id=sha1_tree,
    )
    assert git_snapshot_path_is_safe("src/relay.py")
    assert git_snapshot_path_is_safe("README.md")
    assert git_snapshot_path_is_safe("src/space name.py")
    assert git_snapshot_path_is_allowed("src/relay.py")
    assert not git_snapshot_path_is_allowed(".env")
    for denied_path in (
        "",
        " ",
        "/etc/passwd",
        "C:/windows/system32",
        "src\\relay.py",
        "src/relay\x1f.py",
        "../relay.py",
        "src/../relay.py",
        "src//relay.py",
        "src/./relay.py",
        ".git/config",
        ".env",
        ".env.production",
        "secrets/service-account.json",
        "keys/id_ed25519",
        "keys/production.pem",
        "node_modules/package/index.js",
        "src/node_modules/package/index.js",
        "vendor/package/index.py",
        ".venv/lib/site.py",
        "venv/lib/site.py",
        "__pycache__/relay.pyc",
        "dist/app.js",
        "build/app.js",
        ".cache/response",
        ".pytest_cache/nodeids",
        ".mypy_cache/state.json",
    ):
        assert not git_snapshot_path_is_safe(denied_path)

    key = deterministic_git_snapshot_idempotency_key(
        source_id="source-1",
        commit_id=sha1_commit,
        tree_id=sha1_tree,
    )
    assert key == deterministic_git_snapshot_idempotency_key(
        source_id="source-1",
        commit_id=sha1_commit.casefold(),
        tree_id=sha1_tree.upper(),
    )
    assert key != deterministic_git_snapshot_idempotency_key(
        source_id="source-1",
        commit_id="d" * 40,
        tree_id=sha1_tree,
    )
    assert key != deterministic_git_snapshot_idempotency_key(
        source_id="source-2",
        commit_id=sha1_commit,
        tree_id=sha1_tree,
    )
    expected_digest = sha256(
        ("source-1\0" + sha1_commit.casefold() + "\0" + sha1_tree.casefold()).encode()
    ).hexdigest()
    assert key == f"{GIT_SOURCE_TYPE}:{expected_digest}"
    with pytest.raises(ValueError, match=r"^Git snapshot source identity is required\.$"):
        deterministic_git_snapshot_idempotency_key(
            source_id=" ",
            commit_id=sha1_commit,
            tree_id=sha1_tree,
        )
    with pytest.raises(
        ValueError,
        match=r"^Git snapshot commit and tree identities are invalid\.$",
    ):
        deterministic_git_snapshot_idempotency_key(
            source_id="source-1",
            commit_id=sha1_commit,
            tree_id=sha256_tree,
        )


def test_git_adapter_compiles_only_safe_text_files_with_code_structure() -> None:
    secret = b"do-not-persist-private-git-secret"
    adapter = KnowledgeFabricGitAdapter()
    value = _snapshot(
        source_id="source-1",
        commit_id="a" * 40,
        tree_id="b" * 40,
        files=(
            GitFileSnapshot(".env", secret),
            GitFileSnapshot("dist/app.js", secret),
            GitFileSnapshot("keys/id_ed25519", secret),
            GitFileSnapshot("node_modules/package/index.js", secret),
            GitFileSnapshot("src/opaque.bin", b"\xff\xfe"),
            GitFileSnapshot("README.md", b"# Relay\n\nCurrent architecture."),
            GitFileSnapshot(
                "src/relay.py",
                b"import collections\nfrom .core import engine\n\n"
                b"class Relay:\n    pass\n\n"
                b"def current_symbol() -> str:\n    return 'current'\n",
            ),
        ),
    )

    request = adapter.build_snapshot(value)
    reordered = adapter.build_snapshot(
        _snapshot(
            source_id=value.source_id,
            commit_id=value.commit_id,
            tree_id=value.tree_id,
            files=tuple(reversed(value.files)),
        )
    )

    assert request == reordered
    assert request.activate_git_version is True
    assert request.artifact_content_type == "application/vnd.echo-masque.git-snapshot+json"
    artifact = json.loads(request.artifact_content)
    assert [item["path"] for item in artifact["files"]] == ["README.md", "src/relay.py"]
    assert secret.decode("utf-8") not in request.artifact_content.decode("utf-8")
    assert [item.canonical_locator for item in request.documents] == [
        "https://github.com/example/character-relay/blob/" + "a" * 40 + "/README.md",
        "https://github.com/example/character-relay/blob/" + "a" * 40 + "/src/relay.py",
    ]
    python_document = request.documents[1]
    assert python_document.metadata == {
        "imports": [".core", "collections"],
        "path": "src/relay.py",
    }
    assert [(item.heading, item.coordinates["kind"]) for item in python_document.sections] == [
        ("Relay", "class"),
        ("current_symbol", "function"),
    ]
    assert [item.block_type for item in python_document.blocks] == [
        "python_class",
        "python_function",
    ]

    with pytest.raises(GitSnapshotError):
        adapter.build_snapshot(
            _snapshot(
                source_id="source-1",
                commit_id="a" * 40,
                tree_id="b" * 64,
                files=(GitFileSnapshot("README.md", b"safe"),),
            )
        )


def test_git_current_version_changes_query_visibility_without_erasing_retained_evidence(
    tmp_path: Path,
) -> None:
    database, storage, _fabric, content, service, source_id = _service(tmp_path)
    adapter = KnowledgeFabricGitAdapter()
    index = KnowledgeFabricIndexRepository(database)
    denied_secret = b"do-not-persist-git-denied-secret"
    first = _snapshot(
        source_id=source_id,
        commit_id="a" * 40,
        tree_id="b" * 40,
        files=(
            GitFileSnapshot(".env", denied_secret),
            GitFileSnapshot(
                "src/relay.py",
                b"def legacy_symbol() -> str:\n    return 'legacy-only'\n",
            ),
        ),
    )
    first_version = adapter.ingest(service=service, snapshot=first)
    index.rebuild_entries_for_source_version(first_version.id)
    first_artifact = content.get_artifact(first_version.artifact_id)
    assert first_artifact is not None
    assert denied_secret not in storage.get_private(object_key=first_artifact.object_key)
    assert all(
        denied_secret.decode("utf-8") not in document.canonical_locator
        and denied_secret.decode("utf-8") not in document.metadata_json
        for document in content.list_canonical_documents(first_version.id)
    )
    assert all(
        denied_secret.decode("utf-8") not in evidence.text_content
        and denied_secret.decode("utf-8") not in evidence.evidence_locator
        for evidence in content.list_evidence_units(first_version.id)
    )
    assert all(
        denied_secret.decode("utf-8") not in checkpoint.metadata_json
        for checkpoint in content.list_ingestion_checkpoints(
            content.get_or_create_ingestion_job(
                source_id=source_id,
                job_type="source_snapshot",
                idempotency_key=adapter.build_snapshot(first).idempotency_key,
            ).id
        )
    )

    second = _snapshot(
        source_id=source_id,
        commit_id="c" * 40,
        tree_id="d" * 40,
        parent_commit_id=first.commit_id,
        files=(
            GitFileSnapshot(
                "src/relay.py",
                b"def current_symbol() -> str:\n    return 'current-only'\n",
            ),
        ),
    )
    second_version = adapter.ingest(service=service, snapshot=second)
    index.rebuild_entries_for_source_version(second_version.id)

    versions = {item.version_key: item for item in content.list_source_versions(source_id)}
    assert versions[first.commit_id].status == "superseded"
    assert versions[second.commit_id].status == "available"
    assert content.list_evidence_units(first_version.id)
    with database.session() as session:
        retained_entries = session.scalar(
            select(func.count(KnowledgeEvidenceRetrievalEntryRecord.id)).where(
                KnowledgeEvidenceRetrievalEntryRecord.source_version_id == first_version.id
            )
        )
    assert retained_entries == 1

    corpus_id = content.get_source(source_id)
    assert corpus_id is not None
    candidates = index.search_sparse(
        authorized_corpus_ids=frozenset({corpus_id.corpus_id}),
        query="symbol",
        candidate_limit=10,
    )
    assert [(item.source_version_id, item.text_content) for item in candidates] == [
        (second_version.id, "def current_symbol() -> str:\n    return 'current-only'"),
    ]
    assert storage.put_calls == 2

    reactivated = adapter.ingest(service=service, snapshot=first)
    assert reactivated.id == first_version.id
    assert storage.put_calls == 2
    versions = {item.version_key: item for item in content.list_source_versions(source_id)}
    assert versions[first.commit_id].status == "available"
    assert versions[second.commit_id].status == "superseded"
    candidates = index.search_sparse(
        authorized_corpus_ids=frozenset({corpus_id.corpus_id}),
        query="symbol",
        candidate_limit=10,
    )
    assert [(item.source_version_id, item.text_content) for item in candidates] == [
        (first_version.id, "def legacy_symbol() -> str:\n    return 'legacy-only'"),
    ]


def test_git_activation_rejects_non_git_source_before_private_upload(tmp_path: Path) -> None:
    _database, storage, fabric, content, service, source_id = _service(tmp_path)
    source = content.get_source(source_id)
    assert source is not None
    manual = fabric.create_source(
        corpus_id=source.corpus_id,
        source_type="manual_text",
        locator="https://docs.example.test/manual",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    request = KnowledgeFabricGitAdapter().build_snapshot(
        _snapshot(
            source_id=manual.id,
            commit_id="a" * 40,
            tree_id="b" * 40,
            files=(GitFileSnapshot("README.md", b"safe content"),),
        )
    )

    with pytest.raises(ValueError, match="Git activation requires a Git snapshot Source"):
        service.ingest_snapshot(request)

    assert storage.put_calls == 0
    assert content.list_source_versions(manual.id) == []
