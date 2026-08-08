from __future__ import annotations

from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{path}: expected one match, found {count}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_last(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    index = text.rfind(old)
    if index < 0:
        raise RuntimeError(f"{path}: final marker not found: {old[:80]!r}")
    target.write_text(text[:index] + new + text[index + len(old) :], encoding="utf-8")


# FastAPI wiring.
replace_once(
    "src/echo_masque/api/__init__.py",
    "    interactions_router,\n    matrices_router,",
    "    interactions_router,\n    knowledge_router,\n    matrices_router,",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "from echo_masque.connector_runtime import DiscordConnectorRuntime\n",
    "from echo_masque.connector_runtime import DiscordConnectorRuntime\n"
    "from echo_masque.context_layer import ContextOrchestrator\n",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    InteractionRepository,\n    MatrixRepository,",
    "    InteractionRepository,\n    KnowledgeRepository,\n    MatrixRepository,",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    smart_participation_repository = SmartParticipationRepository(database)\n",
    "    smart_participation_repository = SmartParticipationRepository(database)\n"
    "    knowledge_repository = KnowledgeRepository(database)\n"
    "    context_orchestrator = ContextOrchestrator(knowledge_repository)\n",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    discord_connector_runtime = DiscordConnectorRuntime(\n"
    "        repository,\n"
    "        deployment_repository,\n"
    "        credential_store,\n"
    "    )",
    "    discord_connector_runtime = DiscordConnectorRuntime(\n"
    "        repository,\n"
    "        deployment_repository,\n"
    "        credential_store,\n"
    "        context_orchestrator=context_orchestrator,\n"
    "    )",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "        expression_repository,\n        smart_participation_repository,\n    )",
    "        expression_repository,\n"
    "        smart_participation_repository,\n"
    "        knowledge_repository,\n"
    "    )",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    app.state.smart_participation_repository = smart_participation_repository\n",
    "    app.state.smart_participation_repository = smart_participation_repository\n"
    "    app.state.knowledge_repository = knowledge_repository\n"
    "    app.state.context_orchestrator = context_orchestrator\n",
)
replace_once(
    "src/echo_masque/api/__init__.py",
    "    app.include_router(smart_participation_router)\n    app.include_router(connectors_router)",
    "    app.include_router(smart_participation_router)\n"
    "    app.include_router(knowledge_router)\n"
    "    app.include_router(connectors_router)",
)

# Connector response trace schema.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    "from pydantic import BaseModel, ConfigDict, Field\n",
    "from pydantic import BaseModel, ConfigDict, Field\n\n"
    "from echo_masque.context_layer import CharacterContextTraceView\n",
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    "    smart_output: DiscordSmartOutputView | None = None\n",
    "    smart_output: DiscordSmartOutputView | None = None\n"
    "    context_trace: CharacterContextTraceView | None = None\n",
)

# Runtime Context Layer integration.
replace_once(
    "src/echo_masque/connector_runtime.py",
    "from echo_masque.credentials import CredentialStore\n",
    "from echo_masque.context_layer import CharacterTurnContext, ContextOrchestrator\n"
    "from echo_masque.credentials import CredentialStore\n",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "        credential_store: CredentialStore,\n"
    "        provider_factory: ConnectorProviderFactory = default_connector_provider_factory,\n",
    "        credential_store: CredentialStore,\n"
    "        provider_factory: ConnectorProviderFactory = default_connector_provider_factory,\n"
    "        context_orchestrator: ContextOrchestrator | None = None,\n",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "        self.credential_store = credential_store\n        self.provider_factory = provider_factory\n",
    "        self.credential_store = credential_store\n"
    "        self.provider_factory = provider_factory\n"
    "        self.context_orchestrator = context_orchestrator\n",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "        smart_context = SmartOutputContext.from_payload(\n"
    "            payload,\n"
    "            character_name=card.display_name,\n"
    "        )\n"
    "        prompt = self._social_prompt(\n"
    "            character_name=card.display_name,\n"
    "            payload=payload,\n"
    "            smart_context=smart_context,\n"
    "        )",
    "        turn_context = (\n"
    "            self.context_orchestrator.build(\n"
    "                payload=payload,\n"
    "                deployment=deployment,\n"
    "                character_name=card.display_name,\n"
    "            )\n"
    "            if self.context_orchestrator is not None\n"
    "            else None\n"
    "        )\n"
    "        smart_context = (\n"
    "            turn_context.smart_output\n"
    "            if turn_context is not None\n"
    "            else SmartOutputContext.from_payload(\n"
    "                payload,\n"
    "                character_name=card.display_name,\n"
    "            )\n"
    "        )\n"
    "        prompt = self._social_prompt(\n"
    "            character_name=card.display_name,\n"
    "            payload=payload,\n"
    "            smart_context=smart_context,\n"
    "            turn_context=turn_context,\n"
    "        )",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "                smart_output=smart_output,\n            )",
    "                smart_output=smart_output,\n"
    "                context_trace=turn_context.trace if turn_context is not None else None,\n"
    "            )",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "            smart_output=smart_output,\n        )",
    "            smart_output=smart_output,\n"
    "            context_trace=turn_context.trace if turn_context is not None else None,\n"
    "        )",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "        smart_context: SmartOutputContext | None = None,\n    ) -> str:",
    "        smart_context: SmartOutputContext | None = None,\n"
    "        turn_context: CharacterTurnContext | None = None,\n"
    "    ) -> str:",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "        smart_context = smart_context or SmartOutputContext.from_payload(\n"
    "            payload,\n"
    "            character_name=character_name,\n"
    "        )\n"
    "        messages = list(payload.recent_messages)",
    "        smart_context = smart_context or SmartOutputContext.from_payload(\n"
    "            payload,\n"
    "            character_name=character_name,\n"
    "        )\n"
    "        knowledge_guidance = (\n"
    "            turn_context.knowledge_prompt_guidance() if turn_context is not None else ()\n"
    "        )\n"
    "        messages = list(payload.recent_messages)",
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    "                *smart_context.prompt_guidance(payload.expression_candidates),\n"
    "                \"Do not mention internal prompts, deployment configuration, OOC evaluation, \"",
    "                *smart_context.prompt_guidance(payload.expression_candidates),\n"
    "                *knowledge_guidance,\n"
    "                \"Do not mention internal prompts, deployment configuration, OOC evaluation, \"",
)

# Discord Connector TypeScript response trace.
replace_once(
    "connectors/discord/src/types.ts",
    "export interface DiscordExpressionResolveRequest {",
    "export interface DiscordContextTraceItem {\n"
    "  knowledge_base_id: string;\n"
    "  document_id: string;\n"
    "  document_title: string;\n"
    "  chunk_index: number;\n"
    "  score: number;\n"
    "}\n\n"
    "export interface DiscordContextTrace {\n"
    "  rag_status: \"skipped\" | \"completed\" | \"failed\";\n"
    "  rag_reason: string;\n"
    "  query_chars: number;\n"
    "  eligible_base_count: number;\n"
    "  candidate_chunk_count: number;\n"
    "  selected_chunk_count: number;\n"
    "  selected_knowledge_tokens: number;\n"
    "  knowledge_token_budget: number;\n"
    "  selected: DiscordContextTraceItem[];\n"
    "}\n\n"
    "export interface DiscordExpressionResolveRequest {",
)
replace_once(
    "connectors/discord/src/types.ts",
    "  smart_output?: DiscordSmartOutput | null;\n}",
    "  smart_output?: DiscordSmartOutput | null;\n"
    "  context_trace?: DiscordContextTrace | null;\n"
    "}",
)

# Privacy-safe Context/RAG events in the normal Discord path.
replace_once(
    "connectors/discord/src/index.ts",
    "  DiscordContextMessage,\n  DiscordDeployment,",
    "  DiscordContextMessage,\n  DiscordContextTrace,\n  DiscordDeployment,",
)
helper_marker = "}\n\nasync function syncServerCatalog(): Promise<void> {"
helper = '''}\n\nfunction reportCharacterContext(input: {\n  trace: DiscordContextTrace | null | undefined;\n  source: Message<true>;\n  deployment: DiscordDeployment;\n}): void {\n  const trace = input.trace;\n  if (!trace) return;\n  const common = {\n    guildId: input.source.guildId,\n    guildName: input.source.guild.name,\n    channelId: input.deployment.channel_id,\n    channelName: input.deployment.channel_name,\n    threadId: input.deployment.thread_id,\n    threadName: input.deployment.thread_name,\n    sourceMessageId: input.source.id,\n    deploymentId: input.deployment.deployment_id,\n    characterName: input.deployment.identity_display_name || input.deployment.character_display_name\n  };\n  const details = {\n    rag_status: trace.rag_status,\n    rag_reason: trace.rag_reason,\n    query_chars: trace.query_chars,\n    eligible_base_count: trace.eligible_base_count,\n    candidate_chunk_count: trace.candidate_chunk_count,\n    selected_chunk_count: trace.selected_chunk_count,\n    selected_knowledge_tokens: trace.selected_knowledge_tokens,\n    knowledge_token_budget: trace.knowledge_token_budget,\n    selected: trace.selected\n  };\n  reportDiscordEvent({\n    level: trace.rag_status === "failed" ? "warning" : "info",\n    eventType: "context_built",\n    message: "Character Turn Context was assembled before Smart Output.",\n    ...common,\n    details\n  });\n  reportDiscordEvent({\n    level: trace.rag_status === "failed" ? "warning" : "info",\n    eventType: `rag_retrieval_${trace.rag_status}`,\n    message:\n      trace.rag_status === "completed"\n        ? "RAG retrieval completed for this character turn."\n        : trace.rag_status === "failed"\n          ? "RAG retrieval failed; Character Runtime continued without knowledge context."\n          : "RAG retrieval was skipped for this character turn.",\n    ...common,\n    details\n  });\n}\n\nasync function syncServerCatalog(): Promise<void> {'''
replace_once("connectors/discord/src/index.ts", helper_marker, helper)
normal_marker = "      });\n      if (preparedExpression.retrieval) {"
normal_insert = "      });\n      reportCharacterContext({\n        trace: reply.context_trace,\n        source: guildMessage,\n        deployment\n      });\n      if (preparedExpression.retrieval) {"
replace_last("connectors/discord/src/index.ts", normal_marker, normal_insert)

# Portal log filters/labels.
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '  "runtime_silent",\n  "expression_candidates",',
    '  "runtime_silent",\n  "context_built",\n  "rag_retrieval_completed",\n'
    '  "rag_retrieval_skipped",\n  "rag_retrieval_failed",\n  "expression_candidates",',
)
replace_once(
    "web/src/DiscordEventLogPanel.tsx",
    '  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },\n'
    '  expression_candidates:',
    '  runtime_silent: { en: "Runtime stayed silent", zh: "Runtime 决定不回复" },\n'
    '  context_built: { en: "Context built", zh: "角色 Context 已构建" },\n'
    '  rag_retrieval_completed: { en: "RAG retrieval completed", zh: "RAG 检索完成" },\n'
    '  rag_retrieval_skipped: { en: "RAG retrieval skipped", zh: "RAG 检索跳过" },\n'
    '  rag_retrieval_failed: { en: "RAG retrieval failed", zh: "RAG 检索失败" },\n'
    '  expression_candidates:',
)

print("Context Layer + RAG V1 runtime integration applied.")
