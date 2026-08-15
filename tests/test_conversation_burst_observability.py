from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.api.routes.conversation_burst_observability import (
    conversation_burst_snapshot,
)
from echo_masque.persistence.database import Database
from echo_masque.persistence.deployment_models import (
    DiscordConnectorEventRecord,
    PlatformConnectionRecord,
)


def test_burst_snapshot_combines_live_heartbeat_and_persisted_activity() -> None:
    database = Database("sqlite:///:memory:")
    database.initialize()
    now = datetime.now(UTC)
    metadata = {
        "turn_collector_enabled": True,
        "turn_collector_quiet_window_ms": 3000,
        "turn_collector_max_wait_ms": 10000,
        "turn_collector_max_messages": 5,
        "turn_collector_max_characters": 1500,
        "turn_collector_pending_burst_scope_count": 2,
        "turn_collector_pending_preflight_scope_count": 1,
        "turn_collector_candidate_messages": 14,
        "turn_collector_bypass_messages": 4,
        "turn_collector_bursts": 5,
        "turn_collector_collected_messages": 12,
        "turn_collector_collapsed_messages": 7,
        "turn_collector_interaction_bypasses": 1,
        "turn_collector_bypass_reasons": {"explicit_audience": 3, "reply_reference": 1},
        "turn_collector_last_burst_at": now.isoformat(),
        "turn_collector_last_burst_id": "burst-live",
        "turn_collector_last_flush_reason": "quiet_window",
    }
    with database.session() as session:
        session.add(
            PlatformConnectionRecord(
                id="connection-1",
                owner_id="owner-1",
                platform="discord",
                display_name="Discord Bot",
                connection_mode="managed",
                external_account_id="bot-1",
                status="connected",
                metadata_json=json.dumps(metadata),
                last_seen_at=now,
            )
        )
        session.add(
            DiscordConnectorEventRecord(
                id="event-1",
                owner_id="owner-1",
                connection_id="connection-1",
                level="info",
                event_type="smart_participation_burst_flushed",
                message="burst",
                guild_id="guild-1",
                guild_name="Guild",
                channel_id="channel-1",
                channel_name="general",
                thread_id="",
                thread_name="",
                source_message_id="message-3",
                deployment_id="",
                character_name="",
                details_json=json.dumps(
                    {
                        "burst_id": "burst-persisted",
                        "flush_reason": "quiet_window",
                        "message_count": 3,
                        "author_count": 1,
                        "collapsed_message_count": 2,
                        "collection_latency_ms": 3450,
                    }
                ),
                occurred_at=now,
            )
        )
        session.commit()

    request = cast(
        Any, SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(database=database)))
    )
    result = conversation_burst_snapshot(request, cast(Any, SimpleNamespace(id="admin")))

    assert len(result.connectors) == 1
    connector = result.connectors[0]
    assert connector.effective_config.quiet_window_ms == 3000
    assert connector.effective_config.max_wait_ms == 10000
    assert connector.pending_burst_scopes == 2
    assert connector.pending_preflight_scopes == 1
    assert connector.collapsed_messages == 7
    assert connector.bypass_reasons == {"explicit_audience": 3, "reply_reference": 1}
    assert result.bursts_24h == 1
    assert result.collected_messages_24h == 3
    assert result.collapsed_messages_24h == 2
    assert result.last_persisted_burst is not None
    assert result.last_persisted_burst.burst_id == "burst-persisted"
    assert result.last_persisted_burst.collection_latency_ms == 3450
