"""Synthetic API-to-delivery replay harness for representative Discord Runtime turns."""

from pathlib import Path

from fastapi.testclient import TestClient
from test_discord_connector import (  # type: ignore[import-not-found]
    connector_headers,
    inbound_payload,
    seed_deployment,
    settings,
)

from echo_masque.api import create_app


def test_normal_discord_journey_uses_context_and_durable_delivery_claims(tmp_path: Path) -> None:
    """Exercise ingress, supplied context, ConnectorRuntime, durable reply, and delivery."""
    app = create_app(settings(tmp_path / "journey.db"))
    client = TestClient(app)
    connection, deployment = seed_deployment(client)
    first = inbound_payload(
        connection,
        deployment,
        message_id="journey-1",
        text="Ann, remember blue?",
        mentioned_bot=True,
    )
    first["recent_messages"] = [
        {**first["recent_messages"][0], "text": "I prefer blue."},  # type: ignore[index]
    ]
    response = client.post(
        "/api/connectors/discord/messages", headers=connector_headers(), json=first
    )
    assert response.status_code == 200, response.text
    reply = response.json()
    assert reply["action"] == "reply"
    assert reply["delivery_required"] is True
    assert reply["operation_id"] and reply["step_id"]
    claim = client.post(
        "/api/connectors/discord/messages/delivery/claim",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "operation_id": reply["operation_id"],
            "step_id": reply["step_id"],
            "claim_nonce": "journey-delivery-nonce",
        },
    )
    assert claim.status_code == 200, claim.text
    acknowledged = client.post(
        "/api/connectors/discord/messages/delivery/ack",
        headers=connector_headers(),
        json={
            "connection_id": connection["id"],
            "operation_id": reply["operation_id"],
            "step_id": reply["step_id"],
            "claim_nonce": "journey-delivery-nonce",
            "sent_message_ids": ["synthetic-discord-message"],
        },
    )
    assert acknowledged.status_code == 204, acknowledged.text
    replay = client.post(
        "/api/connectors/discord/messages", headers=connector_headers(), json=first
    )
    assert replay.status_code == 200
    assert replay.json()["operation_id"] == reply["operation_id"]
    assert replay.json()["durable_status"] == "delivered"

    denied = {**first, "channel_id": "other-channel", "channel_name": "other"}
    denied_response = client.post(
        "/api/connectors/discord/messages", headers=connector_headers(), json=denied
    )
    assert denied_response.status_code == 200
    assert denied_response.json()["reason"] == "no_active_deployment"
