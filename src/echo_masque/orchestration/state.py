"""Shared graph state contracts for Character Relay orchestration."""

from __future__ import annotations

from typing import Literal, TypedDict

OrchestrationGraphName = Literal[
    "foundation",
    "condition_watch",
    "character_turn",
    "social_turn",
    "evaluation",
]
OrchestrationStatus = Literal["pending", "running", "completed", "failed"]
ContextStatus = Literal["not_started", "ready", "skipped", "failed"]
DeliveryStatus = Literal["not_started", "pending", "delivered", "skipped", "failed"]


class CharacterRuntimeState(TypedDict, total=False):
    """Portable orchestration state; business records remain authoritative elsewhere.

    Keep this state limited to workflow coordination and privacy-safe references. Repository
    objects, provider clients, credentials, raw retrieved knowledge, and full Tool results do
    not belong in graph state.
    """

    trace_id: str
    graph_run_id: str
    graph_name: OrchestrationGraphName
    orchestration_version: str
    status: OrchestrationStatus

    owner_id: str
    deployment_id: str
    platform: str
    connection_id: str
    guild_id: str
    channel_id: str
    thread_id: str

    selected_deployment_ids: tuple[str, ...]
    current_deployment_id: str

    context_status: ContextStatus
    rag_status: ContextStatus
    tool_rounds: int
    tool_result_count: int
    smart_output_status: ContextStatus

    invite_candidate_deployment_id: str
    delivery_status: DeliveryStatus
    errors: tuple[str, ...]


__all__ = [
    "CharacterRuntimeState",
    "ContextStatus",
    "DeliveryStatus",
    "OrchestrationGraphName",
    "OrchestrationStatus",
]
