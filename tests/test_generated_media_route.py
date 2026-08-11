from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import SecretStr

from echo_masque.api.routes.generated_media import router as generated_media_router
from echo_masque.persistence import Database, GeneratedMediaArtifactRepository

_PNG = b"\x89PNG\r\n\x1a\n" + b"generated-route"


def app_and_artifact() -> tuple[FastAPI, str, str]:
    database = Database("sqlite://")
    database.initialize()
    repository = GeneratedMediaArtifactRepository(database)
    artifact = repository.create(
        owner_id="owner-1",
        deployment_id="deployment-1",
        character_card_id="card-ann",
        media_key="sha256:route-test",
        mime_type="image/png",
        filename="generated.png",
        provider="fake",
        model="fake-image",
        content=_PNG,
    )
    app = FastAPI()
    app.state.settings = SimpleNamespace(
        connector_shared_secret=SecretStr("connector-secret")
    )
    app.state.generated_media_repository = repository
    app.include_router(generated_media_router, prefix="/api/connectors/discord")
    return app, artifact.id, artifact.media_key


def test_generated_media_route_requires_connector_authentication() -> None:
    app, artifact_id, _ = app_and_artifact()
    client = TestClient(app)

    response = client.get(
        f"/api/connectors/discord/generated-media/{artifact_id}",
        params={"deployment_id": "deployment-1"},
    )

    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"


def test_generated_media_route_scopes_artifact_to_deployment() -> None:
    app, artifact_id, _ = app_and_artifact()
    client = TestClient(app)

    response = client.get(
        f"/api/connectors/discord/generated-media/{artifact_id}",
        params={"deployment_id": "deployment-other"},
        headers={"Authorization": "Bearer connector-secret"},
    )

    assert response.status_code == 404


def test_generated_media_route_returns_private_binary_artifact() -> None:
    app, artifact_id, media_key = app_and_artifact()
    client = TestClient(app)

    response = client.get(
        f"/api/connectors/discord/generated-media/{artifact_id}",
        params={"deployment_id": "deployment-1"},
        headers={"Authorization": "Bearer connector-secret"},
    )

    assert response.status_code == 200
    assert response.content == _PNG
    assert response.headers["content-type"].startswith("image/png")
    assert response.headers["cache-control"] == "private, no-store"
    assert response.headers["x-character-relay-media-key"] == media_key
    assert 'filename="generated.png"' in response.headers["content-disposition"]
