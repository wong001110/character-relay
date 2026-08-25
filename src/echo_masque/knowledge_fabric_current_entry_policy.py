"""Pure retention decisions for source-native current-entry mappings."""


def may_reuse_current_evidence(
    *,
    current_status: str,
    current_content_sha256: str | None,
    current_evidence_unit_id: str | None,
    incoming_content_sha256: str,
) -> bool:
    """Only an available, content-identical entry can retain its old immutable Evidence."""

    return (
        current_status == "available"
        and current_content_sha256 == incoming_content_sha256
        and current_evidence_unit_id is not None
    )


def current_evidence_must_be_invalidated(*, status: str, evidence_unit_id: str | None) -> bool:
    """A previously current available entry loses only its derived indexes when replaced/removed."""

    return status == "available" and evidence_unit_id is not None


__all__ = ["current_evidence_must_be_invalidated", "may_reuse_current_evidence"]
