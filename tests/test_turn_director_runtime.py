from pydantic import ValidationError

from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.utility_gateway_contracts import TurnDirectorProposal


def _proposal(**updates: object) -> TurnDirectorProposal:
    values: dict[str, object] = {
        "response_mode": "answer",
        "response_posture": "informed_response",
        "focus_message_ids": ("message-1",),
        "read_requests": (
            {"tool_id": "knowledge.search", "query": "release date", "limit": 2},
        ),
        "confidence": 0.9,
        "reason_code": "knowledge_gap",
    }
    values.update(updates)
    return TurnDirectorProposal.model_validate(values)


def test_turn_director_runtime_rejects_scope_or_posture_changes() -> None:
    allowed = ("memory.search", "conversation.search", "knowledge.search")

    assert DiscordConnectorRuntime._valid_turn_director_proposal(
        _proposal(),
        selected_message_ids=("message-1", "message-2"),
        allowed_tools=allowed,
        response_posture="informed_response",
    )
    assert not DiscordConnectorRuntime._valid_turn_director_proposal(
        _proposal(focus_message_ids=("outside-message",)),
        selected_message_ids=("message-1", "message-2"),
        allowed_tools=allowed,
        response_posture="informed_response",
    )
    assert not DiscordConnectorRuntime._valid_turn_director_proposal(
        _proposal(response_posture="casual_peer"),
        selected_message_ids=("message-1", "message-2"),
        allowed_tools=allowed,
        response_posture="informed_response",
    )
    assert not DiscordConnectorRuntime._valid_turn_director_proposal(
        _proposal(
            read_requests=(
                {"tool_id": "memory.search", "query": "release date", "limit": 2},
            )
        ),
        selected_message_ids=("message-1", "message-2"),
        allowed_tools=("knowledge.search",),
        response_posture="informed_response",
    )


def test_turn_director_contract_forbids_unknown_or_external_tools() -> None:
    try:
        _proposal(unexpected="not allowed")
    except ValidationError:
        pass
    else:
        raise AssertionError("Turn Director contract accepted an unknown field")

    try:
        _proposal(
            read_requests=(
                {"tool_id": "image.generate", "query": "release date", "limit": 2},
            )
        )
    except ValidationError:
        pass
    else:
        raise AssertionError("Turn Director contract accepted a side-effect tool")
