from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Expected block not found in {path}: {old[:120]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


# Preserve original Discord message IDs for visible images collected into a Conversation Burst.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    "    attachments: list[DiscordAttachmentContent] = Field(default_factory=list, max_length=10)\n    embeds: list[DiscordEmbedContent] = Field(default_factory=list, max_length=10)\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n",
    "    attachments: list[DiscordAttachmentContent] = Field(default_factory=list, max_length=10)\n    embeds: list[DiscordEmbedContent] = Field(default_factory=list, max_length=10)\n    burst_media_message_ids: list[str] = Field(default_factory=list, max_length=3)\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n",
)

# Media result cache must be keyed by the payload actually being resolved, not the outer turn.
replace_once(
    "src/echo_masque/media_connector_runtime.py",
    "        key = (deployment.id, resolved.payload.message_id, scope)\n",
    "        key = (deployment.id, payload.message_id, scope)\n",
)

# Add bounded passive perception for source image messages captured by the Turn Collector.
replace_once(
    "src/echo_masque/media_connector_runtime.py",
    "    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:\n        \"\"\"Inject memory/passive images only; active links/videos are Tool-driven.\"\"\"\n\n",
    '''    async def _burst_passive_image_contexts(\n        self,\n        prepared: PreparedCharacterTurn,\n        *,\n        payload: DiscordInboundMessage,\n        now: float,\n    ) -> tuple[tuple[LiveMediaContext, ...], int]:\n        \"\"\"Perceive visible image messages collected immediately before the current text.\n\n        Each source is resolved with its original Discord message ID so Conversation Media and\n        Graph provenance remain attached to the actual image message instead of the burst tail.\n        \"\"\"\n\n        memory_service = self.conversation_media_service\n        contexts: list[LiveMediaContext] = []\n        cache_hits = 0\n        seen: set[str] = set()\n        for raw_message_id in payload.burst_media_message_ids[:2]:\n            source_message_id = raw_message_id.strip()\n            if (\n                not source_message_id\n                or source_message_id == payload.message_id\n                or source_message_id in seen\n            ):\n                continue\n            seen.add(source_message_id)\n            source_payload = payload.model_copy(\n                update={\n                    \"message_id\": source_message_id,\n                    \"text\": \"\",\n                    \"attachments\": [],\n                    \"embeds\": [],\n                    \"burst_media_message_ids\": [],\n                }\n            )\n            result = await self._media_result_for_payload(\n                prepared,\n                payload=source_payload,\n                scope=f\"burst-passive-image:{source_message_id}\",\n                now=now,\n            )\n            source_contexts = tuple(\n                item for item in result.contexts if item.kind == \"image\"\n            )\n            if not source_contexts:\n                continue\n            cache_hits += result.cache_hits\n            if memory_service is not None:\n                memory_service.remember_perceived(\n                    owner_id=prepared.resolved.deployment.owner_id,\n                    deployment_id=prepared.resolved.deployment.id,\n                    character_card_id=prepared.resolved.card.id,\n                    payload=source_payload,\n                    contexts=source_contexts,\n                )\n            contexts.extend(source_contexts)\n            if len(contexts) >= 5:\n                break\n        return tuple(contexts[:5]), cache_hits\n\n    async def _ensure_media_context(self, prepared: PreparedCharacterTurn) -> None:\n        \"\"\"Inject memory/passive images only; active links/videos are Tool-driven.\"\"\"\n\n''',
)

replace_once(
    "src/echo_masque/media_connector_runtime.py",
    '''        if not has_shared_content(payload):\n            return\n\n        key = (deployment.id, payload.message_id)\n        now = monotonic()\n        passive_payload, active_payload = self._split_passive_images(payload)\n        passive_contexts: tuple[LiveMediaContext, ...] = ()\n        passive_cache_hits = 0\n        passive_reason = \"\"\n\n        if passive_payload is not None:\n            passive_result = await self._media_result_for_payload(\n                prepared,\n                payload=passive_payload,\n                scope=\"passive-images\",\n                now=now,\n            )\n            passive_contexts = tuple(\n                item for item in passive_result.contexts if item.kind == \"image\"\n            )\n            passive_cache_hits = passive_result.cache_hits\n            passive_reason = passive_result.reason\n            if passive_contexts:\n                if memory_service is not None:\n                    memory_service.remember_perceived(\n                        owner_id=deployment.owner_id,\n                        deployment_id=deployment.id,\n                        character_card_id=resolved.card.id,\n                        payload=passive_payload,\n                        contexts=passive_contexts,\n                    )\n                self._inject_guidance(prepared, _passive_image_guidance(passive_contexts))\n            else:\n                self._inject_guidance(\n                    prepared,\n                    _passive_image_unavailable_guidance(passive_payload),\n                )\n\n        if not has_shared_content(active_payload):\n''',
    '''        key = (deployment.id, payload.message_id)\n        now = monotonic()\n        burst_contexts, burst_cache_hits = await self._burst_passive_image_contexts(\n            prepared,\n            payload=payload,\n            now=now,\n        )\n        if not has_shared_content(payload) and not burst_contexts:\n            return\n\n        passive_payload, active_payload = self._split_passive_images(payload)\n        passive_contexts: tuple[LiveMediaContext, ...] = burst_contexts\n        passive_cache_hits = burst_cache_hits\n        passive_reason = (\n            \"conversation_burst_visible_image_attachment\" if burst_contexts else \"\"\n        )\n\n        if passive_payload is not None:\n            passive_result = await self._media_result_for_payload(\n                prepared,\n                payload=passive_payload,\n                scope=\"passive-images\",\n                now=now,\n            )\n            current_contexts = tuple(\n                item for item in passive_result.contexts if item.kind == \"image\"\n            )\n            passive_contexts = tuple((*passive_contexts, *current_contexts)[:5])\n            passive_cache_hits += passive_result.cache_hits\n            passive_reason = passive_result.reason or passive_reason\n            if current_contexts and memory_service is not None:\n                memory_service.remember_perceived(\n                    owner_id=deployment.owner_id,\n                    deployment_id=deployment.id,\n                    character_card_id=resolved.card.id,\n                    payload=passive_payload,\n                    contexts=current_contexts,\n                )\n            if not current_contexts and not burst_contexts:\n                self._inject_guidance(\n                    prepared,\n                    _passive_image_unavailable_guidance(passive_payload),\n                )\n\n        if passive_contexts:\n            self._inject_guidance(prepared, _passive_image_guidance(passive_contexts))\n\n        if not has_shared_content(active_payload):\n''',
)

# Add a focused provenance regression test using the existing fake Runtime services.
replace_once(
    "tests/test_media_connector_runtime.py",
    '''    async def contexts_for_turn(self, **_: object) -> LiveMediaResult:\n        self.calls += 1\n        return self.result\n\n\nclass FakeDeploymentRepository:\n''',
    '''    async def contexts_for_turn(self, **values: object) -> LiveMediaResult:\n        self.calls += 1\n        payload = values.get(\"payload\")\n        if isinstance(payload, DiscordInboundMessage):\n            self.payload_message_ids.append(payload.message_id)\n        return self.result\n\n\nclass FakeConversationMediaService:\n    def __init__(self) -> None:\n        self.remembered_message_ids: list[str] = []\n\n    def resolve_for_turn(self, **_: object) -> tuple[()]:\n        return ()\n\n    def guidance(self, _: object) -> tuple[str, ...]:\n        return ()\n\n    def remember_perceived(self, **values: object) -> None:\n        payload = values.get(\"payload\")\n        if isinstance(payload, DiscordInboundMessage):\n            self.remembered_message_ids.append(payload.message_id)\n\n\nclass FakeDeploymentRepository:\n''',
)
replace_once(
    "tests/test_media_connector_runtime.py",
    '''    def __init__(self, result: LiveMediaResult | None = None) -> None:\n        self.calls = 0\n        self.result = result or LiveMediaResult(\n''',
    '''    def __init__(self, result: LiveMediaResult | None = None) -> None:\n        self.calls = 0\n        self.payload_message_ids: list[str] = []\n        self.result = result or LiveMediaResult(\n''',
)
replace_once(
    "tests/test_media_connector_runtime.py",
    '''def runtime_for(\n    service: FakeLiveMediaService,\n    deployment_repository: object | None = None,\n) -> MediaAwareDiscordConnectorRuntime:\n''',
    '''def runtime_for(\n    service: FakeLiveMediaService,\n    deployment_repository: object | None = None,\n    conversation_media_service: object | None = None,\n) -> MediaAwareDiscordConnectorRuntime:\n''',
)
replace_once(
    "tests/test_media_connector_runtime.py",
    '''        tool_registry=registry,\n        live_media_service=cast(Any, service),\n    )\n''',
    '''        tool_registry=registry,\n        live_media_service=cast(Any, service),\n        conversation_media_service=cast(Any, conversation_media_service),\n    )\n''',
)

with Path("tests/test_media_connector_runtime.py").open("a", encoding="utf-8") as stream:
    stream.write(
        '''\n\ndef test_burst_visible_image_uses_original_source_message_for_perception() -> None:\n    service = FakeLiveMediaService(\n        LiveMediaResult(\n            status=\"completed\",\n            reason=\"ok\",\n            contexts=(\n                LiveMediaContext(\n                    source_key=\"sha256:image-source\",\n                    kind=\"image\",\n                    label=\"photo.png\",\n                    summary=\"A visible image from the immediately preceding Discord message.\",\n                ),\n            ),\n        )\n    )\n    memory = FakeConversationMediaService()\n    runtime = runtime_for(service, conversation_media_service=memory)\n    prepared = prepared_turn(prompt_target(SkipMediaProvider()))\n    prepared.resolved.payload = prepared.resolved.payload.model_copy(\n        update={\n            \"message_id\": \"text-message\",\n            \"text\": \"这个是不是很像 Ann\",\n            \"burst_media_message_ids\": [\"image-message\"],\n        }\n    )\n\n    asyncio.run(runtime._ensure_media_context(cast(Any, prepared)))\n\n    assert service.payload_message_ids == [\"image-message\"]\n    assert memory.remembered_message_ids == [\"image-message\"]\n    assert \"Visible images in this turn were passively perceived\" in prepared.prompt\n'''
    )
