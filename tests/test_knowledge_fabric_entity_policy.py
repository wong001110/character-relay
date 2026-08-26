from echo_masque.knowledge_fabric_interpretation_policy import (
    RESOLUTION_ACTIVE,
    RESOLUTION_REJECTED,
    RESOLUTION_SUPERSEDED,
    interpretation_status_is_valid,
    may_replace_active_resolution,
    resolution_status_is_valid,
    world_interpretation_promotes_to_belief,
)


def test_resolution_and_interpretation_policy_fails_closed() -> None:
    assert resolution_status_is_valid(RESOLUTION_ACTIVE)
    assert resolution_status_is_valid(RESOLUTION_REJECTED)
    assert resolution_status_is_valid(RESOLUTION_SUPERSEDED)
    assert not resolution_status_is_valid("pending")
    assert may_replace_active_resolution(existing_canonical_id="one", next_canonical_id="two")
    assert not may_replace_active_resolution(existing_canonical_id="one", next_canonical_id="one")
    assert not may_replace_active_resolution(existing_canonical_id="", next_canonical_id="two")
    assert interpretation_status_is_valid("active")
    assert interpretation_status_is_valid("disputed")
    assert interpretation_status_is_valid("unresolved")
    assert not interpretation_status_is_valid("promoted")
    assert not world_interpretation_promotes_to_belief()
