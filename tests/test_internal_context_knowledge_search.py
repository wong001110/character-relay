from __future__ import annotations

import json
from pathlib import Path
from typing import cast

from echo_masque.internal_context import INTERNAL_CONTEXT_TOOL_IDS, InternalContextService
from echo_masque.knowledge_fabric_context import KnowledgeContextBuilder
from echo_masque.knowledge_fabric_epistemic_policy import DenyAllCharacterEpistemicPolicy
from echo_masque.knowledge_fabric_query import (
    KnowledgeQueryEngine,
    KnowledgeQueryHit,
    KnowledgeQueryRequest,
    KnowledgeQueryResult,
)
from echo_masque.persistence.belief_repository import BeliefRepository
from echo_masque.persistence.conversation_runtime_repository import ConversationRuntimeRepository
from echo_masque.persistence.conversation_structure_repository import (
    ConversationStructureRepository,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.knowledge_fabric_repository import KnowledgeFabricRepository
from echo_masque.tool_runtime import ToolExecutionContext


class _RecordingQueryEngine:
    def __init__(self) -> None:
        self.requests: list[KnowledgeQueryRequest] = []

    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResult:
        self.requests.append(request)
        return KnowledgeQueryResult(
            mode="overview",
            accessible_corpus_count=1,
            freshness_status="not_requested",
            hits=(
                KnowledgeQueryHit(
                    evidence_unit_id="evidence-visible",
                    corpus_id="corpus-visible",
                    source_version_id="source-version-visible",
                    evidence_locator="https://private.example.test/locator-must-not-leak",
                    document_title="Visible handbook",
                    text_content="Only the admitted Fabric evidence is available.",
                    authority_profile="canonical",
                    channels=("sparse",),
                ),
            ),
        )


class _UnavailableQueryEngine(_RecordingQueryEngine):
    def query(self, request: KnowledgeQueryRequest) -> KnowledgeQueryResult:
        self.requests.append(request)
        raise RuntimeError("query unavailable")


class _AllowEvidence:
    def allows(self, **_: str) -> bool:
        return True


def _context() -> ToolExecutionContext:
    return ToolExecutionContext(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="card-1",
        platform="discord",
        connection_id="connection-1",
        guild_id="guild-1",
    )


def _service(
    tmp_path: Path,
    *,
    query_engine: object,
    epistemic_policy: object,
    create_scope: bool = True,
) -> tuple[InternalContextService, _RecordingQueryEngine, KnowledgeFabricRepository]:
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = Database(f"sqlite:///{tmp_path / 'internal-knowledge-search.db'}")
    database.initialize()
    fabric = KnowledgeFabricRepository(database)
    if create_scope:
        fabric.ensure_server_scope(
            platform="discord",
            connection_id="connection-1",
            workspace_id="guild-1",
        )
    service = InternalContextService(
        belief_repository=BeliefRepository(database),
        structure_repository=ConversationStructureRepository(database),
        runtime_repository=ConversationRuntimeRepository(database),
        knowledge_context=KnowledgeContextBuilder(
            fabric_repository=fabric,
            query_engine=cast(KnowledgeQueryEngine, query_engine),
            epistemic_policy=cast(DenyAllCharacterEpistemicPolicy, epistemic_policy),
        ),
    )
    return service, cast(_RecordingQueryEngine, query_engine), fabric


def test_knowledge_search_uses_admitted_fabric_evidence_without_raw_locator(tmp_path: Path) -> None:
    engine = _RecordingQueryEngine()
    service, _engine, _fabric = _service(
        tmp_path,
        query_engine=engine,
        epistemic_policy=_AllowEvidence(),
    )

    result = json.loads(
        service.execute("knowledge.search", {"query": "handbook", "limit": 3}, _context())
    )

    assert INTERNAL_CONTEXT_TOOL_IDS == (
        "memory.search",
        "conversation.search",
        "knowledge.search",
    )
    assert engine.requests[0].mode == "overview"
    assert engine.requests[0].candidate_limit == 3
    assert engine.requests[0].result_limit == 3
    assert result["available"] is True
    assert result["count"] == 1
    encoded = json.dumps(result)
    assert "UNTRUSTED KNOWLEDGE EVIDENCE" in encoded
    assert "evidence_locator" not in encoded
    assert "locator-must-not-leak" not in encoded
    assert result["results"][0]["ref"] == "evidence:evidence-visible"
    assert result["results"][0]["source_version_id"] == "source-version-visible"


def test_knowledge_search_fails_closed_for_epistemic_denial_or_unavailable_query(
    tmp_path: Path,
) -> None:
    denied_engine = _RecordingQueryEngine()
    denied_service, _engine, _fabric = _service(
        tmp_path / "denied",
        query_engine=denied_engine,
        epistemic_policy=DenyAllCharacterEpistemicPolicy(),
    )
    denied = json.loads(
        denied_service.execute("knowledge.search", {"query": "handbook", "limit": 2}, _context())
    )

    unavailable_engine = _UnavailableQueryEngine()
    unavailable_service, _engine, _fabric = _service(
        tmp_path / "unavailable",
        query_engine=unavailable_engine,
        epistemic_policy=_AllowEvidence(),
    )
    unavailable = json.loads(
        unavailable_service.execute(
            "knowledge.search",
            {"query": "handbook", "limit": 2},
            _context(),
        )
    )

    assert denied["available"] is True
    assert denied["results"] == []
    assert "Visible handbook" not in json.dumps(denied)
    assert "evidence-visible" not in json.dumps(denied)
    assert unavailable["available"] is False
    assert unavailable["results"] == []


def test_knowledge_search_unknown_scope_does_not_create_state_or_query(tmp_path: Path) -> None:
    engine = _RecordingQueryEngine()
    service, _engine, fabric = _service(
        tmp_path,
        query_engine=engine,
        epistemic_policy=_AllowEvidence(),
        create_scope=False,
    )

    result = json.loads(
        service.execute("knowledge.search", {"query": "handbook", "limit": 2}, _context())
    )

    assert result["available"] is False
    assert result["results"] == []
    assert engine.requests == []
    assert fabric.list_server_scopes() == []
    try:
        service.execute("wiki.lookup", {"query": "handbook", "limit": 2}, _context())
    except ValueError as exc:
        assert str(exc) == "Unknown Internal Context Tool."
    else:
        raise AssertionError("Retired internal Tool ID must not be executable.")
