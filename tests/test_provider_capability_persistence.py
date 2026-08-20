from __future__ import annotations

from echo_masque.persistence import Database
from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.provider_capability_persistence import ProviderCapabilityPersistence


def test_capability_observation_survives_registry_restart() -> None:
    database = Database("sqlite://")
    database.initialize()
    store = ProviderCapabilityPersistence(database)
    ProviderModelCapabilityRegistry.reset_for_test()
    ProviderModelCapabilityRegistry.configure_persistence(store)

    ProviderModelCapabilityRegistry.observe(
        provider="gemini",
        model="Gemini-Test",
        base_url="https://generativelanguage.googleapis.com/v1beta/openai",
        capability="remote_image_url",
        supported=False,
        detail="remote URL rejected",
    )
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="gemini",
            model="Gemini-Test",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            capability="remote_image_url",
        )
        == "unsupported"
    )

    ProviderModelCapabilityRegistry.reset_for_test()
    ProviderModelCapabilityRegistry.configure_persistence(
        ProviderCapabilityPersistence(database)
    )
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="gemini",
            model="Gemini-Test",
            base_url="https://generativelanguage.googleapis.com/v1beta/openai",
            capability="remote_image_url",
        )
        == "unsupported"
    )
    hydrated = ProviderModelCapabilityRegistry.snapshot(provider="gemini")
    assert len(hydrated) == 1
    assert hydrated[0].detail == "remote URL rejected"

    ProviderModelCapabilityRegistry.reset_for_test()


def test_capability_persistence_is_model_and_endpoint_scoped() -> None:
    database = Database("sqlite://")
    database.initialize()
    ProviderModelCapabilityRegistry.reset_for_test()
    ProviderModelCapabilityRegistry.configure_persistence(
        ProviderCapabilityPersistence(database)
    )

    ProviderModelCapabilityRegistry.observe(
        provider="cloudflare",
        model="model-a",
        base_url="https://api.cloudflare.example/v1",
        capability="json_schema",
        supported=False,
    )

    assert (
        ProviderModelCapabilityRegistry.status(
            provider="cloudflare",
            model="model-a",
            base_url="https://api.cloudflare.example/v1",
            capability="json_schema",
        )
        == "unsupported"
    )
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="cloudflare",
            model="model-b",
            base_url="https://api.cloudflare.example/v1",
            capability="json_schema",
        )
        == "unknown"
    )
    assert (
        ProviderModelCapabilityRegistry.status(
            provider="cloudflare",
            model="model-a",
            base_url="https://api.cloudflare.example/other/v1",
            capability="json_schema",
        )
        == "unknown"
    )

    ProviderModelCapabilityRegistry.reset_for_test()
