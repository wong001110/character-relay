from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "connectors/discord/src/index.ts"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, got {count}")
    return text.replace(old, new, 1)


def main() -> None:
    text = INDEX.read_text(encoding="utf-8")

    text = replace_once(
        text,
        'import { DiscordEventReporter } from "./eventReporter.js";\n',
        'import { DiscordEventReporter } from "./eventReporter.js";\n'
        'import {\n'
        '  CharacterContextTurnIntelligenceMetrics,\n'
        '  hasCharacterContextTurnIntelligenceActivity\n'
        '} from "./turnIntelligenceTelemetry.js";\n',
        "telemetry import",
    )

    text = replace_once(
        text,
        'const context = new ContextBuffer(config.maxContextMessages);\n',
        'const context = new ContextBuffer(config.maxContextMessages);\n'
        'const characterContextTurnIntelligenceMetrics =\n'
        '  new CharacterContextTurnIntelligenceMetrics();\n',
        "telemetry metrics instance",
    )

    text = replace_once(
        text,
        '  const details = {\n'
        '    rag_status: trace.rag_status,\n',
        '  const turnIntelligence = characterContextTurnIntelligenceMetrics.observe(trace);\n'
        '  const details = {\n'
        '    rag_status: trace.rag_status,\n',
        "observe trace",
    )

    text = replace_once(
        text,
        '    knowledge_token_budget: trace.knowledge_token_budget,\n'
        '    selected: trace.selected\n'
        '  };\n',
        '    knowledge_token_budget: trace.knowledge_token_budget,\n'
        '    turn_intelligence_mode: turnIntelligence.mode,\n'
        '    turn_intelligence_requested_tasks: turnIntelligence.requestedTasks,\n'
        '    turn_intelligence_knowledge_source: turnIntelligence.knowledgeSource,\n'
        '    turn_intelligence_pending_action_source: turnIntelligence.pendingActionSource,\n'
        '    turn_intelligence_knowledge_route: turnIntelligence.knowledgeRoute,\n'
        '    turn_intelligence_pending_action_continue:\n'
        '      turnIntelligence.pendingActionContinue,\n'
        '    selected: trace.selected\n'
        '  };\n',
        "trace event details",
    )

    text = replace_once(
        text,
        '    ...common,\n'
        '    details\n'
        '  });\n'
        '}\n\n'
        'async function syncServerCatalog(): Promise<void> {\n',
        '    ...common,\n'
        '    details\n'
        '  });\n'
        '  if (hasCharacterContextTurnIntelligenceActivity(turnIntelligence)) {\n'
        '    reportDiscordEvent({\n'
        '      level:\n'
        '        turnIntelligence.knowledgeSource === "legacy_fallback" ||\n'
        '        turnIntelligence.pendingActionSource === "legacy_fallback"\n'
        '          ? "warning"\n'
        '          : "info",\n'
        '      eventType: "turn_intelligence_character_context",\n'
        '      message:\n'
        '        "Character context routing recorded a bounded Turn Intelligence decision.",\n'
        '      ...common,\n'
        '      details: {\n'
        '        mode: turnIntelligence.mode,\n'
        '        requested_tasks: turnIntelligence.requestedTasks,\n'
        '        knowledge_source: turnIntelligence.knowledgeSource,\n'
        '        knowledge_route: turnIntelligence.knowledgeRoute,\n'
        '        pending_action_source: turnIntelligence.pendingActionSource,\n'
        '        pending_action_continue: turnIntelligence.pendingActionContinue\n'
        '      }\n'
        '    });\n'
        '  }\n'
        '}\n\n'
        'async function syncServerCatalog(): Promise<void> {\n',
        "turn intelligence event",
    )

    text = replace_once(
        text,
        '      smart_participation_enabled: config.smartParticipationEnabled,\n',
        '      smart_participation_enabled: config.smartParticipationEnabled,\n'
        '      ...characterContextTurnIntelligenceMetrics.healthSnapshot(),\n',
        "health metrics",
    )

    INDEX.write_text(text, encoding="utf-8")


if __name__ == "__main__":
    main()
