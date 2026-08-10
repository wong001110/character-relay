from pydantic import SecretStr

from echo_masque.config import Settings
from echo_masque.credentials import CredentialVault
from echo_masque.persistence import AuthRepository, Database, KeyGroupRepository, Repository


def _fixture() -> tuple[Database, AuthRepository, Repository, str, str]:
    database = Database("sqlite://")
    database.initialize()
    auth = AuthRepository(database)
    user = auth.create_user(
        user_id="user-1",
        email="user@example.com",
        display_name="User",
        password_hash="hash",
    )
    repository = Repository(database)
    target = repository.create_target(
        name="Character provider",
        target_kind="prompt_model",
        config={
            "name": "Character provider",
            "provider": "openrouter",
            "base_url": "https://openrouter.ai/api/v1",
            "model": "deepseek/example",
            "system_prompt": "Stay in character.",
            "temperature": 0.7,
        },
    )
    card = repository.create_character_card(
        owner_id=user.id,
        target_id=target.id,
        display_name="Mia",
        subtitle="",
        subject_type="custom",
        persona_summary="Test character",
        traits=[],
        tags=[],
        expected_tone=None,
        forbidden_behaviors=[],
        memory_summary=None,
        preferred_suites=[],
        portrait_variant="lavender",
    )
    return database, auth, repository, user.id, card.id


def test_key_group_can_supply_character_credential_with_direct_override() -> None:
    database, auth, _, owner_id, card_id = _fixture()
    groups = KeyGroupRepository(database)
    group = groups.create_group(
        owner_id=owner_id,
        name="OpenRouter Main",
        provider="openrouter",
        base_url="https://openrouter.ai/api/v1",
        default_models={"character": "deepseek/example", "media": "xiaomi/mimo-v2.5"},
    )
    groups.set_assignment(
        owner_id=owner_id,
        character_card_id=card_id,
        capability="character",
        key_group_id=group.id,
    )

    vault = CredentialVault(auth, Settings(environment="test"))
    vault.set_scope(
        owner_id=owner_id,
        scope_kind=CredentialVault.key_group_scope_kind,
        scope_id=group.id,
        value=SecretStr("shared-key"),
        actor_user_id=owner_id,
        resource_type="provider_key_group",
    )

    shared = vault.get(owner_id, card_id)
    assert shared is not None
    assert shared.get_secret_value() == "shared-key"

    vault.set(owner_id, card_id, SecretStr("card-override"))
    direct = vault.get(owner_id, card_id)
    assert direct is not None
    assert direct.get_secret_value() == "card-override"

    vault.delete(owner_id, card_id)
    fallback = vault.get(owner_id, card_id)
    assert fallback is not None
    assert fallback.get_secret_value() == "shared-key"


def test_key_group_resolves_default_and_override_models() -> None:
    database, _, _, owner_id, card_id = _fixture()
    groups = KeyGroupRepository(database)
    group = groups.create_group(
        owner_id=owner_id,
        name="Media",
        provider="xiaomi",
        default_models={"media": "mimo-default"},
    )

    groups.set_assignment(
        owner_id=owner_id,
        character_card_id=card_id,
        capability="media",
        key_group_id=group.id,
    )
    resolved = groups.resolve(
        owner_id=owner_id,
        character_card_id=card_id,
        capability="media",
    )
    assert resolved is not None
    assert resolved.model == "mimo-default"

    groups.set_assignment(
        owner_id=owner_id,
        character_card_id=card_id,
        capability="media",
        key_group_id=group.id,
        model_override="mimo-override",
    )
    overridden = groups.resolve(
        owner_id=owner_id,
        character_card_id=card_id,
        capability="media",
    )
    assert overridden is not None
    assert overridden.model == "mimo-override"
