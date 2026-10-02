from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = (ROOT / "connectors/discord/src/index.ts").read_text(encoding="utf-8")


def between(start: str, end: str) -> str:
    return INDEX.split(start, maxsplit=1)[1].split(end, maxsplit=1)[0]


def test_expression_limit_is_per_character_reply_not_per_trigger() -> None:
    assert "let expressionBudget = 1;" not in INDEX
    assert "expressionBudget -= 1" not in INDEX
    assert "expression_max_per_trigger: 1" not in INDEX
    assert "expression_max_per_character_reply: 1" in INDEX


def test_one_durable_group_path_without_eager_expression_retrieval() -> None:
    section = between("async function processMessage(", "async function resumePendingSocialTurns(")
    assert "relay.processSocialTurnStep(" in section
    assert "await executeSmartOutput(" in section
    assert "await executeCharacterOutput(" in section
    assert "retrieveExpressions(" not in INDEX
    assert "prepareExpression(" not in INDEX
    assert "expression_candidates:" not in INDEX
    assert "expression_run_id:" not in INDEX


def test_retired_activity_and_selector_consumers_are_absent() -> None:
    assert "continueBotTagConversation(" not in INDEX
    assert "processInteractionSession(" not in INDEX
    assert "claimInteraction(" not in INDEX
    assert "legacyQueue" not in INDEX
    assert "normalDelivery" not in INDEX
