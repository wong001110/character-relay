from __future__ import annotations

import json

from pydantic import SecretStr

from echo_masque.knowledge_wiki import KnowledgeWikiService
from echo_masque.persistence import Database, KnowledgeRepository
from echo_masque.persistence.wiki_page_repository import WikiPageRepository
from echo_masque.utility_gateway_contracts import (
    UtilityGatewayUnavailable,
    UtilityInferenceResult,
    UtilityRoute,
    WikiUtilityResult,
)


class FakeWikiGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.prompts: list[str] = []

    def wiki_page(
        self,
        *,
        prompt: str,
    ) -> tuple[WikiUtilityResult, UtilityInferenceResult]:
        self.calls += 1
        self.prompts.append(prompt)
        value = WikiUtilityResult(
            title="Launch overview",
            body="The launch phrase is silver comet.",
            keywords=("launch", "silver comet"),
            confidence=0.91,
        )
        route = UtilityRoute(
            member_id="free-test",
            provider="test-provider",
            model="test-wiki-model",
            base_url="https://example.invalid",
            tier="free",
            api_key=SecretStr("test-key"),
            reason="test",
        )
        return value, UtilityInferenceResult(
            value=value,
            route=route,
            latency_ms=2,
            attempts=1,
        )


class UnavailableWikiGateway:
    def wiki_page(
        self,
        *,
        prompt: str,
    ) -> tuple[WikiUtilityResult, UtilityInferenceResult]:
        del prompt
        raise UtilityGatewayUnavailable("free_pool_exhausted")


def repository() -> KnowledgeRepository:
    database = Database("sqlite://")
    database.initialize()
    return KnowledgeRepository(database, semantic_enabled=False)


def base_with_document(repo: KnowledgeRepository) -> str:
    base = repo.create_base(
        owner_id="owner-1",
        name="Guild launch notes",
        description="Canonical launch information.",
        scope_type="global",
    )
    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base.id,
        title="Launch FAQ",
        content="The launch phrase is silver comet. The launch date is September 3.",
    )
    return base.id


def test_wiki_refresh_persists_provenance_and_reuses_current_source() -> None:
    repo = repository()
    base_id = base_with_document(repo)
    gateway = FakeWikiGateway()
    service = KnowledgeWikiService(repo, gateway=gateway)

    first = service.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )
    second = service.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )

    assert first.status == "created"
    assert first.page is not None
    assert first.provider == "test-provider"
    assert first.model == "test-wiki-model"
    assert first.tier == "free"
    assert second.status == "reused"
    assert second.page is not None
    assert second.page.id == first.page.id
    assert gateway.calls == 1

    manifest = json.loads(first.page.source_manifest_json)
    assert manifest[0]["title"] == "Launch FAQ"
    assert len(manifest[0]["content_sha256"]) == 64
    assert "content" not in manifest[0]


def test_document_change_marks_existing_wiki_stale_and_requires_refresh() -> None:
    repo = repository()
    base_id = base_with_document(repo)
    gateway = FakeWikiGateway()
    service = KnowledgeWikiService(repo, gateway=gateway)

    created = service.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )
    assert created.page is not None
    assert created.page.stale is False

    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        title="Operations note",
        content="Launch support opens at 08:30 UTC.",
    )

    stored = WikiPageRepository(repo.database).get_page(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        page_key="overview",
    )
    assert stored is not None
    assert stored.stale is True
    assert service.current_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    ) is None

    refreshed = service.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )
    assert refreshed.status == "updated"
    assert refreshed.page is not None
    assert refreshed.page.stale is False
    assert refreshed.page.source_hash != created.source_hash
    assert gateway.calls == 2


def test_gateway_failure_keeps_stale_wiki_out_of_current_results() -> None:
    repo = repository()
    base_id = base_with_document(repo)
    initial = KnowledgeWikiService(repo, gateway=FakeWikiGateway())
    created = initial.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )
    assert created.page is not None

    repo.create_document(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        title="Changed source",
        content="A newly added source makes the old overview stale.",
    )
    failed = KnowledgeWikiService(
        repo,
        gateway=UnavailableWikiGateway(),
    ).refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )

    assert failed.status == "gateway_unavailable"
    assert failed.page is None
    assert KnowledgeWikiService(repo).current_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    ) is None

    # Raw Knowledge remains available even though derived Wiki generation failed.
    rag = repo.retrieve_for_turn(
        owner_id="owner-1",
        connection_id="",
        guild_id="",
        channel_id="",
        thread_id="",
        character_card_id="",
        query="newly added source",
    )
    assert rag.candidates


def test_delete_base_removes_derived_wiki_page() -> None:
    repo = repository()
    base_id = base_with_document(repo)
    service = KnowledgeWikiService(repo, gateway=FakeWikiGateway())
    created = service.refresh_overview(
        owner_id="owner-1",
        knowledge_base_id=base_id,
    )
    assert created.page is not None

    assert repo.delete_base(base_id, "owner-1") is True
    assert WikiPageRepository(repo.database).get_page(
        owner_id="owner-1",
        knowledge_base_id=base_id,
        page_key="overview",
    ) is None
