from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from echo_masque.api.app import create_app
from echo_masque.config import Settings


def settings(path: Path) -> Settings:
    return Settings(environment="test", database_url=f"sqlite:///{path}")


@pytest.mark.parametrize(
    "path",
    [
        "/characters",
        "/characters/new",
        "/characters/character-id",
        "/characters/character-id/persona",
        "/characters/character-id/prompt",
        "/characters/character-id/prompt/inspect",
        "/characters/character-id/memory",
        "/characters/character-id/runtime",
        "/characters/character-id/deployments",
        "/characters/character-id/edit",
        "/characters/character-id/test",
        "/deployments",
        "/deployments/server-profile/characters",
        "/deployments/server-profile/knowledge",
        "/deployments/server-profile/interactions",
        "/deployments/server-profile/intelligence/conversation",
        "/toolbox",
        "/settings",
        "/dev/ui",
    ],
)
def test_client_deep_link_serves_the_portal_entry_document(tmp_path: Path, path: str) -> None:
    client = TestClient(create_app(settings(tmp_path / "portal.db")))

    response = client.get(path)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    assert '<div id="root"></div>' in response.text


def test_unknown_api_route_is_not_converted_into_a_portal_route(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "api.db")))

    response = client.get("/api/not-a-route")

    assert response.status_code == 404


def test_unknown_character_subroute_is_not_converted_into_a_portal_route(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "unknown-character-route.db")))

    response = client.get("/characters/character-id/not-a-route")

    assert response.status_code == 404


def test_unknown_deployment_subroute_is_not_converted_into_a_portal_route(tmp_path: Path) -> None:
    client = TestClient(create_app(settings(tmp_path / "unknown-deployment-route.db")))

    response = client.get("/deployments/server-profile/not-a-route")

    assert response.status_code == 404
