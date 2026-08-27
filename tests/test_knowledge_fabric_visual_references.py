from __future__ import annotations

import asyncio
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from typing import cast

from sqlalchemy import select

from echo_masque.knowledge_fabric_ingestion import (
    KnowledgeFabricIngestionService,
    SourceSnapshotIngestionRequest,
)
from echo_masque.knowledge_fabric_visual_identity import KnowledgeFabricVisualIdentityResolver
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
    KnowledgeCanonicalDocumentRecord,
    KnowledgeObjectArtifactRecord,
)
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.knowledge_fabric_visual_reference_repository import (
    KnowledgeFabricVisualReferenceRepository,
)
from echo_masque.providers.openai_multimodal import (
    OpenAICompatibleMultimodalProvider,
    ReferenceImageComparison,
)


@dataclass
class _FabricPolicy:
    corpus: object
    allowed: bool

    def list_effective_corpora(self, server_scope_id: str) -> list[object]:
        del server_scope_id
        return [type("Effective", (), {"corpus": self.corpus})()]

    def character_corpus_is_admitted(
        self, *, deployment_id: str, character_card_id: str, corpus_id: str
    ) -> bool:
        del deployment_id, character_card_id, corpus_id
        return self.allowed


@dataclass
class _Storage:
    objects: dict[str, bytes]

    def put_private(
        self, *, object_key: str, content: bytes, content_type: str, metadata: Mapping[str, str]
    ) -> StoredKnowledgeObject:
        del metadata
        self.objects[object_key] = content
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


class _ComparisonProvider:
    def __init__(self, result: ReferenceImageComparison) -> None:
        self.result = result
        self.candidate_uri = ""
        self.reference_uris: tuple[str, ...] = ()

    async def compare_fictional_character_images(
        self,
        *,
        candidate_uri: str,
        reference_uris: tuple[str, ...],
    ) -> ReferenceImageComparison:
        self.candidate_uri = candidate_uri
        self.reference_uris = reference_uris
        return self.result


def test_visual_reference_is_corpus_bound_provenance_and_revocable(tmp_path: Path) -> None:
    database = Database(f"sqlite:///{tmp_path / 'visual.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Teyvat", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="manual_text",
        locator="https://example.test/amber",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    ingestion = KnowledgeFabricIngestionService(
        content,
        storage,
        object_key_prefix="knowledge",
    )
    version = ingestion.ingest_snapshot(
        SourceSnapshotIngestionRequest(
            source_id=source.id,
            version_key="amber-v1",
            idempotency_key="amber-v1",
            artifact_content=b"private portrait bytes",
            artifact_content_type="image/webp",
            published_at=datetime(2026, 8, 27, tzinfo=UTC),
            documents=(
                CanonicalDocumentInput(
                    canonical_locator="https://example.test/amber",
                    title="Amber",
                    mime_type="text/plain",
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="page:0",
                            block_type="page",
                            ordinal=0,
                            text_content="Amber is a Pyro archer.",
                        ),
                    ),
                ),
            ),
        )
    )
    evidence = content.list_evidence_units(version.id)[0]
    with database.session() as session:
        document = session.scalar(
            select(KnowledgeCanonicalDocumentRecord).where(
                KnowledgeCanonicalDocumentRecord.source_version_id == version.id
            )
        )
        artifact = session.scalar(
            select(KnowledgeObjectArtifactRecord).where(
                KnowledgeObjectArtifactRecord.source_id == source.id
            )
        )
    assert document is not None and artifact is not None
    asset = content.create_asset_reference(
        document_id=document.id,
        artifact_id=artifact.id,
        asset_type="image",
        structural_path="image:0",
    )
    entity = KnowledgeFabricInterpretationRepository(database).create_canonical_entity(
        corpus_id=corpus.id,
        entity_type="character",
        canonical_name="Amber",
        aliases=("安柏",),
    )
    references = KnowledgeFabricVisualReferenceRepository(database)
    reference = references.create(
        corpus_id=corpus.id,
        canonical_entity_id=entity.id,
        evidence_unit_id=evidence.id,
        asset_id=asset.id,
        descriptor={"hair": "brown", "outfit": "red"},
    )
    assert [item.id for item in references.list_active(corpus.id)] == [reference.id]
    resolver = KnowledgeFabricVisualIdentityResolver(
        fabric=_FabricPolicy(corpus=corpus, allowed=True),  # type: ignore[arg-type]
        references=references,
    )
    assert resolver.resolve(
        deployment_id="deployment",
        character_card_id="card",
        server_scope_id="scope",
        image_source_keys=(f"sha256:{artifact.content_sha256}",),
        caption="",
    ).status == "exact_reference"
    assert resolver.resolve(
        deployment_id="deployment",
        character_card_id="card",
        server_scope_id="scope",
        image_source_keys=(),
        caption="This is Amber",
    ).status == "captioned_reference"
    denied = KnowledgeFabricVisualIdentityResolver(
        fabric=_FabricPolicy(corpus=corpus, allowed=False),  # type: ignore[arg-type]
        references=references,
    )
    assert denied.resolve(
        deployment_id="deployment",
        character_card_id="card",
        server_scope_id="scope",
        image_source_keys=(f"sha256:{artifact.content_sha256}",),
        caption="Amber",
    ).status == "unresolved"
    assert references.revoke(reference.id) is True
    assert references.list_active(corpus.id) == []


def test_pairwise_visual_reference_requires_explicit_fictional_authorization(
    tmp_path: Path,
) -> None:
    database = Database(f"sqlite:///{tmp_path / 'pairwise-visual.db'}")
    database.initialize()
    storage = _Storage(objects={})
    fabric = KnowledgeFabricRepository(database, object_storage=storage)
    corpus = fabric.create_system_global_corpus(
        name="Teyvat", description="", default_authority_profile="standard", status="active"
    )
    source = fabric.create_source(
        corpus_id=corpus.id,
        source_type="manual_text",
        locator="https://example.test/amber",
        access_profile_json="{}",
        parser_profile_json="{}",
        sync_policy_json="{}",
        freshness_policy_json="{}",
        authority_profile="standard",
    )
    content = KnowledgeFabricContentRepository(database, object_storage=storage)
    version = KnowledgeFabricIngestionService(
        content, storage, object_key_prefix="knowledge"
    ).ingest_snapshot(
        SourceSnapshotIngestionRequest(
            source_id=source.id,
            version_key="amber-pairwise-v1",
            idempotency_key="amber-pairwise-v1",
            artifact_content=b"private amber reference",
            artifact_content_type="image/webp",
            published_at=datetime(2026, 8, 28, tzinfo=UTC),
            documents=(
                CanonicalDocumentInput(
                    canonical_locator="https://example.test/amber",
                    title="Amber",
                    mime_type="text/plain",
                    blocks=(
                        CanonicalBlockInput(
                            structural_path="page:0",
                            block_type="page",
                            ordinal=0,
                            text_content="Amber official reference.",
                        ),
                    ),
                ),
            ),
        )
    )
    evidence = content.list_evidence_units(version.id)[0]
    with database.session() as session:
        document = session.scalar(
            select(KnowledgeCanonicalDocumentRecord).where(
                KnowledgeCanonicalDocumentRecord.source_version_id == version.id
            )
        )
        artifact = session.scalar(
            select(KnowledgeObjectArtifactRecord).where(
                KnowledgeObjectArtifactRecord.source_id == source.id
            )
        )
    assert document is not None and artifact is not None
    asset = content.create_asset_reference(
        document_id=document.id,
        artifact_id=artifact.id,
        asset_type="image",
        structural_path="image:0",
    )
    entity = KnowledgeFabricInterpretationRepository(database).create_canonical_entity(
        corpus_id=corpus.id,
        entity_type="fictional_character",
        canonical_name="Amber",
    )
    references = KnowledgeFabricVisualReferenceRepository(database)
    references.create(
        corpus_id=corpus.id,
        canonical_entity_id=entity.id,
        evidence_unit_id=evidence.id,
        asset_id=asset.id,
        comparison_authorized=True,
    )
    provider = _ComparisonProvider(
        ReferenceImageComparison(matched_reference_index=0, confidence=0.97)
    )
    resolver = KnowledgeFabricVisualIdentityResolver(
        fabric=_FabricPolicy(corpus=corpus, allowed=True),  # type: ignore[arg-type]
        references=references,
        object_storage=storage,
    )
    resolution = asyncio.run(
        resolver.resolve_pairwise(
            deployment_id="deployment",
            character_card_id="card",
            server_scope_id="scope",
            candidate_uri="https://cdn.example.test/current.png",
            provider=cast(OpenAICompatibleMultimodalProvider, provider),
        )
    )
    assert resolution.status == "pairwise_reference"
    assert resolution.canonical_name == "Amber"
    assert provider.candidate_uri == "https://cdn.example.test/current.png"
    assert provider.reference_uris == ("data:image/webp;base64,cHJpdmF0ZSBhbWJlciByZWZlcmVuY2U=",)

    references.revoke(references.list_active(corpus.id)[0].id)
    assert asyncio.run(
        resolver.resolve_pairwise(
            deployment_id="deployment",
            character_card_id="card",
            server_scope_id="scope",
            candidate_uri="https://cdn.example.test/current.png",
            provider=cast(OpenAICompatibleMultimodalProvider, provider),
        )
    ).status == "unresolved"
