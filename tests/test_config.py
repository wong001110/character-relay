from echo_masque.config import Settings


def test_default_settings_require_no_credentials() -> None:
    settings = Settings(environment="test")
    assert settings.environment == "test"
    assert not hasattr(settings, "api_key")
