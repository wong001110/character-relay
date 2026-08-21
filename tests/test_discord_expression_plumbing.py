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


def test_bot_follow_up_gets_candidates_and_executes_expression_decision() -> None:
    section = between(
        "async function continueBotTagConversation(",
        "async function processInteractionSession(",
    )
    assert "await prepareExpression(" in section
    assert "resolveExpressionSourceMessage(" in section
    assert 'expression_run_id: preparedExpression.retrieval?.run_id ?? ""' in section
    assert "expression_candidates: preparedExpression.retrieval?.candidates ?? []" in section
    assert 'node_name: "model_select"' in section
    assert "await executeCharacterOutput(" in section


def test_interaction_participants_get_independent_expression_decisions() -> None:
    section = between(
        "async function processInteractionSession(",
        "async function processMessage(",
    )
    assert "await prepareExpression(" in section
    assert 'expression_run_id: preparedExpression.retrieval?.run_id ?? ""' in section
    assert "expression_candidates: preparedExpression.retrieval?.candidates ?? []" in section
    assert 'node_name: "model_select"' in section
    assert "await executeCharacterOutput(" in section
