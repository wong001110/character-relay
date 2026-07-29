from scripts.live_demo_seed import (
    CARD_DRIFT,
    CARD_STABLE,
    CHARACTERS,
    MODEL_KEY_ENV,
    PACK_NAME,
    card_create_payload,
    normalized_base_url,
    scenario_definitions,
    target_payload,
)


def test_live_demo_contract_keeps_two_distinct_characters() -> None:
    assert [item.display_name for item in CHARACTERS] == [CARD_STABLE, CARD_DRIFT]
    assert CHARACTERS[0].temperature == 0.3
    assert CHARACTERS[1].temperature == 1.0
    assert CHARACTERS[0].system_prompt != CHARACTERS[1].system_prompt
    assert PACK_NAME.startswith("LIVE DEMO")


def test_target_uses_environment_subject_key_without_persisting_secret() -> None:
    payload = target_payload(CHARACTERS[0])
    config = payload["config"]
    assert isinstance(config, dict)
    assert config["api_key_env"] == MODEL_KEY_ENV
    assert "api_key" not in config
    assert "password" not in config


def test_bilingual_pack_has_three_scenarios_per_language() -> None:
    scenarios = scenario_definitions()
    assert len(scenarios) == 6
    assert sum(item["language"] == "en" for item in scenarios) == 3
    assert sum(item["language"] == "zh-CN" for item in scenarios) == 3
    assert {item["category"] for item in scenarios} == {
        "identity_integrity",
        "false_memory",
        "prompt_injection",
    }
    assert all(item["max_turns"] == 3 for item in scenarios)
    assert all(item["recommended_tester_mode"] == "adaptive" for item in scenarios)
    assert all(item["recommended_judge_mode"] == "hybrid" for item in scenarios)


def test_card_creation_binds_existing_target_without_raw_key() -> None:
    payload = card_create_payload(CHARACTERS[0], "target-id")
    assert payload["target_id"] == "target-id"
    assert payload["display_name"] == CARD_STABLE
    assert "api_key" not in payload
    assert payload["model"] == "deepseek-v4-flash"


def test_normalized_base_url() -> None:
    assert normalized_base_url(" https://example.up.railway.app/ ") == (
        "https://example.up.railway.app"
    )
