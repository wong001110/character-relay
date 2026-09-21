"""Additive source metadata and bounded partial-delivery receipts (D03/D08/D10)."""

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from echo_masque.api.connector_schemas import DiscordContextMessage
from echo_masque.api.runtime_durability_schemas import DiscordDeliveryFailureRequest


def test_historical_context_preserves_reply_edit_and_role_identity() -> None:
    value = DiscordContextMessage(
        message_id="m2", author_id="webhook-user", author_display_name="Ann",
        author_deployment_id="ann-deployment", text="reply",
        reply_to_message_id="m1", edited_at=datetime(2026, 9, 21, tzinfo=UTC), is_bot=True,
    )
    restored = DiscordContextMessage.model_validate_json(value.model_dump_json())
    assert restored.reply_to_message_id == "m1"
    assert restored.author_deployment_id == "ann-deployment"
    assert restored.edited_at == datetime(2026, 9, 21, tzinfo=UTC)
    legacy = DiscordContextMessage(message_id="m1", author_id="u1", author_display_name="Ann")
    assert legacy.reply_to_message_id == "" and legacy.author_deployment_id == ""


@pytest.mark.parametrize("ids", [[""], ["x" * 201], [str(i) for i in range(21)]])
def test_partial_receipt_contract_rejects_unbounded_or_empty_ids(ids: list[str]) -> None:
    with pytest.raises(ValidationError):
        DiscordDeliveryFailureRequest(
            connection_id="connection", operation_id="o" * 32, step_id="s" * 32,
            claim_nonce="nonce" * 4, sent_message_ids=ids,
        )


def test_partial_receipts_are_optional_for_existing_connectors() -> None:
    value = DiscordDeliveryFailureRequest(
        connection_id="connection", operation_id="o" * 32, step_id="s" * 32,
        claim_nonce="nonce" * 4,
    )
    assert value.sent_message_ids == []
