from pathlib import Path

from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import func, select

from echo_masque.api import create_app
from echo_masque.config import Settings
from echo_masque.persistence.conversation_media_models import ConversationMediaReferenceRecord
from echo_masque.persistence.generated_media_models import GeneratedMediaArtifactRecord


def settings(path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=f"sqlite:///{path}",
        credential_encryption_keys=SecretStr(Fernet.generate_key().decode("ascii")),
    )


def count_owner(app: object, model: object, owner_id: str) -> int:
    database = app.state.database  # type: ignore[attr-defined]
    with database.session() as session:
        return int(
            session.scalar(
                select(func.count()).select_from(model).where(model.owner_id == owner_id)  # type: ignore[attr-defined]
            )
            or 0
        )


def test_media_rows_follow_local_claim_and_account_deletion(tmp_path: Path) -> None:
    app = create_app(settings(tmp_path / "media-lifecycle.db"))
    actor = app.state.auth_repository.create_user(
        email="media-owner@example.com",
        display_name="Media Owner",
        password_hash="unused",
        role="user",
    )
    conversation = app.state.conversation_media_repository
    generated = app.state.generated_media_repository

    conversation.remember_generated_reference(
        owner_id="local-user",
        deployment_id="deployment-legacy",
        character_card_id="card-ann",
        guild_id="guild-1",
        channel_id="channel-1",
        thread_id="",
        message_id="generated-message",
        source_key="generated:sha256:legacy",
        label="legacy.png",
        source_uri="https://cdn.discordapp.com/attachments/channel/legacy.png",
    )
    generated.create(
        owner_id="local-user",
        deployment_id="deployment-legacy",
        character_card_id="card-ann",
        media_key="sha256:legacy",
        mime_type="image/png",
        filename="legacy.png",
        provider="fake",
        model="fake-image",
        content=b"\x89PNG\r\n\x1a\nlegacy",
    )

    claimed = app.state.account_lifecycle_service.claim_local_workspace(
        actor_user_id=actor.id
    )

    assert claimed["conversation_media_references"] == 1
    assert claimed["generated_media_artifacts"] == 1
    assert count_owner(app, ConversationMediaReferenceRecord, "local-user") == 0
    assert count_owner(app, GeneratedMediaArtifactRecord, "local-user") == 0
    assert count_owner(app, ConversationMediaReferenceRecord, actor.id) == 1
    assert count_owner(app, GeneratedMediaArtifactRecord, actor.id) == 1

    deleted = app.state.account_lifecycle_service.delete_account(
        actor.id,
        email=actor.email,
    )

    assert deleted["conversation_media_references"] == 1
    assert deleted["generated_media_artifacts"] == 1
    assert count_owner(app, ConversationMediaReferenceRecord, actor.id) == 0
    assert count_owner(app, GeneratedMediaArtifactRecord, actor.id) == 0
