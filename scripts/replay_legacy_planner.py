"""Offline adapter for the pre-refactor Planner. Never a production fallback.

Run against the pinned baseline checkout when the legacy modules are retired. Callers
supply actual captured candidate/Segment inputs and a real or explicitly fake semantic
service. This measures the Planner stage only, NOT Connector -> structure -> context.
A source link must come from the actual source-selection record, not an arbitrary
conversion of a Segment to its newest message. Missing links remain unknown.
"""

from __future__ import annotations

import hashlib
import inspect
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
)
from echo_masque.participation_planner_v3 import ParticipationPlannerV3
from echo_masque.persistence.conversation_structure_repository import ConversationSegmentView
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.room_routing_replay import ObservedChoice, Prediction, Usage


@dataclass(frozen=True, slots=True)
class LegacyObservation:
    prediction: Prediction
    planner_source_sha256: str
    comparison_scope: str = "planner_only"


def replay_planner(
    *,
    case_id: str,
    planner: ParticipationPlannerV3,
    payload: SmartParticipationResolveRequest,
    deployments: tuple[CharacterDeploymentRecord, ...],
    candidate_views: tuple[SmartParticipationResolveCandidateView, ...],
    segments: tuple[ConversationSegmentView, ...],
    actual_source_links: Mapping[str, str] | None = None,
    upstream_error: str | None = None,
    usage: Usage | None = None,
) -> LegacyObservation:
    source = inspect.getsourcefile(ParticipationPlannerV3)
    if source is None:
        raise ValueError("Cannot identify the actual legacy Planner source.")
    source_hash = hashlib.sha256(Path(source).read_bytes()).hexdigest()
    if upstream_error:
        return LegacyObservation(
            Prediction(
                case_id=case_id, outcome="error", reason=upstream_error, usage=usage or Usage()
            ),
            source_hash,
        )
    started = time.perf_counter()
    plan = planner.plan(
        payload=payload, deployments=deployments, candidate_views=candidate_views, segments=segments
    )
    observation_usage = usage or Usage(latency_ms=(time.perf_counter() - started) * 1000)
    if not plan.grounding.can_reply:
        return LegacyObservation(
            Prediction(
                case_id=case_id, outcome="blocked", reason=plan.reason, usage=observation_usage
            ),
            source_hash,
        )
    links = actual_source_links or {}
    segment_by_id = {s.id: s for s in segments}
    choices = []
    for speaker in plan.speakers:
        target = links.get(speaker.deployment_id)
        segment = segment_by_id.get(speaker.segment_id)
        if target is not None and (segment is None or target not in segment.message_ids):
            raise ValueError("Recorded source link is outside the selected Segment.")
        choices.append(ObservedChoice(speaker=speaker.deployment_id, target_message_id=target))
    return LegacyObservation(
        Prediction(
            case_id=case_id,
            outcome="speak" if choices else "none",
            choices=tuple(choices),
            reason=plan.reason,
            usage=observation_usage,
        ),
        source_hash,
    )
