from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest

from echo_masque.deployment_discovery_intelligence import RankedDiscoveryCandidate
from echo_masque.discovery_contracts import DiscoveryCandidate
from echo_masque.knowledge_gap_discovery_v3 import (
    KnowledgeGapDiscoveryService,
    KnowledgeGapEvidenceAcceptance,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.entity_evidence_repository import (
    EntityEvidenceRepository,
    KnowledgeGapView,
)


@dataclass(frozen=True)
class _Preview:
    ranked: tuple[RankedDiscoveryCandidate, ...]


class _Discovery:
    def __init__(self, preview: _Preview) -> None:
        self.preview = preview

    async def run_knowledge_gap(self, **_: object) -> _Preview:
        return self.preview


class _SlowDiscovery:
    async def run_knowledge_gap(self, **_: object) -> _Preview:
        await asyncio.sleep(0.1)
        return _Preview(())


class _BlockingDiscovery:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def run_knowledge_gap(self, **_: object) -> _Preview:
        self.started.set()
        await self.release.wait()
        return _Preview(())


def _ranked() -> RankedDiscoveryCandidate:
    return RankedDiscoveryCandidate(
        discovery_item_id="item-1",
        candidate=DiscoveryCandidate(
            source="youtube",
            canonical_key="video-1",
            content_kind="video",
            title="Pilot reference",
            description="not durable evidence",
            creator="creator",
            url="https://example.test/video-1",
        ),
        semantic_relevance=0.8,
        sparse_relevance=0.7,
        freshness=0.6,
        novelty=0.5,
        exploration=0.0,
        final_score=0.75,
        reason="test",
    )


def _service(
    tmp_path, discovery: object, *, ttl: timedelta = timedelta(hours=24), timeout: float = 30
) -> tuple[EntityEvidenceRepository, KnowledgeGapDiscoveryService, KnowledgeGapView]:
    database = Database(f"sqlite:///{tmp_path / 'gap-handoff.db'}")
    database.initialize()
    entities = EntityEvidenceRepository(database)
    entity = entities.ensure_entity(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        name="Pilot",
        entity_type="person",
        source_refs=("message:seed",),
    )
    gap = entities.create_gap(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        entity_id=entity.id,
        missing_fields=("identity",),
        triggered_by_ref="message:seed",
        importance=0.75,
    )
    return (
        entities,
        KnowledgeGapDiscoveryService(
            entities=entities,
            discovery=discovery,  # type: ignore[arg-type]
            candidate_ttl=ttl,
            search_timeout_seconds=timeout,
        ),
        gap,
    )


def _search(service: KnowledgeGapDiscoveryService, gap: KnowledgeGapView, *, now: datetime):
    return service.search(
        owner_id="owner-1",
        deployment_id="deployment-1",
        connection_id="connection-1",
        guild_id="guild-1",
        gap=gap,
        now=now,
    )


def test_search_persists_scoped_candidates_and_authorized_acceptance_creates_evidence(
    tmp_path,
) -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    entities, service, gap = _service(tmp_path, _Discovery(_Preview((_ranked(),))))

    result = asyncio.run(_search(service, gap, now=now))

    assert result.status == "candidates_ready"
    assert result.gap.resolution_state == "unresolved"
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.status == "ready"
    assert entities.gap_candidates_for_scope(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap_id=gap.id,
        now=now,
    ) == (candidate,)
    with pytest.raises(ValueError, match="persisted candidate source"):
        service.accept_candidate_evidence(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            deployment_id="deployment-1",
            gap=result.gap,
            acceptance=KnowledgeGapEvidenceAcceptance(
                candidate_id=candidate.id,
                validation_method="operator_review",
                validated_evidence_ref="foreign-evidence:1",
                resolved_fields=("identity",),
                confidence=0.9,
            ),
            reviewed_by="owner-1",
            now=now,
        )

    accepted_gap = service.accept_candidate_evidence(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap=result.gap,
        acceptance=KnowledgeGapEvidenceAcceptance(
            candidate_id=candidate.id,
            validation_method="operator_review",
            validated_evidence_ref="",
            resolved_fields=("identity",),
            confidence=0.9,
            canonical_entity=True,
        ),
        reviewed_by="owner-1",
        now=now + timedelta(seconds=1),
    )

    assert accepted_gap.resolution_state == "resolved"
    accepted = entities.gap_candidate_for_scope(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap_id=gap.id,
        candidate_id=candidate.id,
    )
    assert accepted.status == "accepted"
    edges = entities.edges_for_ref(
        owner_id="owner-1", ref_type="knowledge_gap_candidate", ref=candidate.id
    )
    assert len(edges) == 1
    assert edges[0].evidence_refs == ("discovery_item:item-1",)
    assert edges[0].status == "active"


def test_rejected_or_cross_scope_candidate_cannot_be_accepted(tmp_path) -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    entities, service, gap = _service(tmp_path, _Discovery(_Preview((_ranked(),))))
    candidate = asyncio.run(_search(service, gap, now=now)).candidates[0]

    rejected = service.reject_candidate(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap_id=gap.id,
        candidate_id=candidate.id,
        reviewed_by="owner-1",
        now=now,
    )
    assert rejected.status == "rejected"
    with pytest.raises(ValueError, match="not available"):
        service.accept_candidate_evidence(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            deployment_id="deployment-1",
            gap=gap,
            acceptance=KnowledgeGapEvidenceAcceptance(
                candidate_id=candidate.id,
                validation_method="operator_review",
                validated_evidence_ref="",
                resolved_fields=("identity",),
                confidence=0.9,
            ),
            reviewed_by="owner-1",
            now=now,
        )
    with pytest.raises(KeyError):
        entities.gap_candidate_for_scope(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-2",
            deployment_id="deployment-1",
            gap_id=gap.id,
            candidate_id=candidate.id,
        )


def test_acceptance_and_rejection_race_has_one_terminal_outcome_and_no_orphan_edge(
    tmp_path,
) -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    entities, service, gap = _service(tmp_path, _Discovery(_Preview((_ranked(),))))
    candidate = asyncio.run(_search(service, gap, now=now)).candidates[0]

    def accept() -> str:
        try:
            service.accept_candidate_evidence(
                owner_id="owner-1",
                connection_id="connection-1",
                guild_id="guild-1",
                deployment_id="deployment-1",
                gap=gap,
                acceptance=KnowledgeGapEvidenceAcceptance(
                    candidate_id=candidate.id,
                    validation_method="operator_review",
                    validated_evidence_ref="",
                    resolved_fields=("identity",),
                    confidence=0.9,
                ),
                reviewed_by="owner-1",
                now=now,
            )
            return "accepted"
        except ValueError:
            return "blocked"

    def reject() -> str:
        try:
            service.reject_candidate(
                owner_id="owner-1",
                connection_id="connection-1",
                guild_id="guild-1",
                deployment_id="deployment-1",
                gap_id=gap.id,
                candidate_id=candidate.id,
                reviewed_by="owner-1",
                now=now,
            )
            return "rejected"
        except ValueError:
            return "blocked"

    with ThreadPoolExecutor(max_workers=2) as executor:
        outcomes = {
            future.result() for future in (executor.submit(accept), executor.submit(reject))
        }

    terminal = entities.gap_candidate_for_scope(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap_id=gap.id,
        candidate_id=candidate.id,
    )
    edges = entities.edges_for_ref(
        owner_id="owner-1", ref_type="knowledge_gap_candidate", ref=candidate.id
    )
    assert outcomes in ({"accepted", "blocked"}, {"rejected", "blocked"})
    assert terminal.status in {"accepted", "rejected"}
    assert len(edges) == (1 if terminal.status == "accepted" else 0)


def test_candidate_ttl_and_timeout_end_in_terminal_nonsearching_state(tmp_path) -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    entities, service, gap = _service(
        tmp_path,
        _Discovery(_Preview((_ranked(),))),
        ttl=timedelta(minutes=1),
    )
    candidate = asyncio.run(_search(service, gap, now=now)).candidates[0]

    assert (
        entities.gap_candidates_for_scope(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            deployment_id="deployment-1",
            gap_id=gap.id,
            now=now + timedelta(minutes=2),
        )
        == ()
    )
    expired = entities.gap_candidate_for_scope(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        deployment_id="deployment-1",
        gap_id=gap.id,
        candidate_id=candidate.id,
        now=now + timedelta(minutes=2),
    )
    assert expired.status == "expired"

    timed_path = tmp_path / "timed"
    timed_path.mkdir()
    _entities, timed_service, timed_gap = _service(timed_path, _SlowDiscovery(), timeout=0.01)
    timed = asyncio.run(_search(timed_service, timed_gap, now=now))
    assert timed.status == "timed_out"
    assert timed.gap.resolution_state == "unresolved"


def test_cancelled_search_and_stale_recovery_do_not_leave_searching_state(tmp_path) -> None:
    now = datetime(2026, 9, 7, tzinfo=UTC)
    blocking = _BlockingDiscovery()
    entities, service, gap = _service(tmp_path, blocking)

    async def cancel() -> None:
        task = asyncio.create_task(_search(service, gap, now=now))
        await blocking.started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    asyncio.run(cancel())
    assert (
        entities.gap_for_scope(
            owner_id="owner-1", connection_id="connection-1", guild_id="guild-1", gap_id=gap.id
        ).resolution_state
        == "unresolved"
    )

    entities.mark_gap_searching(
        owner_id="owner-1",
        connection_id="connection-1",
        guild_id="guild-1",
        gap_id=gap.id,
        now=now,
    )
    assert (
        entities.recover_stale_gap_searches(
            owner_id="owner-1",
            connection_id="connection-1",
            guild_id="guild-1",
            stale_before=now + timedelta(seconds=1),
            now=now + timedelta(seconds=2),
        )
        == 1
    )
    assert (
        entities.gap_for_scope(
            owner_id="owner-1", connection_id="connection-1", guild_id="guild-1", gap_id=gap.id
        ).resolution_state
        == "unresolved"
    )
