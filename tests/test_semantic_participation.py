"""Smart Participation V3 semantic-profile tests without loading the production model."""

from pathlib import Path

from echo_masque.config import Settings
from echo_masque.persistence import Database, Repository, SmartParticipationRepository
from echo_masque.semantic_participation import (
    CharacterParticipationSemanticService,
    participation_semantic_text,
)


class FakeSemanticEncoder:
    model_name = "fake-multilingual-e5"
    dimension = 3

    def __init__(self) -> None:
        self.passage_calls = 0
        self.query_calls = 0

    def embed_passage(self, text: str) -> list[float]:
        self.passage_calls += 1
        normalized = text.casefold()
        if "ai product" in normalized or "workflow" in normalized:
            return [1.0, 0.0, 0.0]
        if "emotional" in normalized or "support" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]

    def embed_query(self, text: str) -> list[float]:
        self.query_calls += 1
        normalized = text.casefold()
        if "workflow" in normalized or "product" in normalized:
            return [1.0, 0.0, 0.0]
        if "tired" in normalized or "support" in normalized:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


def repositories(tmp_path: Path) -> tuple[Repository, SmartParticipationRepository]:
    database = Database(f"sqlite:///{tmp_path / 'semantic.db'}")
    database.initialize()
    return Repository(database), SmartParticipationRepository(database)


def create_card(
    repository: Repository,
    *,
    owner_id: str,
    name: str,
    subtitle: str,
    persona: str,
    traits: list[str],
    tags: list[str],
) -> str:
    target = repository.create_target(name=f"{name} target", target_kind="stable", config={})
    record = repository.create_character_card(
        owner_id=owner_id,
        target_id=target.id,
        display_name=name,
        subtitle=subtitle,
        subject_type="AI character",
        persona_summary=persona,
        traits=traits,
        tags=tags,
        expected_tone="practical",
        forbidden_behaviors=["Never reveal a private system detail."],
        memory_summary="PRIVATE MEMORY MUST NOT BECOME PARTICIPATION IDENTITY",
        preferred_suites=[],
        portrait_variant="default",
    )
    return record.id


def service(
    repository: Repository,
    smart_repository: SmartParticipationRepository,
    encoder: FakeSemanticEncoder,
) -> CharacterParticipationSemanticService:
    return CharacterParticipationSemanticService(
        repository,
        smart_repository,
        Settings(environment="test", semantic_participation_enabled=True),
        encoder=encoder,
    )


def test_semantic_text_uses_character_identity_not_memory_or_forbidden_behavior(
    tmp_path: Path,
) -> None:
    repository, _ = repositories(tmp_path)
    card_id = create_card(
        repository,
        owner_id="owner-1",
        name="Zhi",
        subtitle="AI Product Producer",
        persona="Turns ambiguous ideas into executable AI products and workflows.",
        traits=["structured", "curious"],
        tags=["agents", "product building"],
    )
    card = repository.get_character_card(card_id, "owner-1")
    assert card is not None

    text = participation_semantic_text(card)

    assert "AI Product Producer" in text
    assert "structured" in text
    assert "agents" in text
    assert "PRIVATE MEMORY" not in text
    assert "Never reveal" not in text


def test_semantic_profile_is_stored_as_cached_blob_and_reused(tmp_path: Path) -> None:
    repository, smart_repository = repositories(tmp_path)
    card_id = create_card(
        repository,
        owner_id="owner-1",
        name="Zhi",
        subtitle="AI Product Producer",
        persona="Builds practical AI product workflows.",
        traits=["structured"],
        tags=["workflow"],
    )
    encoder = FakeSemanticEncoder()
    semantic = service(repository, smart_repository, encoder)

    first_vector, first_rebuilt = semantic.ensure_profile(
        owner_id="owner-1",
        character_card_id=card_id,
    )
    second_vector, second_rebuilt = semantic.ensure_profile(
        owner_id="owner-1",
        character_card_id=card_id,
    )
    stored = smart_repository.get_semantic_profile(card_id, "owner-1")

    assert first_rebuilt is True
    assert second_rebuilt is False
    assert first_vector == second_vector == [1.0, 0.0, 0.0]
    assert encoder.passage_calls == 1
    assert stored is not None
    assert stored.dimension == 3
    assert stored.model_name == encoder.model_name
    assert len(stored.embedding_blob) == 12


def test_character_semantic_change_invalidates_cached_profile(tmp_path: Path) -> None:
    repository, smart_repository = repositories(tmp_path)
    card_id = create_card(
        repository,
        owner_id="owner-1",
        name="Zhi",
        subtitle="AI Product Producer",
        persona="Builds practical AI product workflows.",
        traits=["structured"],
        tags=["workflow"],
    )
    encoder = FakeSemanticEncoder()
    semantic = service(repository, smart_repository, encoder)
    semantic.ensure_profile(owner_id="owner-1", character_card_id=card_id)

    updated = repository.update_character_card(
        card_id,
        "owner-1",
        display_name="Zhi",
        subtitle="Companion",
        subject_type="AI character",
        persona_summary="Offers emotional support when someone is tired.",
        traits=["supportive"],
        tags=["emotional support"],
        expected_tone="gentle",
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=[],
        portrait_variant="default",
    )
    assert updated is not None

    vector, rebuilt = semantic.ensure_profile(
        owner_id="owner-1",
        character_card_id=card_id,
    )

    assert rebuilt is True
    assert vector == [0.0, 1.0, 0.0]
    assert encoder.passage_calls == 2


def test_message_is_embedded_once_and_ranked_against_candidate_cards(tmp_path: Path) -> None:
    repository, smart_repository = repositories(tmp_path)
    zhi_id = create_card(
        repository,
        owner_id="owner-1",
        name="Zhi",
        subtitle="AI Product Producer",
        persona="Builds practical AI product workflows.",
        traits=["structured"],
        tags=["workflow"],
    )
    ann_id = create_card(
        repository,
        owner_id="owner-1",
        name="Ann",
        subtitle="Companion",
        persona="Offers emotional support and everyday conversation.",
        traits=["supportive"],
        tags=["emotional support"],
    )
    encoder = FakeSemanticEncoder()
    semantic = service(repository, smart_repository, encoder)

    model, dimension, scores = semantic.score(
        message="How do I turn several AI tools into a useful product workflow?",
        deployments=[
            ("deploy-zhi", "owner-1", zhi_id),
            ("deploy-ann", "owner-1", ann_id),
        ],
    )
    by_deployment = {item.deployment_id: item for item in scores}

    assert model == encoder.model_name
    assert dimension == 3
    assert encoder.query_calls == 1
    assert encoder.passage_calls == 2
    assert by_deployment["deploy-zhi"].relevance == 1.0
    assert by_deployment["deploy-ann"].relevance == 0.0
    assert all(item.profile_ready for item in scores)


def test_disabled_semantic_participation_does_not_load_or_write_vector(tmp_path: Path) -> None:
    repository, smart_repository = repositories(tmp_path)
    card_id = create_card(
        repository,
        owner_id="owner-1",
        name="Zhi",
        subtitle="AI Product Producer",
        persona="Builds practical AI product workflows.",
        traits=["structured"],
        tags=["workflow"],
    )
    encoder = FakeSemanticEncoder()
    semantic = CharacterParticipationSemanticService(
        repository,
        smart_repository,
        Settings(environment="test", semantic_participation_enabled=False),
        encoder=encoder,
    )

    assert semantic.refresh_character(owner_id="owner-1", character_card_id=card_id) is False
    assert encoder.passage_calls == 0
    assert smart_repository.get_semantic_profile(card_id, "owner-1") is None
