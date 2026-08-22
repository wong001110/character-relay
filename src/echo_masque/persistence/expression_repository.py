"""Persistence and retrieval operations for Discord Server expressions."""

from __future__ import annotations

import json
from typing import cast
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from echo_masque.expression_retrieval import (
    ExpressionCandidate,
    ExpressionResource,
    rank_expression_resources,
    semantic_tokens,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    DiscordServerProfileRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.expression_models import (
    DiscordExpressionNodeRecord,
    DiscordExpressionRunRecord,
    DiscordExpressionSemanticRecord,
)
from echo_masque.persistence.interaction_models import DiscordStickerSemanticRecord
from echo_masque.persistence.models import utcnow


def _encode(values: list[str]) -> str:
    return json.dumps(list(dict.fromkeys(value.strip() for value in values if value.strip())))


def _decode(value: str) -> list[str]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(decoded, list):
        return []
    return [item.strip() for item in decoded if isinstance(item, str) and item.strip()]


def _object(value: str) -> dict[str, object]:
    try:
        decoded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return cast(dict[str, object], decoded) if isinstance(decoded, dict) else {}


def expression_key(resource_type: str, resource_id: str) -> str:
    return f"{resource_type}:{resource_id}"


def _default_actions(resource_type: str) -> list[str]:
    return ["inline", "reaction"] if resource_type == "emoji" else ["sticker"]


def _metadata_semantics(
    resource_type: str,
    name: str,
    description: str,
    tags: list[str],
) -> tuple[str, str, float]:
    details = [item for item in (description.strip(), ", ".join(tags)) if item]
    noun = "Emoji" if resource_type == "emoji" else "Sticker"
    if details:
        return f"{noun} named {name}. {'; '.join(details)}.", "discord_metadata", 0.6
    return (
        f"{noun} named {name}; no confirmed meaning has been configured yet.",
        "discord_metadata",
        0.3,
    )


class ExpressionRepository:
    """Store expression dictionaries and durable decision workflow state."""

    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def tags(record: DiscordExpressionSemanticRecord) -> list[str]:
        return _decode(record.tags_json)

    @staticmethod
    def aliases(record: DiscordExpressionSemanticRecord) -> list[str]:
        return _decode(record.aliases_json)

    @staticmethod
    def situations(record: DiscordExpressionSemanticRecord) -> list[str]:
        return _decode(record.situations_json)

    @staticmethod
    def avoid_when(record: DiscordExpressionSemanticRecord) -> list[str]:
        return _decode(record.avoid_when_json)

    @staticmethod
    def allowed_actions(record: DiscordExpressionSemanticRecord) -> list[str]:
        return _decode(record.allowed_actions_json) or _default_actions(record.resource_type)

    @staticmethod
    def run_state(record: DiscordExpressionRunRecord) -> dict[str, object]:
        return _object(record.state_json)

    @staticmethod
    def node_input(record: DiscordExpressionNodeRecord) -> dict[str, object]:
        return _object(record.input_summary_json)

    @staticmethod
    def node_output(record: DiscordExpressionNodeRecord) -> dict[str, object]:
        return _object(record.output_summary_json)

    def _connection(self, session: Session, connection_id: str) -> PlatformConnectionRecord:
        connection = session.get(PlatformConnectionRecord, connection_id)
        if connection is None or connection.platform != "discord":
            raise KeyError("connection")
        return connection

    def _upsert_catalog_resource(
        self,
        session: Session,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        resource_type: str,
        resource_id: str,
        name: str,
        description: str,
        tags: list[str],
        format_type: str,
        asset_url: str,
        animated: bool,
        available: bool,
    ) -> DiscordExpressionSemanticRecord:
        record = session.scalar(
            select(DiscordExpressionSemanticRecord).where(
                DiscordExpressionSemanticRecord.owner_id == owner_id,
                DiscordExpressionSemanticRecord.connection_id == connection_id,
                DiscordExpressionSemanticRecord.guild_id == guild_id,
                DiscordExpressionSemanticRecord.resource_type == resource_type,
                DiscordExpressionSemanticRecord.resource_id == resource_id,
            )
        )
        if record is None:
            record = DiscordExpressionSemanticRecord(
                id=str(uuid4()),
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                resource_type=resource_type,
                resource_id=resource_id,
                name=name,
                allowed_actions_json=_encode(_default_actions(resource_type)),
            )
            if resource_type == "sticker":
                legacy = session.scalar(
                    select(DiscordStickerSemanticRecord).where(
                        DiscordStickerSemanticRecord.owner_id == owner_id,
                        DiscordStickerSemanticRecord.connection_id == connection_id,
                        DiscordStickerSemanticRecord.guild_id == guild_id,
                        DiscordStickerSemanticRecord.sticker_id == resource_id,
                    )
                )
                if legacy is not None and legacy.semantic_description:
                    record.semantic_intent = legacy.semantic_intent
                    record.semantic_emotion = legacy.semantic_emotion
                    record.semantic_description = legacy.semantic_description
                    record.semantic_source = legacy.semantic_source
                    record.semantic_confidence = legacy.semantic_confidence
            session.add(record)
        record.name = name
        record.description = description
        record.tags_json = _encode(tags)
        record.format_type = format_type
        record.asset_url = asset_url
        record.animated = animated
        record.available = available
        record.last_seen_at = utcnow()
        if record.semantic_source != "manual":
            meaning, source, confidence = _metadata_semantics(
                resource_type,
                name,
                description,
                tags,
            )
            record.semantic_description = meaning
            record.semantic_source = source
            record.semantic_confidence = confidence
        return record

    def sync_server_resources(
        self,
        *,
        connection_id: str,
        guild_id: str,
        emojis: list[dict[str, object]] | None,
        stickers: list[dict[str, object]] | None,
    ) -> dict[str, int]:
        with self.database.session() as session:
            connection = self._connection(session, connection_id)
            owner_ids = {
                connection.owner_id,
                *session.scalars(
                    select(DiscordServerProfileRecord.owner_id).where(
                        DiscordServerProfileRecord.connection_id == connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                    )
                ),
            }
            counts = {"emoji": 0, "sticker": 0}
            seen: dict[str, set[str]] = {"emoji": set(), "sticker": set()}
            for resource_type, items in (("emoji", emojis), ("sticker", stickers)):
                if items is None:
                    continue
                for item in items:
                    raw_resource_id = (
                        item.get("emoji_id")
                        if resource_type == "emoji"
                        else item.get("sticker_id")
                    )
                    resource_id = str(raw_resource_id or "").strip()
                    name = str(item.get("name") or resource_type.title()).strip()
                    if not resource_id or not name:
                        continue
                    raw_tags = item.get("tags")
                    tags = (
                        [str(value).strip() for value in raw_tags if str(value).strip()]
                        if isinstance(raw_tags, list)
                        else []
                    )
                    for owner_id in owner_ids:
                        self._upsert_catalog_resource(
                            session,
                            owner_id=owner_id,
                            connection_id=connection_id,
                            guild_id=guild_id,
                            resource_type=resource_type,
                            resource_id=resource_id,
                            name=name,
                            description=str(item.get("description") or ""),
                            tags=tags,
                            format_type=str(item.get("format_type") or resource_type),
                            asset_url=str(item.get("asset_url") or ""),
                            animated=bool(item.get("animated", False)),
                            available=bool(item.get("available", True)),
                        )
                    seen[resource_type].add(resource_id)
                    counts[resource_type] += 1
            for owner_id in owner_ids:
                for resource_type, resource_ids in seen.items():
                    if (resource_type == "emoji" and emojis is None) or (
                        resource_type == "sticker" and stickers is None
                    ):
                        continue
                    records = list(
                        session.scalars(
                            select(DiscordExpressionSemanticRecord).where(
                                DiscordExpressionSemanticRecord.owner_id == owner_id,
                                DiscordExpressionSemanticRecord.connection_id == connection_id,
                                DiscordExpressionSemanticRecord.guild_id == guild_id,
                                DiscordExpressionSemanticRecord.resource_type == resource_type,
                            )
                        )
                    )
                    for record in records:
                        if record.resource_id not in resource_ids:
                            record.available = False
            session.commit()
            return counts

    def clone_server_resources(
        self,
        *,
        source_owner_id: str,
        target_owner_id: str,
        connection_id: str,
        guild_id: str,
    ) -> int:
        """Seed one new claim with the current canonical resource metadata."""

        with self.database.session() as session:
            source = list(
                session.scalars(
                    select(DiscordExpressionSemanticRecord).where(
                        DiscordExpressionSemanticRecord.owner_id == source_owner_id,
                        DiscordExpressionSemanticRecord.connection_id == connection_id,
                        DiscordExpressionSemanticRecord.guild_id == guild_id,
                    )
                )
            )
            created = 0
            for item in source:
                existing = session.scalar(
                    select(DiscordExpressionSemanticRecord.id).where(
                        DiscordExpressionSemanticRecord.owner_id == target_owner_id,
                        DiscordExpressionSemanticRecord.connection_id == connection_id,
                        DiscordExpressionSemanticRecord.guild_id == guild_id,
                        DiscordExpressionSemanticRecord.resource_type == item.resource_type,
                        DiscordExpressionSemanticRecord.resource_id == item.resource_id,
                    )
                )
                if existing is not None:
                    continue
                session.add(
                    DiscordExpressionSemanticRecord(
                        id=str(uuid4()),
                        owner_id=target_owner_id,
                        connection_id=connection_id,
                        guild_id=guild_id,
                        resource_type=item.resource_type,
                        resource_id=item.resource_id,
                        name=item.name,
                        description=item.description,
                        tags_json=item.tags_json,
                        format_type=item.format_type,
                        asset_url=item.asset_url,
                        animated=item.animated,
                        available=item.available,
                        enabled=item.enabled,
                        semantic_intent=item.semantic_intent,
                        semantic_emotion=item.semantic_emotion,
                        semantic_description=item.semantic_description,
                        aliases_json=item.aliases_json,
                        situations_json=item.situations_json,
                        avoid_when_json=item.avoid_when_json,
                        allowed_actions_json=item.allowed_actions_json,
                        semantic_source=item.semantic_source,
                        semantic_confidence=item.semantic_confidence,
                        last_seen_at=item.last_seen_at,
                    )
                )
                created += 1
            session.commit()
            return created

    def list_resources(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
        guild_id: str | None = None,
        resource_type: str | None = None,
    ) -> list[DiscordExpressionSemanticRecord]:
        with self.database.session() as session:
            conditions = [DiscordExpressionSemanticRecord.owner_id == owner_id]
            if connection_id:
                conditions.append(DiscordExpressionSemanticRecord.connection_id == connection_id)
            if guild_id:
                conditions.append(DiscordExpressionSemanticRecord.guild_id == guild_id)
            if resource_type:
                conditions.append(DiscordExpressionSemanticRecord.resource_type == resource_type)
            return list(
                session.scalars(
                    select(DiscordExpressionSemanticRecord)
                    .where(*conditions)
                    .order_by(
                        DiscordExpressionSemanticRecord.resource_type,
                        DiscordExpressionSemanticRecord.available.desc(),
                        DiscordExpressionSemanticRecord.name,
                    )
                )
            )

    def upsert_manual_resource(
        self,
        *,
        owner_id: str,
        connection_id: str,
        guild_id: str,
        resource_type: str,
        resource_id: str,
        name: str,
        description: str,
        tags: list[str],
        format_type: str,
        asset_url: str,
        animated: bool,
        available: bool,
        enabled: bool,
        semantic_intent: str,
        semantic_emotion: str,
        semantic_description: str,
        aliases: list[str],
        situations: list[str],
        avoid_when: list[str],
        allowed_actions: list[str],
    ) -> DiscordExpressionSemanticRecord:
        with self.database.session() as session:
            connection = self._connection(session, connection_id)
            if connection.owner_id != owner_id:
                claim = session.scalar(
                    select(DiscordServerProfileRecord.id).where(
                        DiscordServerProfileRecord.owner_id == owner_id,
                        DiscordServerProfileRecord.connection_id == connection_id,
                        DiscordServerProfileRecord.guild_id == guild_id,
                    )
                )
                if claim is None:
                    raise KeyError("connection")
            record = self._upsert_catalog_resource(
                session,
                owner_id=owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                resource_type=resource_type,
                resource_id=resource_id,
                name=name,
                description=description,
                tags=tags,
                format_type=format_type,
                asset_url=asset_url,
                animated=animated,
                available=available,
            )
            record.enabled = enabled
            record.semantic_intent = semantic_intent
            record.semantic_emotion = semantic_emotion
            record.semantic_description = semantic_description
            record.aliases_json = _encode(aliases)
            record.situations_json = _encode(situations)
            record.avoid_when_json = _encode(avoid_when)
            record.allowed_actions_json = _encode(allowed_actions)
            record.semantic_source = "manual"
            record.semantic_confidence = 1.0
            session.commit()
            session.refresh(record)
            return record

    def resolve_resource(
        self,
        *,
        connection_id: str,
        guild_id: str,
        resource_type: str,
        resource_id: str,
        name: str,
        animated: bool = False,
        available: bool = True,
        asset_url: str = "",
    ) -> DiscordExpressionSemanticRecord:
        with self.database.session() as session:
            connection = self._connection(session, connection_id)
            record = self._upsert_catalog_resource(
                session,
                owner_id=connection.owner_id,
                connection_id=connection_id,
                guild_id=guild_id,
                resource_type=resource_type,
                resource_id=resource_id,
                name=name,
                description="",
                tags=[],
                format_type=resource_type,
                asset_url=asset_url,
                animated=animated,
                available=available,
            )
            session.commit()
            session.refresh(record)
            return record

    def _resource(self, record: DiscordExpressionSemanticRecord) -> ExpressionResource:
        return ExpressionResource(
            key=expression_key(record.resource_type, record.resource_id),
            resource_type=record.resource_type,
            resource_id=record.resource_id,
            name=record.name,
            description=record.description,
            semantic_intent=record.semantic_intent,
            semantic_emotion=record.semantic_emotion,
            semantic_description=record.semantic_description,
            aliases=tuple(self.aliases(record)),
            tags=tuple(self.tags(record)),
            situations=tuple(self.situations(record)),
            avoid_when=tuple(self.avoid_when(record)),
            allowed_actions=tuple(self.allowed_actions(record)),
            animated=record.animated,
            available=record.available,
            enabled=record.enabled,
            semantic_confidence=record.semantic_confidence,
            asset_url=record.asset_url,
            format_type=record.format_type,
            semantic_source=record.semantic_source,
        )

    @staticmethod
    def candidate_dict(candidate: ExpressionCandidate) -> dict[str, object]:
        resource = candidate.resource
        return {
            "resource_key": resource.key,
            "resource_type": resource.resource_type,
            "resource_id": resource.resource_id,
            "name": resource.name,
            "animated": resource.animated,
            "available": resource.available,
            "enabled": resource.enabled,
            "allowed_actions": list(resource.allowed_actions),
            "semantic_intent": resource.semantic_intent,
            "semantic_emotion": resource.semantic_emotion,
            "semantic_description": resource.semantic_description,
            "semantic_source": resource.semantic_source,
            "semantic_confidence": resource.semantic_confidence,
            "asset_url": resource.asset_url,
            "format_type": resource.format_type,
            "score": candidate.score,
            "signals": candidate.signals,
        }

    def _append_node(
        self,
        session: Session,
        *,
        run: DiscordExpressionRunRecord,
        node_name: str,
        status: str,
        attempt: int,
        input_summary: dict[str, object],
        output_summary: dict[str, object],
        error: str = "",
    ) -> DiscordExpressionNodeRecord:
        current = session.scalar(
            select(func.max(DiscordExpressionNodeRecord.node_index)).where(
                DiscordExpressionNodeRecord.run_id == run.id
            )
        )
        node = DiscordExpressionNodeRecord(
            id=str(uuid4()),
            run_id=run.id,
            node_name=node_name,
            node_index=int(current or 0) + 1,
            attempt=attempt,
            status=status,
            input_summary_json=json.dumps(input_summary),
            output_summary_json=json.dumps(output_summary),
            error=error[:2000],
            completed_at=utcnow() if status in {"completed", "failed", "skipped"} else None,
        )
        session.add(node)
        run.current_node = node_name
        run.updated_at = utcnow()
        return node

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
            ranked = rank_expression_resources(
                [self._resource(item) for item in resources],
                query=query,
                allowed_actions=set(allowed_actions),
                recent_resource_keys=recent_keys,
                excluded_resource_keys=set(excluded_resource_keys),
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
                    "retrieval_backend": "hybrid_sparse_v1",
                    "top_k": top_k,
                },
                output_summary={
                    "candidate_count": len(candidates),
                    "candidate_keys": [str(item["resource_key"]) for item in candidates],
                    "candidate_scores": [item["score"] for item in candidates],
                },
            )
            state = self.run_state(run)
            state.update(
                {
                    "version": 1,
                    "retrieval_backend": "hybrid_sparse_v1",
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

    def record_node(
        self,
        *,
        connection_id: str,
        run_id: str,
        node_name: str,
        status: str,
        input_summary: dict[str, object],
        output_summary: dict[str, object],
        error: str,
        selected_action: str | None = None,
        selected_resource_key: str | None = None,
        final_status: str | None = None,
    ) -> DiscordExpressionRunRecord:
        with self.database.session() as session:
            run = session.get(DiscordExpressionRunRecord, run_id)
            if run is None or run.connection_id != connection_id:
                raise KeyError("run")
            self._append_node(
                session,
                run=run,
                node_name=node_name,
                status=status,
                attempt=run.attempt_count,
                input_summary=input_summary,
                output_summary=output_summary,
                error=error,
            )
            state = self.run_state(run)
            state["last_node"] = {
                "name": node_name,
                "status": status,
                "output": output_summary,
                "error": error[:2000],
            }
            if selected_action is not None:
                run.selected_action = selected_action
                state["selected_action"] = selected_action
            if selected_resource_key is not None:
                run.selected_resource_key = selected_resource_key
                state["selected_resource_key"] = selected_resource_key
            if error:
                run.last_error = error[:2000]
            if final_status is not None:
                run.status = final_status
                if final_status in {"completed", "failed", "skipped"}:
                    run.completed_at = utcnow()
            run.state_json = json.dumps(state)
            session.commit()
            session.refresh(run)
            return run

    def list_runs(
        self,
        owner_id: str,
        *,
        connection_id: str | None = None,
        guild_id: str | None = None,
        limit: int = 50,
    ) -> list[DiscordExpressionRunRecord]:
        with self.database.session() as session:
            conditions = [DiscordExpressionRunRecord.owner_id == owner_id]
            if connection_id:
                conditions.append(DiscordExpressionRunRecord.connection_id == connection_id)
            if guild_id:
                conditions.append(DiscordExpressionRunRecord.guild_id == guild_id)
            return list(
                session.scalars(
                    select(DiscordExpressionRunRecord)
                    .where(*conditions)
                    .order_by(DiscordExpressionRunRecord.updated_at.desc())
                    .limit(max(1, min(limit, 200)))
                )
            )

    def get_run(
        self,
        run_id: str,
        owner_id: str,
    ) -> DiscordExpressionRunRecord | None:
        with self.database.session() as session:
            run = session.get(DiscordExpressionRunRecord, run_id)
            if run is None or run.owner_id != owner_id:
                return None
            return run

    def list_nodes(self, run_id: str, owner_id: str) -> list[DiscordExpressionNodeRecord]:
        with self.database.session() as session:
            run = session.get(DiscordExpressionRunRecord, run_id)
            if run is None or run.owner_id != owner_id:
                return []
            return list(
                session.scalars(
                    select(DiscordExpressionNodeRecord)
                    .where(DiscordExpressionNodeRecord.run_id == run_id)
                    .order_by(DiscordExpressionNodeRecord.node_index)
                )
            )

    def delete_owner(self, owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            run_ids = list(
                session.scalars(
                    select(DiscordExpressionRunRecord.id).where(
                        DiscordExpressionRunRecord.owner_id == owner_id
                    )
                )
            )
            nodes = 0
            if run_ids:
                result = session.execute(
                    delete(DiscordExpressionNodeRecord).where(
                        DiscordExpressionNodeRecord.run_id.in_(run_ids)
                    )
                )
                nodes = int(getattr(result, "rowcount", 0) or 0)
            runs = session.execute(
                delete(DiscordExpressionRunRecord).where(
                    DiscordExpressionRunRecord.owner_id == owner_id
                )
            )
            resources = session.execute(
                delete(DiscordExpressionSemanticRecord).where(
                    DiscordExpressionSemanticRecord.owner_id == owner_id
                )
            )
            session.commit()
        return {
            "discord_expression_nodes": nodes,
            "discord_expression_runs": int(getattr(runs, "rowcount", 0) or 0),
            "discord_expression_semantics": int(getattr(resources, "rowcount", 0) or 0),
        }

    def claim_owner(self, source_owner_id: str, target_owner_id: str) -> dict[str, int]:
        with self.database.session() as session:
            resources = session.execute(
                update(DiscordExpressionSemanticRecord)
                .where(DiscordExpressionSemanticRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            runs = session.execute(
                update(DiscordExpressionRunRecord)
                .where(DiscordExpressionRunRecord.owner_id == source_owner_id)
                .values(owner_id=target_owner_id)
            )
            session.commit()
        return {
            "discord_expression_semantics": int(getattr(resources, "rowcount", 0) or 0),
            "discord_expression_runs": int(getattr(runs, "rowcount", 0) or 0),
        }
