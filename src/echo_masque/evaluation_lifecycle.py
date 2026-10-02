"""Account deletion and legacy-local ownership integration for Judge evaluations."""

from typing import cast

from echo_masque.account_lifecycle import LifecycleConflict
from echo_masque.authoring_archive import AuthoringArchiveService
from echo_masque.calibration_lifecycle import CalibrationAwareAccountLifecycleService
from echo_masque.persistence import (
    AuthRepository,
    CalibrationRepository,
    ConditionWatchRepository,
    ConversationMediaReferenceRepository,
    Database,
    DeploymentRepository,
    DeploymentToolRepository,
    DiscordIdentityRepository,
    EvaluationRepository,
    ExpressionRepository,
    GeneratedMediaArtifactRepository,
    ScheduledReminderRepository,
)
from echo_masque.persistence.chat_lifecycle_repository import ChatLifecycleRepository
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.persistence.turn_job_repository import TurnJobRepository
from echo_masque.persistence.web_room_repository import WebRoomRepository


class EvaluationAwareAccountLifecycleService(CalibrationAwareAccountLifecycleService):
    """Own non-core account cleanup, including explicit room evidence and notes."""

    def __init__(
        self,
        database: Database,
        auth_repository: AuthRepository,
        authoring_archive_service: AuthoringArchiveService,
        calibration_repository: CalibrationRepository,
        evaluation_repository: EvaluationRepository,
        deployment_repository: DeploymentRepository | None = None,
        discord_identity_repository: DiscordIdentityRepository | None = None,
        expression_repository: ExpressionRepository | None = None,
        knowledge_fabric_repository: KnowledgeFabricRepository | None = None,
        deployment_tool_repository: DeploymentToolRepository | None = None,
        scheduled_reminder_repository: ScheduledReminderRepository | None = None,
        condition_watch_repository: ConditionWatchRepository | None = None,
        conversation_media_repository: ConversationMediaReferenceRepository | None = None,
        generated_media_repository: GeneratedMediaArtifactRepository | None = None,
        turn_job_repository: TurnJobRepository | None = None,
        web_room_repository: WebRoomRepository | None = None,
    ) -> None:
        super().__init__(
            database,
            auth_repository,
            authoring_archive_service,
            calibration_repository,
        )
        self.evaluation_repository = evaluation_repository
        self.deployment_repository = deployment_repository or DeploymentRepository(database)
        self.deployment_tool_repository = deployment_tool_repository or DeploymentToolRepository(
            database
        )
        self.scheduled_reminder_repository = (
            scheduled_reminder_repository or ScheduledReminderRepository(database)
        )
        self.condition_watch_repository = condition_watch_repository or ConditionWatchRepository(
            database
        )
        self.discord_identity_repository = discord_identity_repository or DiscordIdentityRepository(
            database
        )
        self.expression_repository = expression_repository or ExpressionRepository(database)
        self.knowledge_fabric_repository = knowledge_fabric_repository or KnowledgeFabricRepository(
            database
        )
        self.conversation_media_repository = (
            conversation_media_repository or ConversationMediaReferenceRepository(database)
        )
        self.generated_media_repository = (
            generated_media_repository or GeneratedMediaArtifactRepository(database)
        )
        self.chat_repository = ChatLifecycleRepository(database)
        self.turn_job_repository = turn_job_repository or TurnJobRepository(database)
        self.web_room_repository = web_room_repository or WebRoomRepository(database)

    def delete_account(
        self,
        user_id: str,
        *,
        email: str,
        actor_user_id: str | None = None,
    ) -> dict[str, int]:
        self.validate_account_deletion(user_id)
        chat_counts = self.chat_repository.delete_owner(user_id)
        evaluation_counts = self.evaluation_repository.delete_owner(user_id)
        expression_counts = self.expression_repository.delete_owner(user_id)
        knowledge_fabric_counts = self.knowledge_fabric_repository.delete_owner(user_id)
        identity_counts = self.discord_identity_repository.delete_owner(user_id)
        reminder_count = self.scheduled_reminder_repository.delete_owner(user_id)
        watch_count = self.condition_watch_repository.delete_owner(user_id)
        deployment_tool_count = self.deployment_tool_repository.delete_owner(user_id)
        conversation_media_count = self.conversation_media_repository.delete_owner(user_id)
        generated_media_count = self.generated_media_repository.delete_owner(user_id)
        turn_job_count = self.turn_job_repository.delete_owner(user_id)
        web_room_counts = self.web_room_repository.delete_owner(user_id)
        deployment_counts = self.deployment_repository.delete_owner(user_id)
        deleted = super().delete_account(
            user_id,
            email=email,
            actor_user_id=actor_user_id,
        )
        return {
            **deleted,
            **evaluation_counts,
            **chat_counts,
            **expression_counts,
            **knowledge_fabric_counts,
            **identity_counts,
            "discord_turn_jobs": turn_job_count,
            **web_room_counts,
            "scheduled_reminders": reminder_count,
            "condition_watches": watch_count,
            "deployment_tool_profiles": deployment_tool_count,
            "conversation_media_references": conversation_media_count,
            "generated_media_artifacts": generated_media_count,
            **deployment_counts,
        }

    def claim_local_workspace(self, *, actor_user_id: str) -> dict[str, int]:
        # Sealed room/effect scopes cannot be reassigned by a legacy authoring claim.
        self.chat_repository.assert_claimable("local-user")
        chat_counts = self.chat_repository.claim_authored_notes("local-user", actor_user_id)
        base_counts: dict[str, int] = {}
        base_error: LifecycleConflict | None = None
        try:
            base_counts = super().claim_local_workspace(actor_user_id=actor_user_id)
        except LifecycleConflict as exc:
            base_error = exc

        evaluation_counts = self.evaluation_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        deployment_counts = self.deployment_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        deployment_tool_count = self.deployment_tool_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        reminder_count = self.scheduled_reminder_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        watch_count = self.condition_watch_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        identity_counts = self.discord_identity_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        expression_counts = self.expression_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        knowledge_fabric_counts = self.knowledge_fabric_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        conversation_media_count = self.conversation_media_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        generated_media_count = self.generated_media_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        combined = {
            **base_counts,
            **evaluation_counts,
            **chat_counts,
            **deployment_counts,
            "deployment_tool_profiles": deployment_tool_count,
            "scheduled_reminders": reminder_count,
            "condition_watches": watch_count,
            "conversation_media_references": conversation_media_count,
            "generated_media_artifacts": generated_media_count,
            **identity_counts,
            **expression_counts,
            **knowledge_fabric_counts,
        }
        if sum(combined.values()) == 0:
            if base_error is not None:
                raise base_error
            raise LifecycleConflict("No unclaimed local workspace data was found.")

        if sum(evaluation_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.evaluation_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=cast(dict[str, object], evaluation_counts),
            )
        if sum(deployment_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.deployment_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=cast(dict[str, object], deployment_counts),
            )
        if sum(identity_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.discord_identity_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=cast(dict[str, object], identity_counts),
            )
        if sum(knowledge_fabric_counts.values()) > 0:
            self.auth_repository.audit(
                actor_user_id=actor_user_id,
                action="workspace.knowledge_fabric_local_claimed",
                resource_type="workspace",
                resource_id=actor_user_id,
                metadata=cast(dict[str, object], knowledge_fabric_counts),
            )
        return combined
