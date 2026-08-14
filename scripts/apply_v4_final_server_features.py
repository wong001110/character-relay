from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTE = ROOT / "src/echo_masque/api/routes/smart_participation_v4.py"
LEARNED = ROOT / "src/echo_masque/character_learned_state.py"
SCHEMA = ROOT / "src/echo_masque/api/smart_participation_outcome_schemas.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected one match, got {count}")
    return text.replace(old, new, 1)


def patch_learned() -> None:
    text = LEARNED.read_text(encoding="utf-8")
    text = replace_once(
        text,
        '    "conversation_ownership": 24 * 60 * 60,\n',
        '    "conversation_ownership": 30 * 60,\n',
        "ownership half-life",
    )
    LEARNED.write_text(text, encoding="utf-8")


def patch_schema() -> None:
    text = SCHEMA.read_text(encoding="utf-8")
    text = text.replace('        "admin_annotation",\n', "")
    SCHEMA.write_text(text, encoding="utf-8")


def patch_route() -> None:
    text = ROUTE.read_text(encoding="utf-8")
    text = replace_once(
        text,
        "from echo_masque.api.smart_participation_outcome_schemas import (\n"
        "    SmartParticipationOutcomeObservation,\n"
        "    SmartParticipationOutcomeView,\n"
        ")\n",
        "from echo_masque.api.smart_participation_outcome_schemas import (\n"
        "    SmartParticipationLearnedEvidenceRequest,\n"
        "    SmartParticipationLearnedEvidenceView,\n"
        "    SmartParticipationOutcomeObservation,\n"
        "    SmartParticipationOutcomeView,\n"
        "    SmartParticipationRecentSpeakerRequest,\n"
        "    SmartParticipationRecentSpeakerView,\n"
        ")\n",
        "outcome schema imports",
    )
    text = replace_once(
        text,
        "from echo_masque.character_learned_state import CharacterLearnedStateService\n",
        "from echo_masque.character_learned_state import (\n"
        "    CharacterLearnedStateService,\n"
        "    LearnedStateEvidence,\n"
        ")\n",
        "learned evidence import",
    )
    marker = '\n\n__all__ = ["router"]\n'
    endpoints = r'''

@router.post(
    "/recent-speaker",
    response_model=SmartParticipationRecentSpeakerView,
)
def recent_smart_participation_speaker_v4(
    payload: SmartParticipationRecentSpeakerRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationRecentSpeakerView:
    """Recover only a bounded recent Smart speaker after Connector-local state loss."""

    _authorize_connector(request, authorization)
    records = _deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    allowed_requested = frozenset(payload.allowed_deployment_ids)
    allowed = frozenset(
        item.id
        for item in records
        if item.id in allowed_requested and item.participation_mode == "smart"
    )
    if not allowed:
        return SmartParticipationRecentSpeakerView()
    deployment_id = _durable_service(request).recent_speaker(
        connection_id=payload.connection_id,
        guild_id=payload.guild_id,
        channel_id=payload.channel_id,
        thread_id=payload.thread_id,
        maximum_age_seconds=payload.maximum_age_seconds,
        allowed_deployment_ids=allowed,
    )
    return SmartParticipationRecentSpeakerView(deployment_id=deployment_id)


@router.post(
    "/learned-evidence",
    response_model=SmartParticipationLearnedEvidenceView,
)
def record_smart_participation_learned_evidence_v4(
    payload: SmartParticipationLearnedEvidenceRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> SmartParticipationLearnedEvidenceView:
    """Record bounded Expertise/Stance evidence tied to an actual Connector deployment."""

    _authorize_connector(request, authorization)
    records = _deployment_repository(request).list_connector_deployments(
        platform="discord",
        connection_id=payload.connection_id,
    )
    deployment = next((item for item in records if item.id == payload.deployment_id), None)
    if deployment is None:
        raise HTTPException(status_code=404, detail="Deployment not found on this connector.")
    if payload.delta == 0.0 or payload.confidence == 0.0:
        return SmartParticipationLearnedEvidenceView(recorded=False)
    service = CharacterLearnedStateService(_deployment_repository(request).database)
    view = service.record_evidence(
        LearnedStateEvidence(
            owner_id=deployment.owner_id,
            character_card_id=deployment.character_card_id,
            state_type=payload.state_type,
            subject_type=payload.subject_type,
            subject_key=payload.subject_key,
            delta=payload.delta,
            confidence=payload.confidence,
            source_type=payload.source_type,
            source_message_id=payload.source_message_id,
            source_burst_id=payload.source_burst_id,
            reason_code=payload.reason_code,
        )
    )
    return SmartParticipationLearnedEvidenceView(
        recorded=True,
        state_type=view.state_type,
        subject_key=view.subject_key,
        value=view.value,
        confidence=view.confidence,
        evidence_count=view.evidence_count,
    )
'''
    if "/recent-speaker" not in text:
        text = replace_once(text, marker, endpoints + marker, "final V4 endpoints")
    ROUTE.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    patch_learned()
    patch_schema()
    patch_route()
