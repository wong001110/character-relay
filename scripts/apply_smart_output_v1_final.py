from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one match in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "tests/test_character_prompt_inspector.py",
    'assert prompt["compiler_version"] == "character-relay-compiler-v2"',
    'assert prompt["compiler_version"] == "character-relay-compiler-v3"',
)

replace_once(
    "connectors/discord/src/index.ts",
    """  buildMentionableParticipants,\n  compileSmartMessage,\n  smartOutputResourceCandidate\n""",
    """  buildMentionableParticipants,\n  compileSmartMessage,\n  reserveUniqueCharacterTurn,\n  smartOutputResourceCandidate\n""",
)

replace_once(
    "connectors/discord/src/index.ts",
    """  const eligible = audience.deployments.filter(\n    (deployment) =>\n      !participantsSeen.has(deployment.deployment_id) &&\n      shouldSubmitMessage(\n        deployment,\n      {\n        mentionedBot: true,\n        repliedToBot: false,\n        hasReadableText: Boolean(audience.text || sourceText)\n        },\n        config.smartParticipationEnabled\n      )\n  );\n""",
    """  const eligible = audience.deployments.filter(\n    (deployment) =>\n      !participantsSeen.has(deployment.deployment_id) &&\n      shouldSubmitMessage(\n        deployment,\n        {\n          mentionedBot: true,\n          repliedToBot: false,\n          hasReadableText: Boolean(audience.text || sourceText)\n        },\n        config.smartParticipationEnabled\n      )\n  );\n""",
)

replace_once(
    "connectors/discord/src/index.ts",
    """  for (const [responseIndex, baseDeployment] of eligible.entries()) {\n    if (budget.remainingResponses <= 0) break;\n    budget.remainingResponses -= 1;\n    const deployment = resolveDeploymentLocation(baseDeployment, location);\n""",
    """  for (const [responseIndex, baseDeployment] of eligible.entries()) {\n    if (budget.remainingResponses <= 0) break;\n    if (!reserveUniqueCharacterTurn(participantsSeen, baseDeployment.deployment_id)) {\n      continue;\n    }\n    budget.remainingResponses -= 1;\n    const deployment = resolveDeploymentLocation(baseDeployment, location);\n""",
)

replace_once(
    "connectors/discord/src/index.ts",
    """      depth + 1,\n      budget,\n      new Set([...participantsSeen, turn.deployment.deployment_id])\n""",
    """      depth + 1,\n      budget,\n      participantsSeen\n""",
)

print("Final Smart Output V1 fixes applied.")
