from unittest.mock import Mock

from echo_masque.api.routes.health import _credential_ready
from echo_masque.credentials import CredentialStore
from echo_masque.persistence import Repository
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.targets import PromptModelConfig


def test_environment_fallback_counts_as_ready(monkeypatch) -> None:
    config = PromptModelConfig(
        name="Environment Demo",
        provider="deepseek",
        model="deepseek-v4-flash",
        system_prompt="You are Ann.",
        base_url="https://api.deepseek.com",
        api_key_env="ECHO_MASQUE_MODEL_API_KEY",
    )
    target = Mock(spec=TargetRecord)
    target.target_kind = "prompt_model"
    target.config_json = config.model_dump_json()
    card = Mock(spec=CharacterCardRecord)
    card.id = "demo-card"
    card.target_id = "demo-target"
    repository = Mock(spec=Repository)
    repository.get_target.return_value = target
    credential_store = Mock(spec=CredentialStore)
    credential_store.get.return_value = None

    monkeypatch.delenv("ECHO_MASQUE_MODEL_API_KEY", raising=False)
    assert not _credential_ready(repository, credential_store, "public-demo", card)

    monkeypatch.setenv("ECHO_MASQUE_MODEL_API_KEY", "server-side-only")
    assert _credential_ready(repository, credential_store, "public-demo", card)
