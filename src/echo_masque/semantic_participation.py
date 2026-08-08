"""Semantic Character Card relevance for Smart Participation V3."""

from __future__ import annotations

import hashlib
import logging
import math
import struct
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Protocol

from echo_masque.config import Settings
from echo_masque.persistence.models import CharacterCardRecord
from echo_masque.persistence.repository import Repository
from echo_masque.persistence.smart_participation_repository import (
    SmartParticipationRepository,
    decode_strings,
)

logger = logging.getLogger(__name__)


class SemanticEmbeddingUnavailable(RuntimeError):
    """Raised when semantic embedding cannot be produced without breaking runtime."""


class SemanticEncoder(Protocol):
    model_name: str
    dimension: int

    def embed_passage(self, text: str) -> list[float]: ...

    def embed_query(self, text: str) -> list[float]: ...


class FastEmbedSemanticEncoder:
    """Lazy FastEmbed wrapper for multilingual E5 without a PyTorch runtime."""

    def __init__(
        self,
        *,
        model_name: str,
        model_file: str,
        cache_dir: str,
        dimension: int = 384,
    ) -> None:
        self.model_name = model_name
        self.model_file = model_file
        self.cache_dir = cache_dir
        self.dimension = dimension
        self._model: object | None = None
        self._lock = Lock()

    def _load_model(self) -> object:
        if self._model is not None:
            return self._model
        with self._lock:
            if self._model is not None:
                return self._model
            try:
                from fastembed import TextEmbedding  # type: ignore[import-untyped]
                from fastembed.common.model_description import (  # type: ignore[import-untyped]
                    ModelSource,
                    PoolingType,
                )

                Path(self.cache_dir).mkdir(parents=True, exist_ok=True)
                supported = {
                    item["model"]
                    for item in TextEmbedding.list_supported_models()
                    if isinstance(item, dict) and isinstance(item.get("model"), str)
                }
                if self.model_name not in supported:
                    TextEmbedding.add_custom_model(
                        model=self.model_name,
                        pooling=PoolingType.MEAN,
                        normalization=True,
                        sources=ModelSource(hf=self.model_name),
                        dim=self.dimension,
                        model_file=self.model_file,
                    )
                self._model = TextEmbedding(
                    model_name=self.model_name,
                    cache_dir=self.cache_dir,
                )
                return self._model
            except Exception as exc:  # pragma: no cover - environment/network dependent
                raise SemanticEmbeddingUnavailable(
                    f"Semantic embedding model is unavailable: {exc}"
                ) from exc

    def _embed(self, text: str, prefix: str) -> list[float]:
        model = self._load_model()
        try:
            embed = getattr(model, "embed")  # noqa: B009
            values = list(embed([f"{prefix}: {text}"]))
            if not values:
                raise ValueError("Embedding model returned no vector.")
            vector = [float(value) for value in values[0]]
        except Exception as exc:  # pragma: no cover - backend dependent
            raise SemanticEmbeddingUnavailable(f"Embedding inference failed: {exc}") from exc
        if len(vector) != self.dimension:
            raise SemanticEmbeddingUnavailable(
                f"Embedding dimension mismatch: expected {self.dimension}, got {len(vector)}."
            )
        return vector

    def embed_passage(self, text: str) -> list[float]:
        return self._embed(text, "passage")

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text, "query")


@dataclass(frozen=True)
class SemanticParticipationScore:
    deployment_id: str
    character_card_id: str
    relevance: float
    profile_ready: bool


def _serialize_vector(vector: Sequence[float]) -> bytes:
    if not vector:
        raise ValueError("Embedding vector cannot be empty.")
    return struct.pack(f"<{len(vector)}f", *vector)


def _deserialize_vector(value: bytes, dimension: int) -> list[float]:
    expected = dimension * 4
    if len(value) != expected:
        raise ValueError(
            "Stored embedding has "
            f"{len(value)} bytes; expected {expected} for {dimension} dimensions."
        )
    return list(struct.unpack(f"<{dimension}f", value))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        return 0.0
    dot = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return max(-1.0, min(1.0, dot / (left_norm * right_norm)))


def _compact(value: str | None) -> str:
    return " ".join((value or "").split())


def participation_semantic_text(card: CharacterCardRecord) -> str:
    """Build stable participation-focused text without an additional LLM call."""

    sections: list[tuple[str, str | None]] = [
        ("Character", card.display_name),
        ("Role", card.subtitle),
        ("Type", card.subject_type),
        ("Persona", card.persona_summary),
        ("Traits", ", ".join(decode_strings(card.traits_json))),
        ("Tags", ", ".join(decode_strings(card.tags_json))),
        ("Tone", card.expected_tone),
    ]
    lines = [f"{label}: {_compact(value)}" for label, value in sections if _compact(value)]
    return "\n".join(lines)


class CharacterParticipationSemanticService:
    """Create cached card embeddings and score current-message semantic relevance."""

    def __init__(
        self,
        repository: Repository,
        smart_repository: SmartParticipationRepository,
        settings: Settings,
        *,
        encoder: SemanticEncoder | None = None,
        encoder_factory: Callable[[], SemanticEncoder] | None = None,
    ) -> None:
        self.repository = repository
        self.smart_repository = smart_repository
        self.settings = settings
        self._encoder = encoder
        self._encoder_factory = encoder_factory
        self._encoder_lock = Lock()

    @property
    def enabled(self) -> bool:
        return self.settings.semantic_participation_enabled

    def _get_encoder(self) -> SemanticEncoder:
        if not self.enabled:
            raise SemanticEmbeddingUnavailable("Semantic participation is disabled.")
        if self._encoder is not None:
            return self._encoder
        with self._encoder_lock:
            if self._encoder is not None:
                return self._encoder
            if self._encoder_factory is not None:
                self._encoder = self._encoder_factory()
            else:
                self._encoder = FastEmbedSemanticEncoder(
                    model_name=self.settings.semantic_embedding_model,
                    model_file=self.settings.semantic_embedding_model_file,
                    cache_dir=self.settings.semantic_embedding_cache_dir,
                    dimension=self.settings.semantic_embedding_dimension,
                )
            return self._encoder

    def _source_hash(self, semantic_text: str, encoder: SemanticEncoder) -> str:
        payload = "\n".join([encoder.model_name, str(encoder.dimension), semantic_text])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def ensure_profile(
        self,
        *,
        owner_id: str,
        character_card_id: str,
    ) -> tuple[list[float], bool]:
        card = self.repository.get_character_card(character_card_id, owner_id)
        if card is None:
            raise KeyError("character")
        encoder = self._get_encoder()
        semantic_text = participation_semantic_text(card)
        if not semantic_text:
            raise SemanticEmbeddingUnavailable("Character Card has no semantic participation text.")
        source_hash = self._source_hash(semantic_text, encoder)
        existing = self.smart_repository.get_semantic_profile(character_card_id, owner_id)
        if (
            existing is not None
            and existing.source_hash == source_hash
            and existing.model_name == encoder.model_name
            and existing.dimension == encoder.dimension
        ):
            try:
                return _deserialize_vector(existing.embedding_blob, existing.dimension), False
            except ValueError:
                logger.warning(
                    "Stored Smart Participation embedding is invalid; rebuilding character=%s",
                    character_card_id,
                )

        vector = encoder.embed_passage(semantic_text)
        self.smart_repository.upsert_semantic_profile(
            character_card_id=character_card_id,
            owner_id=owner_id,
            source_hash=source_hash,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            embedding_blob=_serialize_vector(vector),
        )
        return vector, True

    def refresh_character(self, *, owner_id: str, character_card_id: str) -> bool:
        """Refresh one card after save; failures are intentionally fail-open."""

        if not self.enabled:
            return False
        try:
            _, rebuilt = self.ensure_profile(
                owner_id=owner_id,
                character_card_id=character_card_id,
            )
            return rebuilt
        except (KeyError, SemanticEmbeddingUnavailable, ValueError) as exc:
            logger.warning(
                "Semantic participation profile refresh skipped character=%s error=%s",
                character_card_id,
                exc,
            )
            return False

    def score(
        self,
        *,
        message: str,
        deployments: Sequence[tuple[str, str, str]],
    ) -> tuple[str, int, list[SemanticParticipationScore]]:
        """Score (deployment_id, owner_id, character_card_id) tuples with one query embedding."""

        text = _compact(message)
        if not text:
            return "", 0, []
        encoder = self._get_encoder()
        query_vector = encoder.embed_query(text)
        results: list[SemanticParticipationScore] = []
        for deployment_id, owner_id, character_card_id in deployments:
            try:
                profile_vector, _ = self.ensure_profile(
                    owner_id=owner_id,
                    character_card_id=character_card_id,
                )
                relevance = _cosine(query_vector, profile_vector)
                results.append(
                    SemanticParticipationScore(
                        deployment_id=deployment_id,
                        character_card_id=character_card_id,
                        relevance=round(relevance, 6),
                        profile_ready=True,
                    )
                )
            except (KeyError, SemanticEmbeddingUnavailable, ValueError) as exc:
                logger.warning(
                    "Semantic participation candidate skipped deployment=%s error=%s",
                    deployment_id,
                    exc,
                )
                results.append(
                    SemanticParticipationScore(
                        deployment_id=deployment_id,
                        character_card_id=character_card_id,
                        relevance=0.0,
                        profile_ready=False,
                    )
                )
        return encoder.model_name, encoder.dimension, results

    def replace_encoder_for_test(self, encoder: SemanticEncoder) -> None:
        """Install a deterministic encoder in tests without loading the production model."""

        self._encoder = encoder
