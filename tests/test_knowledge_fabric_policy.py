import pytest

from echo_masque.knowledge_fabric_policy import (
    corpus_is_effectively_available,
    is_local_user_owned,
    is_user_grant_for_account,
    is_user_owned_by,
    may_access_server_scope,
    may_manage_global_library,
    overlay_mode_or_inherit,
)
from echo_masque.persistence.knowledge_fabric_repository import (
    OWNER_SERVER,
    OWNER_SYSTEM,
    VISIBILITY_GLOBAL,
)


@pytest.mark.parametrize(
    ("is_super_admin", "is_public_demo", "expected"),
    [
        (True, False, True),
        (False, False, False),
        (True, True, False),
        (False, True, False),
    ],
)
def test_global_library_management_requires_real_super_admin_outside_demo(
    is_super_admin: bool,
    is_public_demo: bool,
    expected: bool,
) -> None:
    assert (
        may_manage_global_library(
            is_super_admin=is_super_admin,
            is_public_demo=is_public_demo,
        )
        is expected
    )


@pytest.mark.parametrize(
    ("is_super_admin", "is_member", "is_public_demo", "expected"),
    [
        (False, False, False, False),
        (False, True, False, True),
        (True, False, False, True),
        (True, True, False, True),
        (True, True, True, False),
        (False, True, True, False),
    ],
)
def test_scope_access_requires_explicit_membership_or_super_admin_and_excludes_demo(
    is_super_admin: bool,
    is_member: bool,
    is_public_demo: bool,
    expected: bool,
) -> None:
    assert (
        may_access_server_scope(
            is_super_admin=is_super_admin,
            is_explicit_administrator=is_member,
            is_public_demo=is_public_demo,
        )
        is expected
    )


def test_overlay_mode_defaults_only_when_missing_and_rejects_unknown_values() -> None:
    assert overlay_mode_or_inherit(None) == "inherit"
    for mode in ("inherit", "augment", "override", "deny"):
        assert overlay_mode_or_inherit(mode) == mode
    with pytest.raises(ValueError) as exc_info:
        overlay_mode_or_inherit("delete-global")
    assert str(exc_info.value) == "Unknown Knowledge overlay mode."


@pytest.mark.parametrize(
    ("owner_type", "owner_id", "visibility", "status", "grant", "overlay", "expected"),
    [
        (OWNER_SYSTEM, "system", VISIBILITY_GLOBAL, "active", True, None, True),
        (OWNER_SYSTEM, "system", VISIBILITY_GLOBAL, "active", False, None, False),
        (OWNER_SYSTEM, "system", VISIBILITY_GLOBAL, "active", True, "deny", False),
        (OWNER_SYSTEM, "system", VISIBILITY_GLOBAL, "inactive", True, "inherit", False),
        (OWNER_SYSTEM, "system", "private", "active", True, "inherit", False),
        (OWNER_SERVER, "scope-a", "private", "active", False, "inherit", True),
        (OWNER_SERVER, "scope-b", "private", "active", True, "override", False),
    ],
)
def test_accessible_space_is_filtered_before_any_future_ranking(
    owner_type: str,
    owner_id: str,
    visibility: str,
    status: str,
    grant: bool,
    overlay: str | None,
    expected: bool,
) -> None:
    assert (
        corpus_is_effectively_available(
            owner_type=owner_type,
            owner_id=owner_id,
            visibility=visibility,
            status=status,
            server_scope_id="scope-a",
            global_grant_enabled=grant,
            overlay_mode=overlay,
        )
        is expected
    )


def test_account_lifecycle_only_matches_explicit_user_owner_and_grantee_rows() -> None:
    assert is_user_owned_by(owner_type="user", owner_id="account-a", account_id="account-a")
    assert not is_user_owned_by(owner_type="server", owner_id="account-a", account_id="account-a")
    assert not is_user_owned_by(owner_type="system", owner_id="account-a", account_id="account-a")
    assert not is_user_owned_by(owner_type="user", owner_id="account-b", account_id="account-a")
    assert is_local_user_owned(
        owner_type="user",
        owner_id="local-user",
        local_owner_id="local-user",
    )
    assert not is_local_user_owned(
        owner_type="server",
        owner_id="local-user",
        local_owner_id="local-user",
    )
    assert is_user_grant_for_account(
        grantee_type="user",
        grantee_id="account-a",
        account_id="account-a",
    )
    assert not is_user_grant_for_account(
        grantee_type="server",
        grantee_id="account-a",
        account_id="account-a",
    )
