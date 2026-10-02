from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_object_storage import StoredKnowledgeObject
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_content_repository import (
    CanonicalBlockInput,
    CanonicalDocumentInput,
    KnowledgeFabricContentRepository,
)
from echo_masque.persistence.knowledge_fabric_interpretation_repository import (
    KnowledgeFabricInterpretationRepository,
)
from echo_masque.persistence.knowledge_fabric_models import (
    KnowledgeCanonicalEntityRecord,
    KnowledgeCorpusRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository


@dataclass
class _PrivateStorage:
    values: dict[str, bytes]

    def put_private(
        self,
        *,
        object_key: str,
        content: bytes,
        content_type: str,
        metadata: Mapping[str, str],
    ) -> StoredKnowledgeObject:
        self.values.setdefault(object_key, content)
        return StoredKnowledgeObject(
            provider="cloudflare_r2",
            bucket="private",
            object_key=object_key,
            content_sha256=sha256(content).hexdigest(),
            byte_size=len(content),
            content_type=content_type,
        )

    def get_private(self, *, object_key: str) -> bytes:
        return self.values[object_key]

    def delete_private(self, *, object_key: str) -> bool:
        return self.values.pop(object_key, None) is not None


def _snapshot(
    source_id: str,
    *,
    version_key: str = "one",
) -> SourceSnapshotIngestionRequest:
    return SourceSnapshotIngestionRequest(
        source_id=source_id,
        version_key=version_key,
        idempotency_key=f"delivery-{version_key}",
        artifact_content=b"Evidence-backed canonical interpretation.",
        artifact_content_type="text/markdown",
        published_at=datetime(2026, 8, 25, tzinfo=UTC),
        documents=(
            CanonicalDocumentInput(
                canonical_locator="https://example.test/world",
                title="World",
                mime_type="text/markdown",
                blocks=(
                    CanonicalBlockInput(
                        structural_path="paragraph:0",
                        block_type="paragraph",
                        ordinal=0,
                        text_content="Evidence-backed canonical interpretation.",
                    ),
                ),
            ),
        ),
    )


def _seed(
    tmp_path: Path,
    *,
    owner_type: str = "system",
    owner_id: str = "system",
) -> tuple[
    Database,
    _PrivateStorage,
    KnowledgeFabricRepository,
    KnowledgeFabricInterpretationRepository,
    str,
    str,
]:
    database = Database(f"sqlite:///{tmp_path / 'phase4.db'}")
    database.initialize()
    storage = _PrivateStorage(values={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    if owner_type == "system":
        corpus = fabric.create_system_global_corpus(
            name="World",
            description="",
            default_authority_profile="standard",
            status="active",
        )
    else:
        corpus = KnowledgeCorpusRecord(
            id="user-corpus",
            name="User World",
            owner_type=owner_type,
            owner_id=owner_id,
            visibility="private",
            default_authority_profile="standard",
            status="active",
        )
        with database.session() as session:
            session.add(corpus)
            session.commit()
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="manual_text",
        locator="https://example.test/world",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    service = KnowledgeFabricIngestionService(
        content,
        storage,
        object_key_prefix="knowledge-fabric",
    )
    version = service.ingest_snapshot(_snapshot(source.id))
    evidence = content.list_evidence_units(version.id)[0]
    return (
        database,
        storage,
        fabric,
        KnowledgeFabricInterpretationRepository(database),
        corpus.id,
        evidence.id,
    )


def test_canonical_assertion_event_and_graph_never_create_automatic_chat_beliefs(
    tmp_path: Path,
) -> None:
    database, _, _, interpretations, corpus_id, evidence_id = _seed(tmp_path)
    entity = interpretations.create_canonical_entity(
        corpus_id=corpus_id,
        entity_type="character",
        canonical_name="Klee",
        aliases=("Spark Knight",),
    )
    assert (
        interpretations.create_canonical_entity(
            corpus_id=corpus_id,
            entity_type="character",
            canonical_name="  KLEE  ",
        ).id
        == entity.id
    )

    supported = interpretations.create_assertion(
        corpus_id=corpus_id,
        subject_entity_id=entity.id,
        predicate="has_title",
        object_value="Spark Knight",
        evidence_unit_ids=(evidence_id,),
        confidence=0.9,
    )
    disputed = interpretations.create_assertion(
        corpus_id=corpus_id,
        subject_entity_id=entity.id,
        predicate="has_title",
        object_value="Knight of Favonius",
        evidence_unit_ids=(evidence_id,),
        confidence=0.4,
        status="disputed",
    )
    event = interpretations.create_world_event(
        corpus_id=corpus_id,
        event_type="story_event",
        title="Festival",
        participants=((entity.id, "participant"),),
        evidence_unit_ids=(evidence_id,),
        valid_from=datetime(2026, 1, 1, tzinfo=UTC),
    )
    graph = interpretations.add_graph_relation(
        corpus_id=corpus_id,
        source_ref_type="canonical_entity",
        source_ref_id=entity.id,
        relation_type="PARTICIPATED_IN",
        target_ref_type="world_event",
        target_ref_id=event.id,
        evidence_unit_ids=(evidence_id,),
        confidence=0.9,
    )
    assert (
        interpretations.add_graph_relation(
            corpus_id=corpus_id,
            source_ref_type="canonical_entity",
            source_ref_id=entity.id,
            relation_type="PARTICIPATED_IN",
            target_ref_type="world_event",
            target_ref_id=event.id,
            evidence_unit_ids=(evidence_id,),
            confidence=0.9,
        ).id
        == graph.id
    )
    assert {supported.status, disputed.status} == {"active", "disputed"}
    assert (
        len(
            interpretations.list_interpretation_evidence(
                interpretation_type="assertion",
                interpretation_id=supported.id,
            )
        )
        == 1
    )
    assert (
        len(
            interpretations.list_interpretation_evidence(
                interpretation_type="world_event",
                interpretation_id=event.id,
            )
        )
        == 1
    )
    from sqlalchemy import inspect

    assert "beliefs_v3" not in inspect(database.engine).get_table_names()
    assert "conversation_episodes_v3" not in inspect(database.engine).get_table_names()


def test_interpretation_lifecycle_removes_only_user_corpus_state(
    tmp_path: Path,
) -> None:
    database, storage, fabric, interpretations, corpus_id, evidence_id = _seed(
        tmp_path,
        owner_type="user",
        owner_id="user-1",
    )
    entity = interpretations.create_canonical_entity(
        corpus_id=corpus_id,
        entity_type="character",
        canonical_name="Klee",
    )
    interpretations.create_assertion(
        corpus_id=corpus_id,
        subject_entity_id=entity.id,
        predicate="has_title",
        object_value="Spark Knight",
        evidence_unit_ids=(evidence_id,),
    )

    counts = fabric.delete_owner("user-1")

    assert counts["knowledge_fabric_canonical_entities"] == 1
    assert counts["knowledge_fabric_extracted_assertions"] == 1
    assert not storage.values
    with database.session() as session:
        assert session.get(KnowledgeCanonicalEntityRecord, entity.id) is None
