from datetime import UTC, datetime, timedelta

from echo_masque.character_recall import CharacterRecallService
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.discord_identity_models import DiscordMessageRouteRecord


class _AlphaEncoder:
    model_name = "test/current-message-recall"
    dimension = 3

    def embed_query(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]

    def embed_passage(self, text: str) -> list[float]:
        return [1.0, 0.0, 0.0]


def _episode(
    runtime: ConversationRuntimeRepository,
    *,
    key: str,
    message_id: str,
    summary: str,
    now: datetime,
):
    runtime.append_episode_segment(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        channel_id="general",
        discord_thread_id="",
        conversation_thread_id=key,
        segment_id=f"segment-{key}",
        source_message_ids=(message_id,),
        participant_ids=("user-1",),
        summary=summary,
        key_events=(summary,),
        now=now,
    )
    return runtime.close_episode(
        owner_id="owner-1", conversation_thread_id=key, reason="test", now=now
    )


def test_explicit_history_recall_excludes_current_trigger_episode() -> None:
    database = Database("sqlite://")
    database.initialize()
    runtime = ConversationRuntimeRepository(database)
    now = datetime(2026, 8, 18, 3, 0, tzinfo=UTC)
    historical = _episode(
        runtime,
        key="historical",
        message_id="old-message",
        summary="Earlier Project Alpha architecture discussion.",
        now=now,
    )
    current = _episode(
        runtime,
        key="current",
        message_id="current-message",
        summary="还记得之前的 Project Alpha architecture 吗？",
        now=now + timedelta(minutes=5),
    )
    assert historical is not None and current is not None
    with database.session() as session:
        session.add(
            CharacterDeploymentRecord(
                id="deployment-ann",
                owner_id="owner-1",
                character_card_id="character-ann",
                connection_id="connection-1",
                platform="discord",
                workspace_id="guild-1",
                workspace_name="Guild",
                channel_id="general",
                channel_name="general",
                thread_id="",
                thread_name="",
                participation_mode="smart",
                memory_scope="server",
                version_label="",
                sticker_count=0,
                status="active",
            )
        )
        for message_id in ("old-message", "current-message"):
            session.add(
                DiscordMessageRouteRecord(
                    message_id=message_id,
                    owner_id="owner-1",
                    connection_id="connection-1",
                    deployment_id="deployment-ann",
                    character_card_id="character-ann",
                    workspace_id="guild-1",
                    channel_id="general",
                    thread_id="",
                    webhook_id="webhook-1",
                )
            )
        session.commit()
    result = CharacterRecallService(
        BeliefRepository(database), encoder=_AlphaEncoder()
    ).high_confidence_recall(
        owner_id="owner-1",
        character_card_id="character-ann",
        connection_id="connection-1",
        guild_id="guild-1",
        subject_user_id="user-1",
        deployment_id="deployment-ann",
        query="还记得之前的 Project Alpha architecture 吗？",
        exclude_source_message_id="current-message",
    )
    refs = {item.ref for item in result.items if item.origin == "episode"}
    assert historical.id in refs
    assert current.id not in refs
