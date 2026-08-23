import json

from echo_masque.api.connector_schemas import DiscordContextMessage, DiscordInboundMessage
from echo_masque.api.expression_schemas import ExpressionCandidate
from echo_masque.connector_runtime import DiscordConnectorRuntime


def _expression() -> ExpressionCandidate:
    return ExpressionCandidate(
        resource_key="emoji:wave",
        resource_type="emoji",
        resource_id="wave",
        name="wave",
        animated=False,
        available=True,
        enabled=True,
        allowed_actions=["inline", "reaction"],
        semantic_intent="friendly_greeting",
        semantic_emotion="warm",
        semantic_description="A very long private description that must not be in the prompt.",
        semantic_source="manual",
        semantic_confidence=1.0,
        asset_url="",
        format_type="emoji",
        score=0.9,
        signals={},
    )


def _payload(*, include_trigger: bool) -> DiscordInboundMessage:
    candidate = _expression()
    recent = [
        DiscordContextMessage(
            message_id="message-prior",
            author_id="member-prior",
            author_display_name="Prior member",
            text="Prior context.",
        )
    ]
    if include_trigger:
        recent.append(
            DiscordContextMessage(
                message_id="message-trigger",
                author_id="member-trigger",
                author_display_name="Trigger member",
                text="Private trigger text.",
                emojis=[candidate],
            )
        )
    return DiscordInboundMessage(
        connection_id="connection-1",
        deployment_id="deployment-1",
        message_id="message-trigger",
        guild_id="guild-1",
        guild_name="Guild",
        channel_id="channel-1",
        channel_name="general",
        author_id="member-trigger",
        author_display_name="Trigger member",
        text="Private trigger text.",
        mentioned_bot=True,
        emojis=[candidate],
        expression_candidates=[candidate],
        recent_messages=recent,
    )


def test_roleplay_prompt_suppresses_duplicate_live_context_and_trigger() -> None:
    result = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=_payload(include_trigger=True),
        context_sections=(
            "LIVE CONTEXT\nPrior member: Prior context.\nTrigger member: Private trigger text.",
            "BELIEFS\nKeep the useful V3 evidence.",
        ),
    )

    assert "LIVE CONTEXT" not in result.text
    assert "BELIEFS\nKeep the useful V3 evidence." in result.text
    assert result.text.count("Private trigger text.") == 1
    assert "Latest triggering message: trigger (already included" in result.text
    assert "A very long private description" not in result.text
    assert "intent: friendly_greeting" in result.text
    assert "source: manual" not in result.text
    assert "confidence:" not in result.text

    manifest = result.manifest
    assert manifest["trigger_already_in_recent"] is True
    assert manifest["live_context_suppressed"] is True
    assert manifest["duplicate_suppressed_count"] == 2
    assert manifest["expression_candidate_count"] == 1
    assert manifest["expression_intent_count"] == 1
    assert manifest["expression_description_fallback_count"] == 0
    serialized = json.dumps(manifest)
    assert "Private trigger text" not in serialized
    assert "A very long private description" not in serialized
    assert "member-trigger" not in serialized


def test_roleplay_prompt_appends_a_missing_trigger_once() -> None:
    result = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=_payload(include_trigger=False),
    )

    assert result.text.count("Private trigger text.") == 1
    assert result.manifest["trigger_already_in_recent"] is False
    assert result.manifest["recent_message_count"] == 2


def test_roleplay_prompt_limits_the_transcript_to_the_selected_segment() -> None:
    payload = _payload(include_trigger=True).model_copy(
        update={
            "recent_messages": [
                DiscordContextMessage(
                    message_id="segment-message",
                    author_id="member-segment",
                    author_display_name="Segment member",
                    text="Selected discussion.",
                ),
                DiscordContextMessage(
                    message_id="other-message",
                    author_id="member-other",
                    author_display_name="Other member",
                    text="Unrelated simultaneous discussion.",
                ),
                DiscordContextMessage(
                    message_id="message-trigger",
                    author_id="member-trigger",
                    author_display_name="Trigger member",
                    text="Private trigger text.",
                ),
            ]
        }
    )

    result = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=payload,
        focused_message_ids=("segment-message", "message-trigger"),
    )

    assert "Focused conversation:" in result.text
    assert "Selected discussion." in result.text
    assert "Private trigger text." in result.text
    assert "Unrelated simultaneous discussion." not in result.text
    assert result.manifest["focused_segment_applied"] is True
    assert result.manifest["focused_message_count"] == 2
    assert result.manifest["recent_message_count"] == 2


def test_roleplay_prompt_excludes_an_unselected_smart_trigger() -> None:
    payload = _payload(include_trigger=True).model_copy(
        update={
            "mentioned_bot": False,
            "smart_candidate": True,
            "recent_messages": [
                DiscordContextMessage(
                    message_id="segment-message",
                    author_id="member-segment",
                    author_display_name="Segment member",
                    text="Selected discussion.",
                ),
                DiscordContextMessage(
                    message_id="other-message",
                    author_id="member-other",
                    author_display_name="Other member",
                    text="Unrelated simultaneous discussion.",
                ),
                DiscordContextMessage(
                    message_id="message-trigger",
                    author_id="member-trigger",
                    author_display_name="Trigger member",
                    text="Private trigger text.",
                ),
            ],
        }
    )

    result = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=payload,
        focused_message_ids=("segment-message",),
    )

    assert "Focused conversation:" in result.text
    assert "Selected discussion." in result.text
    assert "Private trigger text." not in result.text
    assert "Unrelated simultaneous discussion." not in result.text
    assert "selected conversation" in result.text
    assert result.manifest["focused_segment_applied"] is True
    assert result.manifest["focused_trigger_excluded"] is True
    assert result.manifest["recent_message_count"] == 1


def test_roleplay_prompt_falls_back_to_the_trigger_for_explicit_addressing() -> None:
    payload = _payload(include_trigger=True).model_copy(
        update={
            "recent_messages": [
                DiscordContextMessage(
                    message_id="segment-message",
                    author_id="member-segment",
                    author_display_name="Segment member",
                    text="Selected discussion.",
                ),
                DiscordContextMessage(
                    message_id="message-trigger",
                    author_id="member-trigger",
                    author_display_name="Trigger member",
                    text="Private trigger text.",
                ),
            ]
        }
    )

    result = DiscordConnectorRuntime._social_prompt_with_manifest(
        character_name="Ann",
        payload=payload,
        focused_message_ids=("segment-message",),
    )

    assert "Recent conversation:" in result.text
    assert "Selected discussion." in result.text
    assert "Private trigger text." in result.text
    assert result.manifest["focused_segment_applied"] is False
    assert result.manifest["focused_trigger_excluded"] is False
