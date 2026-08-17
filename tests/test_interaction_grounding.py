from __future__ import annotations

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.interaction_grounding import ground_interaction


def _payload(text: str, *, mentioned: bool = False, replied: bool = False) -> DiscordInboundMessage:
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-ann",
        message_id="m1",
        guild_id="guild-1",
        channel_id="general",
        author_id="user-1",
        author_display_name="Juen",
        text=text,
        mentioned_bot=mentioned,
        replied_to_bot=replied,
        smart_candidate=True,
    )


def test_profession_relevance_does_not_turn_ambient_chat_into_direct_question() -> None:
    result = ground_interaction(
        payload=_payload("律师碰到证据不足的案子一般会怎么处理？"),
        character_name="Ann",
        role_hint="律师",
    )

    assert result.audience == "ambient"
    assert result.expertise_relevant is True
    assert result.expertise_requested is False
    assert result.directed_at_character is False
    assert result.response_posture == "casual_peer"


def test_platform_mention_is_direct_character_address() -> None:
    result = ground_interaction(
        payload=_payload("这个案子你怎么看？", mentioned=True),
        character_name="Ann",
        role_hint="律师",
    )

    assert result.audience == "direct_character"
    assert result.directed_at_character is True
    assert result.interaction_type == "direct_request"


def test_explicit_role_group_address_is_not_personal_interrogation() -> None:
    result = ground_interaction(
        payload=_payload("你们做律师的遇到这种证据都会怎么判断？"),
        character_name="Ann",
        role_hint="律师",
    )

    assert result.audience == "role_group_directed"
    assert result.directed_at_character is False
    assert result.expertise_requested is True
    assert result.response_posture == "role_peer"


def test_direct_prior_claim_challenge_is_grounded_as_challenge() -> None:
    result = ground_interaction(
        payload=_payload("Ann，你刚才说这没问题，现在怎么解释？"),
        character_name="Ann",
        role_hint="律师",
    )

    assert result.audience == "direct_character"
    assert result.interaction_type == "direct_challenge"
    assert result.response_posture == "respond_to_challenge"


def test_explicit_group_invitation_is_group_request() -> None:
    result = ground_interaction(
        payload=_payload("大家觉得这个方案怎么样？"),
        character_name="Ann",
        role_hint="律师",
    )

    assert result.audience == "group_invited"
    assert result.interaction_type == "group_request"
    assert result.directed_at_character is False
