from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from echo_masque.auth import AuthService, DuplicateAccountError, InvitationError
from echo_masque.config import Settings
from echo_masque.persistence.auth_repository import AuthRepository
from echo_masque.persistence.database import Database
from echo_masque.persistence.models import InvitationRecord

_PASSWORD = "correct horse battery staple"


def _service(tmp_path: Path) -> tuple[Database, AuthRepository, AuthService]:
    database = Database(f"sqlite:///{tmp_path / 'invitations.db'}")
    database.initialize()
    repository = AuthRepository(database)
    service = AuthService(
        repository,
        Settings(
            environment="production",
            database_url=f"sqlite:///{tmp_path / 'invitations.db'}",
            public_registration_enabled=False,
            legacy_local_user_enabled=False,
        ),
    )
    return database, repository, service


def _invitation(
    repository: AuthRepository,
    service: AuthService,
    *,
    email: str | None,
    code: str,
) -> tuple[str, str]:
    invitation = repository.create_invitation(
        code_hash=service.token_digest(code),
        email=email,
        expires_at=datetime.now(UTC) + timedelta(days=1),
    )
    return invitation.id, code


def test_invitation_redemption_is_single_use_across_sequential_attempts(tmp_path: Path) -> None:
    database, repository, service = _service(tmp_path)
    invitation_id, code = _invitation(
        repository, service, email=None, code="review-single-use-code"
    )

    registered = service.register(
        email="first@example.com",
        display_name="First",
        password=_PASSWORD,
        invitation_code=code,
    )
    with pytest.raises(InvitationError):
        service.register(
            email="second@example.com",
            display_name="Second",
            password=_PASSWORD,
            invitation_code=code,
        )

    with database.session() as session:
        invitation = session.get(InvitationRecord, invitation_id)
        assert invitation is not None
        assert invitation.accepted_by == registered.id
        assert invitation.accepted_at is not None
    assert repository.count_users() == 1


def test_rejected_or_failed_invitation_registration_rolls_back_its_claim(tmp_path: Path) -> None:
    database, repository, service = _service(tmp_path)
    rejected_id, rejected_code = _invitation(
        repository,
        service,
        email="allowed@example.com",
        code="review-rejected-code",
    )

    with pytest.raises(InvitationError):
        service.register(
            email="other@example.com",
            display_name="Other",
            password=_PASSWORD,
            invitation_code=rejected_code,
        )

    repository.create_user(
        email="duplicate@example.com",
        display_name="Existing",
        password_hash="unused",
    )
    failed_id, failed_code = _invitation(
        repository,
        service,
        email="duplicate@example.com",
        code="review-failed-code",
    )
    with pytest.raises(DuplicateAccountError):
        service.register(
            email="duplicate@example.com",
            display_name="Duplicate",
            password=_PASSWORD,
            invitation_code=failed_code,
        )

    with database.session() as session:
        rejected = session.get(InvitationRecord, rejected_id)
        failed = session.get(InvitationRecord, failed_id)
        assert rejected is not None
        assert rejected.accepted_at is None
        assert rejected.accepted_by is None
        assert failed is not None and failed.accepted_at is None and failed.accepted_by is None
    assert repository.count_users() == 1
