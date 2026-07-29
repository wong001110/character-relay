from scripts import live_storage_acceptance as acceptance


def test_normalized_base_url() -> None:
    assert acceptance.normalized_base_url("https://example.com/") == "https://example.com"


def test_capture_requires_stable_storage_and_retained_demo(monkeypatch) -> None:
    responses = {
        "/health": {
            "environment": "production",
            "storage": {
                "storage_instance_id": "storage-123",
                "database_path": "/data/echo_masque.db",
                "mount_path": "/data",
                "mount_ready": True,
            },
        },
        "/api/characters": [
            {
                "id": "stable-card",
                "target_id": "stable-target",
                "display_name": acceptance.STABLE_CARD,
            },
            {
                "id": "drift-card",
                "target_id": "drift-target",
                "display_name": acceptance.DRIFT_CARD,
            },
        ],
        "/api/test-packs": [
            {
                "id": "pack-1",
                "name": acceptance.DEMO_PACK,
                "version": 1,
            }
        ],
    }

    monkeypatch.setattr(
        acceptance,
        "request_json",
        lambda _base_url, path: responses[path],
    )

    result = acceptance.capture("https://example.com")

    assert result["storage"]["storage_instance_id"] == "storage-123"
    assert result["retained"] == {
        "stable_card_id": "stable-card",
        "stable_target_id": "stable-target",
        "drift_card_id": "drift-card",
        "drift_target_id": "drift-target",
        "test_pack_id": "pack-1",
        "test_pack_version": 1,
    }
