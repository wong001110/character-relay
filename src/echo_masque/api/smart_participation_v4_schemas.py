"""Deprecated import bridge to the final Conversation Intelligence v3 connector contract.

Runtime authority lives in smart_participation_v3_schemas. This module exists only to keep
internal imports stable while legacy modules are physically removed during the same hard cutover.
It contains no V4 or Topic-specific fields.
"""

from echo_masque.api.smart_participation_v3_schemas import (
    SmartParticipationBurstMessage,
    SmartParticipationMediaDescriptor,
    SmartParticipationResolveCandidate,
    SmartParticipationResolveCandidateView,
    SmartParticipationResolveRequest,
    SmartParticipationResolveView,
    SmartParticipationSpeakerPlanItem,
)

__all__ = [
    "SmartParticipationBurstMessage",
    "SmartParticipationMediaDescriptor",
    "SmartParticipationResolveCandidate",
    "SmartParticipationResolveCandidateView",
    "SmartParticipationResolveRequest",
    "SmartParticipationResolveView",
    "SmartParticipationSpeakerPlanItem",
]
