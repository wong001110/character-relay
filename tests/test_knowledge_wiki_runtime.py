from __future__ import annotations

from pydantic import SecretStr

from echo_masque.knowledge_wiki import KnowledgeWikiService
from echo_masque.persistence import Database
from echo_masque.persistence.knowledge_repository import KnowledgeRepository as RawKnowledgeRepository
from echo_masque.persistence.wiki_aware_knowledge_repository import WikiAwareKnowledgeRepository
from echo_masque.utility_gateway_contracts import (
    UtilityGatewayUnavailable,
    UtilityInferenceResult,
    UtilityRoute,
    WikiUtilityResult,
)


class FakeWikiGateway:
    def __init__(self) -> None:
        self.calls = 0

    def wiki_page(
        self,
        *,
        prompt: str,
    ) -> tuple[WikiUtilityResult, UtilityInferenceResult]:
        assert "Guild launch notes" in prompt
        self.calls += 1
        value = WikiUtilityResult(
            title="Guild launch overview",
            body=(
                "The guild launch is a coordinated September release. "
                "The launch phrase is silver comet and support opens before release."
            ),
            keywords=("guild launch", "silver comet", "September"),
            confidence=0.92,
        )
        return value, UtilityInferenceResult(
            value=value,
            route=UtilityRoute(
                member_id="wiki-free",
                provider="test-provider",
                model="test-wiki-model",
                base_url="https://example.invalid",
                tier="free",
                api_key=SecretStr("test-key"),
                reason="test",
            ),
            latency_ms=1,
            attempts=1,
        )


class UnavailableWikiGateway:
    def wiki_page(
        self,
        *,
        prompt: str,
    ) -> tuple[WikiUtilityResult, UtilityInferenceResult]:
        del prompt
        raise UtilityGatewayUnavailable("no_eligible_provider")


def repository() -> WikiAwareKnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    return WikiAwareKnowledgeRepository(database, semantic_enabled=False)


def seed(repo: WikiAwareKnowledgeRepository) -> tuple[str, str]:
    base = repo.create_base(
        owner_id="owner-1",
        name="Guild launch notes",
        description="Canonical information for the guild launch.",
        scope_type="global",
    )
    document = repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Guild launch notes",
        content=(
            "The guild launch date is September 3. The launch phrase is silver comet. "
            "Support opens at 08:30 UTC. This document is the canonical source for exact "
            "launch timing and operational details."
        ),
    )
    return base.id, document.id


def retrieve(repo: WikiAwareKnowledgeRepository, query: str):
    return repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="",
        guild_id="",
        channel_id="",
        thread_id="",
        character_card_id="",
        query=query,
        top_k=4,
    )


def test_overview_query_lazy_builds_then_reuses_compact_wiki() -> None:
    repo = repository()
    seed(repo)
    gateway = FakeWikiGateway()
    repo.set_wiki_service(KnowledgeWikiService(repo, gateway=gateway))

    first = retrieve(repo, "Please give me an overview of the Guild launch notes")
    second = retrieve(repo, "Summarize the Guild launch notes")

    assert first.candidates
    assert first.candidates[0].resource.document_id == "wiki:overview"
    assert first.candidates[0].signals["wiki"] == 1.0
    assert "Provenance:" in first.candidates[0].resource.content
    assert "sha256:" in first.candidates[0].resource.content
    assert second.candidates[0].resource.document_id == "wiki:overview"
    assert gateway.calls == 1


def test_exact_or_evidence_query_keeps_raw_rag_authoritative() -> None:
    repo = repository()
    _, document_id = seed(repo)
    gateway = FakeWikiGateway()
    repo.set_wiki_service(KnowledgeWikiService(repo, gateway=gateway))

    result = retrieve(repo, "What is the exact launch date in the Guild launch notes?")

    assert result.candidates
    assert result.candidates[0].resource.document_id == document_id
    assert result.candidates[0].signals.get("wiki") is None
    assert gateway.calls == 0


def test_stale_overview_is_lazily_rebuilt_on_next_overview_query() -> None:
    repo = repository()
    base_id, _ = seed(repo)
    gateway = FakeWikiGateway()
    repo.set_wiki_service(KnowledgeWikiService(repo, gateway=gateway))

    first = retrieve(repo, "Give me a summary of the Guild launch notes")
    assert first.candidates[0].resource.document_id == "wiki:overview"
    assert gateway.calls == 1

    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        title="Guild launch support update",
        content="Support coverage now also includes the September 4 follow-up window.",
    )
    second = retrieve(repo, "Give me an overview of the Guild launch notes")

    assert second.candidates[0].resource.document_id == "wiki:overview"
    assert gateway.calls == 2


def test_wiki_failure_falls_back_to_unmodified_raw_candidates() -> None:
    repo = repository()
    _, document_id = seed(repo)
    repo.set_wiki_service(KnowledgeWikiService(repo, gateway=UnavailableWikiGateway()))

    result = retrieve(repo, "Give me an overview of the Guild launch notes")

    assert result.candidates
    assert result.candidates[0].resource.document_id == document_id
    assert result.candidates[0].signals.get("wiki") is None


def test_wiki_overview_reduces_context_size_relative_to_multi_chunk_raw_rag() -> None:
    repo = repository()
    base_id, _ = seed(repo)
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        title="Guild launch operations",
        content=("Guild launch operations and support details. " * 120).strip(),
    )
    gateway = FakeWikiGateway()
    repo.set_wiki_service(KnowledgeWikiService(repo, gateway=gateway))

    query = "Give me an overview of the Guild launch notes and launch operations"
    wiki_result = retrieve(repo, query)
    raw_repo = RawKnowledgeRepository(repo.database, semantic_enabled=False)
    raw_result = raw_repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="",
        guild_id="",
        channel_id="",
        thread_id="",
        character_card_id="",
        query=query,
        top_k=4,
    )

    wiki_chars = sum(len(item.resource.content) for item in wiki_result.candidates)
    raw_chars = sum(len(item.resource.content) for item in raw_result.candidates)
    assert wiki_result.candidates[0].resource.document_id == "wiki:overview"
    assert raw_chars > wiki_chars
