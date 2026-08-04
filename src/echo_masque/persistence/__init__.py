"""Persistence exports."""

from echo_masque.persistence.auth_repository import AuthRepository
from echo_masque.persistence.authoring_models import (
    AuthoringRuntimeRecord,
    AuthoringScenarioDraftRecord,
    AuthoringTestPackDraftItemRecord,
    AuthoringTestPackDraftRecord,
)
from echo_masque.persistence.authoring_repository import AuthoringConflict, AuthoringRepository
from echo_masque.persistence.calibration_models import (
    CalibrationCaseRecord,
    CalibrationDatasetRecord,
)
from echo_masque.persistence.calibration_repository import CalibrationConflict
from echo_masque.persistence.calibration_repository import (
    CalibrationRepository as BaseCalibrationRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    CharacterDeploymentRecord,
    PlatformConnectionRecord,
)
from echo_masque.persistence.deployment_repository import (
    DeploymentConflict,
    DeploymentRepository,
)
from echo_masque.persistence.discord_identity_models import (
    DeploymentMessageIdentityRecord,
    DiscordMessageRouteRecord,
    DiscordWebhookBindingRecord,
)
from echo_masque.persistence.discord_identity_repository import DiscordIdentityRepository
from echo_masque.persistence.evaluation_models import (
    JudgeEvaluationRecord,
    JudgePredictionRecord,
)
from echo_masque.persistence.evaluation_repository import EvaluationRepository
from echo_masque.persistence.matrix_repository import MatrixRepository
from echo_masque.persistence.portable_calibration_repository import (
    PortableCalibrationRepository,
)
from echo_masque.persistence.provider_trace_models import ProviderTraceRecord
from echo_masque.persistence.provider_trace_repository import ProviderTraceRepository
from echo_masque.persistence.repository import Repository
from echo_masque.persistence.storage import (
    StorageStatus,
    UnsafeProductionStorageError,
    inspect_storage,
)
from echo_masque.persistence.target_access_repository import TargetAccessRepository
from echo_masque.persistence.trial_request import (
    TrialRequestMetadata,
    decode_trial_metadata,
    decode_trial_request,
    encode_trial_request,
)
from echo_masque.persistence.workspace_repository import WorkspaceRepository

CalibrationRepository = PortableCalibrationRepository

__all__ = [
    "AuthRepository",
    "AuthoringConflict",
    "AuthoringRepository",
    "AuthoringRuntimeRecord",
    "AuthoringScenarioDraftRecord",
    "AuthoringTestPackDraftItemRecord",
    "AuthoringTestPackDraftRecord",
    "BaseCalibrationRepository",
    "CalibrationCaseRecord",
    "CalibrationConflict",
    "CalibrationDatasetRecord",
    "CalibrationRepository",
    "CharacterDeploymentRecord",
    "Database",
    "DeploymentConflict",
    "DeploymentMessageIdentityRecord",
    "DeploymentRepository",
    "DiscordIdentityRepository",
    "DiscordMessageRouteRecord",
    "DiscordWebhookBindingRecord",
    "EvaluationRepository",
    "JudgeEvaluationRecord",
    "JudgePredictionRecord",
    "MatrixRepository",
    "PlatformConnectionRecord",
    "PortableCalibrationRepository",
    "ProviderTraceRecord",
    "ProviderTraceRepository",
    "Repository",
    "StorageStatus",
    "TargetAccessRepository",
    "TrialRequestMetadata",
    "UnsafeProductionStorageError",
    "WorkspaceRepository",
    "decode_trial_metadata",
    "decode_trial_request",
    "encode_trial_request",
    "inspect_storage",
]
