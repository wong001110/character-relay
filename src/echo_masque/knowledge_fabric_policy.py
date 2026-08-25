"""Small, deterministic authorization and precedence rules for Knowledge Fabric."""

from __future__ import annotations

OVERLAY_INHERIT = "inherit"
OVERLAY_DENY = "deny"
OVERLAY_MODES = frozenset({OVERLAY_INHERIT, "augment", "override", OVERLAY_DENY})


def may_manage_global_library(*, is_super_admin: bool, is_public_demo: bool) -> bool:
    """Only a real Super Admin manages global library state; Demo never can."""

    return is_super_admin and not is_public_demo


def may_access_server_scope(
    *,
    is_super_admin: bool,
    is_explicit_administrator: bool,
    is_public_demo: bool,
) -> bool:
    """Authorize a scope only through Super Admin or explicit new membership."""

    return not is_public_demo and (is_super_admin or is_explicit_administrator)


def overlay_mode_or_inherit(mode: str | None) -> str:
    """Fail closed for malformed policy data rather than inventing precedence."""

    if mode is None:
        return OVERLAY_INHERIT
    if mode not in OVERLAY_MODES:
        raise ValueError("Unknown Knowledge overlay mode.")
    return mode


def corpus_is_effectively_available(
    *,
    owner_type: str,
    owner_id: str,
    visibility: str,
    status: str,
    server_scope_id: str,
    global_grant_enabled: bool,
    overlay_mode: str | None,
) -> bool:
    """Apply access before future retrieval/ranking and make deny non-destructive."""

    mode = overlay_mode_or_inherit(overlay_mode)
    if mode == OVERLAY_DENY:
        return False
    if status != "active":
        return False
    if owner_type == "server":
        return owner_id == server_scope_id
    return (
        owner_type == "system"
        and visibility == "global"
        and global_grant_enabled
    )


def is_user_owned_by(*, owner_type: str, owner_id: str, account_id: str) -> bool:
    """Keep account deletion strictly away from system and server ownership."""

    return owner_type == "user" and owner_id == account_id


def is_local_user_owned(*, owner_type: str, owner_id: str, local_owner_id: str) -> bool:
    """Only conventional local user data is eligible for a local-workspace claim."""

    return owner_type == "user" and owner_id == local_owner_id


def is_user_grant_for_account(*, grantee_type: str, grantee_id: str, account_id: str) -> bool:
    """Never mistake a server grant for an account-owned grant during lifecycle work."""

    return grantee_type == "user" and grantee_id == account_id


__all__ = [
    "corpus_is_effectively_available",
    "is_local_user_owned",
    "is_user_grant_for_account",
    "is_user_owned_by",
    "may_access_server_scope",
    "may_manage_global_library",
    "overlay_mode_or_inherit",
]
