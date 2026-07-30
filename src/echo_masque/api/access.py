"""Server-enforced access helpers for user-owned and public deterministic runs."""

from __future__ import annotations

from typing import cast

from fastapi import HTTPException, Request, status

from echo_masque.api.schemas import TrialStart
from echo_masque.auth import AuthContext
from echo_masque.domain import JudgeMode
from echo_masque.persistence import WorkspaceRepository
from echo_masque.workspace import RunSnapshotView

PUBLIC_SMOKE_OWNER = "public-smoke"
_PUBLIC_TARGETS = {"demo-stable", "demo-fragile"}


def workspace_repository(request: Request) -> WorkspaceRepository:
    return cast(WorkspaceRepository, request.app.state.workspace_repository)


def is_public_deterministic_trial(payload: TrialStart) -> bool:
    """Return whether an anonymous request is restricted to secret-free demo execution."""

    return bool(
        payload.target_id in _PUBLIC_TARGETS
        and payload.character_card_id is None
        and payload.test_pack_id is None
        and payload.tester_mode == "benchmark"
        and payload.judge_mode == JudgeMode.RULES
        and payload.adaptive_tester is None
        and payload.suite
    )


def owner_for_trial_start(payload: TrialStart, context: AuthContext | None) -> str:
    if context is not None:
        return context.user.id
    if is_public_deterministic_trial(payload):
        return PUBLIC_SMOKE_OWNER
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required.",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_run_access(
    request: Request,
    run_id: str,
    context: AuthContext | None,
    *,
    allow_public: bool = True,
) -> RunSnapshotView:
    """Hide private Run existence unless the authenticated user owns its snapshot."""

    snapshot = workspace_repository(request).get_run_snapshot(run_id)
    if snapshot is None:
        raise HTTPException(status_code=404, detail="Trial not found.")
    if context is not None and snapshot.owner_id == context.user.id:
        return snapshot
    if allow_public and snapshot.owner_id == PUBLIC_SMOKE_OWNER:
        return snapshot
    raise HTTPException(status_code=404, detail="Trial not found.")
