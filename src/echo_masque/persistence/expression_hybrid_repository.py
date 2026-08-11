"""Dense+sparse Expression Dictionary retrieval on top of the existing workflow repository."""

from __future__ import annotations

import json
from uuid import uuid4

from sqlalchemy import select

from echo_masque.config import Settings, get_settings
from echo_masque.expression_retrieval import (
    ExpressionResource,
    expression_semantic_text,
    rank_expression_resources,
    semantic_tokens,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.expression_models import (
    DiscordExpressionRunRecord,
    DiscordExpressionSemanticRecord,
)
from echo_masque.persistence.expression_repository import (
    ExpressionRepository as BaseExpressionRepository,
)
from echo_masque.persistence.semantic_vector_repository import SemanticVectorRepository
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
)
from echo_masque.semantic_participation import (
    _cosine as dense_cosine,
)

_EXPRESSION_VECTOR_NAMESPACE = "expression-resource"


class HybridExpressionRepository(BaseExpressionRepository):
    """Expression repository that reuses the shared E5 runtime for semantic retrieval."""

    def __init__(
        self,
        database: Database,
        *,
        settings: Settings | None = None,
        semantic_encoder: SemanticEncoder | None = None,
        semantic_enabled: bool | None = None,
    ) -> None:
        super().__init__(database)
        self._settings = settings or get_settings()
        self._semantic_encoder = semantic_encoder
        self._semantic_enabled = (
            semantic_enabled
            if semantic_enabled is not None
            else (
                self._settings.semantic_embedding_runtime_enabled
                and self._settings.expression_semantic_retrieval_enabled
            )
        )
        self._semantic_vectors = SemanticVectorRepository(database)

    def _encoder(self) -> SemanticEncoder:
        if self._semantic_encoder is None:
            if not self._semantic_enabled:
                raise SemanticEmbeddingUnavailable("Semantic Expression retrieval is disabled.")
            self._semantic_encoder = FastEmbedSemanticEncoder(
                model_name=self._settings.semantic_embedding_model,
                model_file=self._settings.semantic_embedding_model_file,
                cache_dir=self._settings.semantic_embedding_cache_dir,
                dimension=self._settings.semantic_embedding_dimension,
            )
        return self._semantic_encoder

    def _ensure_vector(
        self,
        *,
        owner_id: str,
        record: DiscordExpressionSemanticRecord,
        resource: ExpressionResource,
    ) -> list[float]:
        encoder = self._encoder()
        semantic_text = expression_semantic_text(resource)
        source_hash = self._semantic_vectors.source_hash(
            semantic_text,
            encoder.model_name,
            encoder.dimension,
        )
        cached = self._semantic_vectors.get(
            owner_id=owner_id,
            namespace=_EXPRESSION_VECTOR_NAMESPACE,
            resource_id=record.id,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            source_hash=source_hash,
        )
        if cached is not None:
            return cached
        vector = encoder.embed_passage(semantic_text)
        self._semantic_vectors.upsert(
            owner_id=owner_id,
            namespace=_EXPRESSION_VECTOR_NAMESPACE,
            resource_id=record.id,
            semantic_text=semantic_text,
            model_name=encoder.model_name,
            dimension=encoder.dimension,
            vector=vector,
        )
        return vector

    def _dense_scores(
        self,
        *,
        owner_id: str,
        records: list[DiscordExpressionSemanticRecord],
        query: str,
        allowed_actions: set[str],
        excluded_resource_keys: set[str],
    ) -> dict[str, float] | None:
        if not self._semantic_enabled or not query.strip():
            return None
        try:
            encoder = self._encoder()
            query_vector = encoder.embed_query(query)
        except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
            return None

        eligible: list[tuple[DiscordExpressionSemanticRecord, ExpressionResource]] = []
        for record in records:
            resource = self._resource(record)
            if not resource.enabled or not resource.available:
                continue
            if resource.key in excluded_resource_keys:
                continue
            if not allowed_actions.intersection(resource.allowed_actions):
                continue
            eligible.append((record, resource))
        if not eligible:
            return None

        scores: dict[str, float] = {}
        for record, resource in eligible:
            try:
                vector = self._ensure_vector(
                    owner_id=owner_id,
                    record=record,
                    resource=resource,
                )
            except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
                # Do not mix partially dense and sparse-only scores in one ranking pass.
                return None
            scores[resource.key] = dense_cosine(query_vector, vector)
        return scores

    def retrieve(
        self,
        *,
        connection_id: str,
        guild_id: str,
        channel_id: str,
        source_message_id: str,
        deployment_id: str,
        query: str,
        allowed_actions: list[str],
        excluded_resource_keys: list[str],
        top_k: int,
        run_id: str | None = None,
    ) -> tuple[DiscordExpressionRunRecord, list[dict[str, object]]]:
        with self.database.session() as session:
            connection = self._connection(session, connection_id)
            deployment = session.get(CharacterDeploymentRecord, deployment_id)
            if (
                deployment is None
                or deployment.connection_id != connection_id
                or deployment.owner_id != connection.owner_id
            ):
                raise KeyError("deployment")
            if run_id:
                run = session.get(DiscordExpressionRunRecord, run_id)
                if run is None or run.connection_id != connection_id:
                    raise KeyError("run")
                run.attempt_count += 1
            else:
                run = session.scalar(
                    select(DiscordExpressionRunRecord).where(
                        DiscordExpressionRunRecord.connection_id == connection_id,
                        DiscordExpressionRunRecord.source_message_id == source_message_id,
                        DiscordExpressionRunRecord.deployment_id == deployment_id,
                    )
                )
                if run is None:
                    run = DiscordExpressionRunRecord(
                        id=str(uuid4()),
                        owner_id=connection.owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        channel_id=channel_id,
                        source_message_id=source_message_id,
                        deployment_id=deployment_id,
                        character_card_id=deployment.character_card_id,
                    )
                    session.add(run)
                    session.flush()

            resources = list(
                session.scalars(
                    select(DiscordExpressionSemanticRecord).where(
                        DiscordExpressionSemanticRecord.owner_id == connection.owner_id,
                        DiscordExpressionSemanticRecord.connection_id == connection_id,
                        DiscordExpressionSemanticRecord.guild_id == guild_id,
                    )
                )
            )
            recent_keys = set(
                session.scalars(
                    select(DiscordExpressionRunRecord.selected_resource_key)
                    .where(
                        DiscordExpressionRunRecord.owner_id == connection.owner_id,
                        DiscordExpressionRunRecord.deployment_id == deployment_id,
                        DiscordExpressionRunRecord.selected_resource_key != "",
                        DiscordExpressionRunRecord.id != run.id,
                    )
                    .order_by(DiscordExpressionRunRecord.updated_at.desc())
                    .limit(5)
                )
            )
            query_tokens = semantic_tokens(query)
            allowed = set(allowed_actions)
            excluded = set(excluded_resource_keys)
            self._append_node(
                session,
                run=run,
                node_name="filter_resources",
                status="completed",
                attempt=run.attempt_count,
                input_summary={
                    "query_length": len(query),
                    "query_token_count": len(query_tokens),
                    "allowed_actions": allowed_actions,
                    "excluded_resource_keys": excluded_resource_keys,
                },
                output_summary={
                    "server_resource_count": len(resources),
                    "recent_resource_keys": sorted(recent_keys),
                },
            )

            dense_scores = self._dense_scores(
                owner_id=connection.owner_id,
                records=resources,
                query=query,
                allowed_actions=allowed,
                excluded_resource_keys=excluded,
            )
            backend = (
                "hybrid_dense_sparse_v2" if dense_scores is not None else "hybrid_sparse_v1"
            )
            ranked = rank_expression_resources(
                [self._resource(item) for item in resources],
                query=query,
                allowed_actions=allowed,
                recent_resource_keys=recent_keys,
                excluded_resource_keys=excluded,
                dense_scores=dense_scores,
                top_k=top_k,
            )
            candidates = [self.candidate_dict(item) for item in ranked]
            self._append_node(
                session,
                run=run,
                node_name="rank_candidates",
                status="completed",
                attempt=run.attempt_count,
                input_summary={
                    "retrieval_backend": backend,
                    "top_k": top_k,
                },
                output_summary={
                    "candidate_count": len(candidates),
                    "candidate_keys": [str(item["resource_key"]) for item in candidates],
                    "candidate_scores": [item["score"] for item in candidates],
                    "dense_scored_resource_count": len(dense_scores or {}),
                },
            )
            state = self.run_state(run)
            state.update(
                {
                    "version": 2 if dense_scores is not None else 1,
                    "retrieval_backend": backend,
                    "query_summary": {
                        "length": len(query),
                        "token_count": len(query_tokens),
                    },
                    "allowed_actions": allowed_actions,
                    "excluded_resource_keys": excluded_resource_keys,
                    "candidates": candidates,
                }
            )
            run.state_json = json.dumps(state)
            run.status = "running"
            session.commit()
            session.refresh(run)
            return run, candidates

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        counts = super().delete_owner(owner_id)
        self._semantic_vectors.delete_namespace(
            owner_id=owner_id,
            namespace=_EXPRESSION_VECTOR_NAMESPACE,
        )
        return counts

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        counts = super().claim_owner(source_owner_id, target_owner_id)
        # Claimed records retain IDs but change owner scope. Remove the old-owner cache and let
        # the target owner lazily hydrate equivalent vectors on first retrieval.
        self._semantic_vectors.delete_namespace(
            owner_id=source_owner_id,
            namespace=_EXPRESSION_VECTOR_NAMESPACE,
        )
        return counts
