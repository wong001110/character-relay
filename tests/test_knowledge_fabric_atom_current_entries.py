from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from sqlalchemy import select

from echo_masque.knowledge_fabric_atom_adapter import AtomResponseInput, KnowledgeFabricAtomAdapter
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
    KnowledgeSourceCurrentEntryRecord,
)
from echo_masque.persistence.knowledge_fabric_projection_repository import (
    KnowledgeFabricProjectionRepository,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


class _Storage:
    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: dict[str, str],
    ) -> StoredKnowledgeObject:
        del metadata
        self.objects.setdefault(object_key, content)
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="knowledge-private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.objects[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.objects.pop(object_key, None) is not None


def _feed(
    entries: tuple[tuple[str, str], ...],
    *,
    titles: dict[str, str] | None = None,
    links: dict[str, str] | None = None,
) -> bytes:
    titles = titles or {}
    links = links or {}
    body = "".join(
        "<entry>"
        f"<id>{entry_id}</id><title>{titles.get(entry_id, entry_id)}</title>"
        f"{f'<link href={links[entry_id]!r}/>' if entry_id in links else ''}"
        f"<summary>{text}</summary></entry>"
        for entry_id, text in entries
    )
    return (
        '<feed xmlns="http://www.w3.org/2005/Atom"><title>Feed</title>' + body + "</feed>"
    ).encode()


def test_atom_current_entry_mapping_preserves_unchanged_evidence_and_excludes_removed_entries(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'atom-current.db'}")
    database.initialize()
    storage = _Storage()
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Atom", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="atom_public_https",
        locator="https://example.test/feed",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    service = KnowledgeFabricIngestionService(content, storage, object_key_prefix="knowledge")
    adapter = KnowledgeFabricAtomAdapter()

    def ingest(
        entries: tuple[tuple[str, str], ...],
        *,
        titles: dict[str, str] | None = None,
        links: dict[str, str] | None = None,
    ):
        return service.ingest_snapshot(
            adapter.build_snapshot(
                AtomResponseInput(
                    source_id=source.id,
                    locator=source.locator,
                    content=_feed(entries, titles=titles, links=links),
                    content_type="application/atom+xml",
                    fetched_at=datetime(2026, 8, 26, tzinfo=UTC),
                )
            )
        )

    first = ingest((("a", "old alpha"), ("b", "stable beta"), ("c", "removed gamma")))
    index = KnowledgeFabricIndexRepository(database)
    first_entries = index.rebuild_entries_for_source_version(first.id)
    assert len(first_entries) == 3
    projections = KnowledgeFabricProjectionRepository(database)
    first_projection = projections.get_source_overview(source.id)
    assert first_projection is not None
    with database.session() as session:
        before = {
            item.entry_locator: item.current_evidence_unit_id
            for item in session.scalars(
                select(KnowledgeSourceCurrentEntryRecord).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id
                )
            )
        }

    second = ingest((("a", "new alpha"), ("b", "stable beta"), ("d", "new delta")))
    second_entries = index.rebuild_entries_for_source_version(second.id)
    assert len(second_entries) == 2
    rebuilt_projection = projections.get_source_overview(source.id)
    assert rebuilt_projection is not None
    with database.session() as session:
        mappings = {
            item.entry_locator: item
            for item in session.scalars(
                select(KnowledgeSourceCurrentEntryRecord).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id
                )
            )
        }
    beta_hash = sha256(b"b").hexdigest()
    gamma_hash = sha256(b"c").hexdigest()
    beta_locator = next(locator for locator in mappings if locator.endswith(beta_hash))
    gamma_locator = next(locator for locator in mappings if locator.endswith(gamma_hash))
    assert mappings[beta_locator].current_evidence_unit_id == before[beta_locator]
    assert mappings[gamma_locator].status == "removed"
    assert any(
        item.evidence_unit_id == before[beta_locator]
        for item in rebuilt_projection.provenance
    )
    assert "stable beta" in rebuilt_projection.text_content
    assert "removed gamma" not in rebuilt_projection.text_content
    assert rebuilt_projection.id == first_projection.id
    candidates = index.search_sparse(
        authorized_corpus_ids=frozenset({corpus.id}),
        query="alpha beta gamma delta",
        candidate_limit=10,
    )
    assert {item.text_content for item in candidates} == {"new alpha", "stable beta", "new delta"}
    assert {item.id for item in content.list_source_versions(source.id)} == {first.id, second.id}

    third = ingest((("d", "new delta"), ("b", "stable beta"), ("a", "new alpha")))
    assert index.rebuild_entries_for_source_version(third.id) == []
    no_op_projection = projections.get_source_overview(source.id)
    assert no_op_projection is not None
    assert no_op_projection.id == rebuilt_projection.id
    assert no_op_projection.source_hash == rebuilt_projection.source_hash
    assert no_op_projection.provenance == rebuilt_projection.provenance
    assert content.list_pending_invalidations(third.id) == []

    renamed_beta = ingest(
        (("a", "new alpha"), ("b", "stable beta"), ("d", "new delta")),
        titles={"b": "Renamed beta"},
        links={"b": "https://example.test/updated-beta"},
    )
    with database.session() as session:
        refreshed_beta = session.scalar(
            select(KnowledgeSourceCurrentEntryRecord).where(
                KnowledgeSourceCurrentEntryRecord.entry_locator == beta_locator
            )
        )
        assert refreshed_beta is not None
        assert refreshed_beta.current_evidence_unit_id != before[beta_locator]
        assert (
            session.scalar(
                select(KnowledgeEvidenceRetrievalEntryRecord).where(
                    KnowledgeEvidenceRetrievalEntryRecord.evidence_unit_id
                    == before[beta_locator]
                )
            )
            is None
        )
    assert len(index.rebuild_entries_for_source_version(renamed_beta.id)) == 1
    renamed_projection = projections.get_source_overview(source.id)
    assert renamed_projection is not None
    assert "[Renamed beta]" in renamed_projection.text_content
    retained_beta_dependency = next(
        item
        for item in rebuilt_projection.provenance
        if item.evidence_unit_id == before[beta_locator]
    )
    assert retained_beta_dependency.source_version_id == first.id

    deletion_counts = content.delete_content_for_corpora([corpus.id])
    assert deletion_counts["knowledge_fabric_source_current_entries"] == 4
    with database.session() as session:
        assert (
            session.scalar(
                select(KnowledgeSourceCurrentEntryRecord).where(
                    KnowledgeSourceCurrentEntryRecord.source_id == source.id
                )
            )
            is None
        )
