"""Fail-closed visual identity resolution for approved corpus references."""

from __future__ import annotations

import re
from base64 import b64encode
from dataclasses import dataclass
from typing import Literal

from echo_masque.knowledge_fabric_visual_reference_policy import (
    MAX_EXTERNAL_COMPARISON_REFERENCES,
    external_comparison_is_resolved,
)
from echo_masque.knowledge_object_storage import KnowledgeObjectStorage, ObjectStorageError
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.knowledge_fabric_visual_reference_repository import (
    KnowledgeFabricVisualReferenceRepository,
    VisualReferenceCandidate,
)
from echo_masque.providers.openai_multimodal import OpenAICompatibleMultimodalProvider

VisualIdentityStatus = Literal[
    "unresolved",
    "exact_reference",
    "captioned_reference",
    "pairwise_reference",
]
_PAIRWISE_CONTENT_TYPES = frozenset(
    {"image/png", "image/jpeg", "image/gif", "image/webp"}
)


@dataclass(frozen=True, slots=True)
class VisualIdentityResolution:
    status: VisualIdentityStatus
    canonical_name: str = ""
    corpus_id: str = ""


class KnowledgeFabricVisualIdentityResolver:
    """Resolve only an exact approved image or an explicit caption; never infer lookalikes."""

    def __init__(
        self,
        *,
        fabric: KnowledgeFabricRepository,
        references: KnowledgeFabricVisualReferenceRepository,
        object_storage: KnowledgeObjectStorage | None = None,
    ) -> None:
        self.fabric = fabric
        self.references = references
        self.object_storage = object_storage

    def resolve(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        server_scope_id: str,
        image_source_keys: tuple[str, ...],
        caption: str,
    ) -> VisualIdentityResolution:
        normalized_keys = frozenset(
            value.casefold().strip() for value in image_source_keys if value.strip()
        )
        for effective in self.fabric.list_effective_corpora(server_scope_id):
            corpus = effective.corpus
            if not self.fabric.character_corpus_is_admitted(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                corpus_id=corpus.id,
            ):
                continue
            candidates = self.references.list_active_candidates(corpus.id)
            exact = [
                item
                for item in candidates
                if f"sha256:{item.artifact_sha256}" in normalized_keys
            ]
            if len(exact) == 1:
                return self._resolution("exact_reference", exact[0])
            captioned = [item for item in candidates if self._caption_names(caption, item)]
            if len(captioned) == 1:
                return self._resolution("captioned_reference", captioned[0])
        return VisualIdentityResolution(status="unresolved")

    async def resolve_pairwise(
        self,
        *,
        deployment_id: str,
        character_card_id: str,
        server_scope_id: str,
        candidate_uri: str,
        provider: OpenAICompatibleMultimodalProvider,
    ) -> VisualIdentityResolution:
        """Compare only explicit fictional-character references, otherwise fail closed."""

        storage = self.object_storage
        if storage is None or not candidate_uri:
            return VisualIdentityResolution(status="unresolved")
        for effective in self.fabric.list_effective_corpora(server_scope_id):
            corpus = effective.corpus
            if not self.fabric.character_corpus_is_admitted(
                deployment_id=deployment_id,
                character_card_id=character_card_id,
                corpus_id=corpus.id,
            ):
                continue
            references = self.references.list_active_comparison_candidates(corpus.id)[
                :MAX_EXTERNAL_COMPARISON_REFERENCES
            ]
            reference_uris: list[str] = []
            admitted = []
            for reference in references:
                data_uri = self._private_image_data_uri(
                    storage=storage,
                    object_key=reference.object_key,
                    content_type=reference.content_type,
                )
                if data_uri is not None:
                    reference_uris.append(data_uri)
                    admitted.append(reference)
            if not admitted:
                continue
            try:
                match = await provider.compare_fictional_character_images(
                    candidate_uri=candidate_uri,
                    reference_uris=tuple(reference_uris),
                )
            except Exception:
                continue
            index = match.matched_reference_index
            if not external_comparison_is_resolved(
                matched_reference_index=index,
                reference_count=len(admitted),
                confidence=match.confidence,
            ):
                continue
            if index is None:
                continue
            reference = admitted[index]
            return VisualIdentityResolution(
                status="pairwise_reference",
                canonical_name=reference.canonical_name,
                corpus_id=reference.corpus_id,
            )
        return VisualIdentityResolution(status="unresolved")

    @staticmethod
    def _private_image_data_uri(
        *,
        storage: KnowledgeObjectStorage,
        object_key: str,
        content_type: str,
    ) -> str | None:
        normalized_type = content_type.split(";", 1)[0].strip().casefold()
        if normalized_type not in _PAIRWISE_CONTENT_TYPES:
            return None
        try:
            content = storage.get_private(object_key=object_key)
        except ObjectStorageError:
            return None
        if not content or len(content) > 8 * 1024 * 1024:
            return None
        return f"data:{normalized_type};base64,{b64encode(content).decode('ascii')}"

    @staticmethod
    def _caption_names(caption: str, item: VisualReferenceCandidate) -> bool:
        normalized = caption.casefold()
        for name in (item.canonical_name, *item.aliases):
            value = name.casefold().strip()
            if value and re.search(rf"(?<!\w){re.escape(value)}(?!\w)", normalized):
                return True
        return False

    @staticmethod
    def _resolution(
        status: Literal["exact_reference", "captioned_reference"],
        item: VisualReferenceCandidate,
    ) -> VisualIdentityResolution:
        return VisualIdentityResolution(
            status=status,
            canonical_name=item.canonical_name,
            corpus_id=item.corpus_id,
        )


__all__ = [
    "KnowledgeFabricVisualIdentityResolver",
    "VisualIdentityResolution",
    "VisualIdentityStatus",
]
