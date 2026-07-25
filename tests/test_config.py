from echo_masque.config import Settings


def test_settings_read_prefixed_environment(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("ECHO_MASQUE_ENVIRONMENT", "test")
    monkeypatch.setenv("ECHO_MASQUE_DEBUG", "true")

    settings = Settings()

    assert settings.environment == "test"
    assert settings.debug is True
