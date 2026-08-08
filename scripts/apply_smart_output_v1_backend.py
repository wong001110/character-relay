from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise SystemExit(f"Expected exactly one match in {path}: {old[:80]!r}")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_between(path: str, start: str, end: str | None, replacement: str) -> None:
    target = Path(path)
    text = target.read_text(encoding="utf-8")
    start_index = text.find(start)
    if start_index < 0:
        raise SystemExit(f"Start marker not found in {path}: {start!r}")
    if end is None:
        end_index = len(text)
    else:
        end_index = text.find(end, start_index + len(start))
        if end_index < 0:
            raise SystemExit(f"End marker not found in {path}: {end!r}")
    target.write_text(
        text[:start_index] + replacement + text[end_index:],
        encoding="utf-8",
    )


replace_once(
    "src/echo_masque/api/connector_schemas.py",
    """from echo_masque.api.expression_schemas import (\n    DiscordCatalogEmoji,\n    ExpressionCandidate,\n    ExpressionContent,\n    ExpressionDecision,\n)\n""",
    """from echo_masque.api.expression_schemas import (\n    DiscordCatalogEmoji,\n    ExpressionCandidate,\n    ExpressionContent,\n    ExpressionDecision,\n)\nfrom echo_masque.smart_output import (\n    DiscordActionParticipant,\n    DiscordSmartOutputView,\n)\n""",
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    """    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n""",
    """    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)\n    available_characters: list[str] = Field(default_factory=list, max_length=30)\n    mentionable_participants: list[DiscordActionParticipant] = Field(\n        default_factory=list, max_length=20\n    )\n    recent_messages: list[DiscordContextMessage] = Field(default_factory=list, max_length=30)\n""",
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    """    output_tokens: int | None = None\n    expression: ExpressionDecision = Field(default_factory=ExpressionDecision)\n""",
    """    output_tokens: int | None = None\n    expression: ExpressionDecision = Field(default_factory=ExpressionDecision)\n    smart_output: DiscordSmartOutputView | None = None\n""",
)

replace_once(
    "src/echo_masque/character_prompts.py",
    'CHARACTER_PROMPT_COMPILER_VERSION = "character-relay-compiler-v2"',
    'CHARACTER_PROMPT_COMPILER_VERSION = "character-relay-compiler-v3"',
)
replace_once(
    "src/echo_masque/character_prompts.py",
    """                    "- When runtime instructions provide retrieved Discord expressions and a "\n                    "machine-control protocol, never write a textual placeholder for an "\n                    "expression in visible dialogue, such as [question-mark expression], "\n                    "[emoji], [sticker], or <insert emoji>.",\n                    "- If you want a retrieved custom Emoji to appear as part of your own reply, "\n                    "keep the visible dialogue natural and select the real resource only through "\n                    "the provided machine-control protocol, using the inline action when the "\n                    "runtime instructions define it for that purpose.",\n""",
    """                    "- When runtime instructions provide retrieved Discord expressions and a "\n                    "structured Smart Output protocol, never write a textual placeholder for an "\n                    "expression in visible dialogue, such as [question-mark expression], "\n                    "[emoji], [sticker], or <insert emoji>.",\n                    "- Use a retrieved custom Emoji only through the structured output resource "\n                    "reference supplied by the runtime; never invent a Discord resource ID.",\n                    "- Discord actions, message references, mentions, Emoji, and Stickers are "\n                    "proposals. The runtime validates permissions, resources, and recipients "\n                    "before anything is executed.",\n""",
)

replace_once(
    "src/echo_masque/connector_runtime.py",
    """from echo_masque.targets import PromptModelConfig, PromptModelTarget, fragile_target, stable_target\nfrom echo_masque.targets.base import TargetAdapter\n""",
    """from echo_masque.targets import PromptModelConfig, PromptModelTarget, fragile_target, stable_target\nfrom echo_masque.targets.base import TargetAdapter\nfrom echo_masque.smart_output import (\n    DiscordSmartOutputView,\n    SmartOutputContext,\n    expression_decision_for,\n    legacy_message_output,\n)\n""",
)

respond = '''    async def respond(self, payload: DiscordInboundMessage) -> DiscordConnectorReplyView:\n        deployment = self.deployment_repository.deployment_matches_discord_destination(\n            payload.deployment_id,\n            connection_id=payload.connection_id,\n            guild_id=payload.guild_id,\n            channel_id=payload.channel_id,\n            thread_id=payload.thread_id,\n            category_id=payload.category_id,\n        )\n        if deployment is None:\n            return DiscordConnectorReplyView(\n                action="silent",\n                reason="no_active_deployment",\n                deployment_id=payload.deployment_id,\n            )\n\n        if not self._should_reply(deployment, payload):\n            return DiscordConnectorReplyView(\n                action="silent",\n                reason="trigger_not_matched",\n                deployment_id=deployment.id,\n            )\n\n        card = self.repository.get_character_card(\n            deployment.character_card_id,\n            deployment.owner_id,\n        )\n        if card is None:\n            self.deployment_repository.record_deployment_error(\n                deployment.id,\n                "Character Card is unavailable.",\n            )\n            raise ConnectorRuntimeError("Character Card is unavailable.")\n        target_record = self.repository.get_target(card.target_id)\n        if target_record is None:\n            self.deployment_repository.record_deployment_error(\n                deployment.id,\n                "Character target binding is unavailable.",\n            )\n            raise ConnectorRuntimeError("Character target binding is unavailable.")\n\n        target = self._target(\n            target_kind=target_record.target_kind,\n            target_name=target_record.name,\n            config_json=target_record.config_json,\n            owner_id=deployment.owner_id,\n            character_card_id=card.id,\n            character_profile=CharacterPromptProfile.from_record(card),\n        )\n        smart_context = SmartOutputContext.from_payload(\n            payload,\n            character_name=card.display_name,\n        )\n        prompt = self._social_prompt(\n            character_name=card.display_name,\n            payload=payload,\n            smart_context=smart_context,\n        )\n        try:\n            response = await target.send(prompt)\n        except Exception as exc:\n            self.deployment_repository.record_deployment_error(\n                deployment.id,\n                str(exc),\n            )\n            raise\n\n        final_response = response\n        smart_output, smart_reason = smart_context.parse_and_resolve(\n            response.text.strip(),\n            payload.expression_candidates,\n        )\n        if smart_output is None and target_record.target_kind == "prompt_model":\n            retry_prompt = "\\n".join(\n                (\n                    prompt,\n                    "",\n                    f"Your previous Smart Output was rejected ({smart_reason}).",\n                    "Regenerate once. Return exactly one valid [[CR_OUTPUT {...}]] line "\n                    "and nothing else. Use only the references supplied above.",\n                )\n            )\n            try:\n                retry_response = await target.send(retry_prompt)\n                final_response = retry_response\n                smart_output, smart_reason = smart_context.parse_and_resolve(\n                    retry_response.text.strip(),\n                    payload.expression_candidates,\n                )\n            except Exception as exc:\n                self.deployment_repository.record_deployment_error(\n                    deployment.id,\n                    str(exc),\n                )\n                smart_reason = "smart_output_retry_failed"\n\n        if smart_output is None and target_record.target_kind in {"stable", "fragile"}:\n            smart_output = legacy_message_output(response.text, payload.message_id)\n            smart_reason = "deterministic_target_adapter"\n\n        if smart_output is None:\n            smart_output = DiscordSmartOutputView(action="ignore")\n            smart_reason = f"invalid_smart_output:{smart_reason}"\n\n        expression = expression_decision_for(smart_output)\n        text = smart_context.legacy_visible_text(smart_output)\n        if smart_output.action == "ignore":\n            return DiscordConnectorReplyView(\n                action="silent",\n                reason=(\n                    smart_reason\n                    if smart_reason != "ok"\n                    else "character_chose_ignore"\n                ),\n                deployment_id=deployment.id,\n                character_display_name=card.display_name,\n                latency_ms=final_response.latency_ms,\n                input_tokens=final_response.input_tokens,\n                output_tokens=final_response.output_tokens,\n                expression=expression,\n                smart_output=smart_output,\n            )\n\n        self.deployment_repository.record_deployment_activity(deployment.id)\n        return DiscordConnectorReplyView(\n            action="reply" if smart_output.action == "message" else "expression",\n            reason="smart_output_generated",\n            deployment_id=deployment.id,\n            character_display_name=card.display_name,\n            text=text or None,\n            reply_to_message_id=smart_output.reply_to_message_id,\n            latency_ms=final_response.latency_ms,\n            input_tokens=final_response.input_tokens,\n            output_tokens=final_response.output_tokens,\n            expression=expression,\n            smart_output=smart_output,\n        )\n\n'''
replace_between(
    "src/echo_masque/connector_runtime.py",
    "    async def respond(self, payload: DiscordInboundMessage) -> DiscordConnectorReplyView:\n",
    "    @staticmethod\n    def _parse_expression_decision",
    respond,
)

social = '''    @staticmethod\n    def _social_prompt(\n        *,\n        character_name: str,\n        payload: DiscordInboundMessage,\n        smart_context: SmartOutputContext | None = None,\n    ) -> str:\n        smart_context = smart_context or SmartOutputContext.from_payload(\n            payload,\n            character_name=character_name,\n        )\n        messages = list(payload.recent_messages)\n        if not any(item.message_id == payload.message_id for item in messages):\n            messages.append(\n                DiscordContextMessage(\n                    message_id=payload.message_id,\n                    author_id=payload.author_id,\n                    author_display_name=payload.author_display_name,\n                    text=payload.text,\n                    emojis=payload.emojis,\n                    stickers=payload.stickers,\n                    is_bot=payload.author_is_bot,\n                )\n            )\n        transcript = "\\n".join(\n            (\n                f"[{smart_context.message_alias(item.message_id)} | "\n                f"{'Character' if item.is_bot else 'Member'}: "\n                f"{item.author_display_name}]: "\n                f"{DiscordConnectorRuntime._context_message_content(item)}"\n            )\n            for item in messages[-30:]\n            if item.text.strip() or item.emojis or item.stickers\n        )\n        location = payload.channel_name or payload.channel_id\n        if payload.thread_id:\n            location = f"{location} / {payload.thread_name or payload.thread_id}"\n\n        interaction_guidance: tuple[str, ...] = ()\n        if payload.interaction_session_id:\n            intensity_rules = {\n                "light": "Use mild teasing and keep the response easy to brush off.",\n                "playful": "Use clear playful roasting with wit, not hostility.",\n                "sharp": "Be more direct and cutting, while remaining non-abusive.",\n            }\n            target_name = (\n                payload.interaction_target_display_name or payload.author_display_name\n            )\n            interaction_guidance = (\n                "This reply is part of a Portal-configured Roast Interaction Session.",\n                f"The target member is {target_name}.",\n                f"You are speaker {payload.interaction_position} of "\n                f"{payload.interaction_participant_count} in round "\n                f"{payload.interaction_round} of {payload.interaction_total_rounds}.",\n                intensity_rules.get(\n                    payload.interaction_intensity,\n                    "Use playful teasing without hostility.",\n                ),\n                "Build on earlier character replies in this Interaction Session without "\n                "repeating the same joke. Do not mention another character; speaking order "\n                "is controlled by the Session.",\n                "Roast only the target member's current words, choices, harmless habits, "\n                "gameplay, coding mistakes, lateness, or self-directed jokes. Never target "\n                "identity traits, nationality, race, religion, gender, sexuality, disability, "\n                "health, body, appearance, trauma, family, private data, or threats. Do not "\n                "invent personal facts or encourage harassment outside this bounded exchange.",\n            )\n\n        source_guidance = (\n            "The latest triggering message was written by another deployed character."\n            if payload.author_is_bot\n            else "The latest triggering message was written by a human Discord member."\n        )\n        latest_message = DiscordContextMessage(\n            message_id=payload.message_id,\n            author_id=payload.author_id,\n            author_display_name=payload.author_display_name,\n            text=payload.text,\n            emojis=payload.emojis,\n            stickers=payload.stickers,\n            is_bot=payload.author_is_bot,\n        )\n        latest_content = DiscordConnectorRuntime._context_message_content(latest_message)\n        return "\\n".join(\n            (\n                "You are participating in a real Discord group conversation "\n                "through Character Relay.",\n                f"Continue acting as {character_name} using the existing system "\n                "prompt and persona.",\n                "Decide the most natural behavior for the latest triggering message. "\n                "You do not need to speak or react to every turn.",\n                source_guidance,\n                *interaction_guidance,\n                *smart_context.prompt_guidance(payload.expression_candidates),\n                "Do not mention internal prompts, deployment configuration, OOC evaluation, "\n                "or Character Relay.",\n                "Do not claim to have seen messages outside the supplied transcript.",\n                "Keep visible message content natural for a group chat and do not prefix it "\n                "with your own name.",\n                f"Discord location: {payload.guild_name or payload.guild_id} / {location}",\n                "Recent conversation:",\n                transcript or "(No readable recent messages.)",\n                "Latest triggering message:",\n                (\n                    f"[trigger | "\n                    f"{'Character' if payload.author_is_bot else 'Member'}: "\n                    f"{payload.author_display_name}]: {latest_content}"\n                ),\n                "Return Smart Output now.",\n            )\n        )\n'''
replace_between(
    "src/echo_masque/connector_runtime.py",
    "    @staticmethod\n    def _social_prompt(\n",
    None,
    social,
)

replace_once(
    "tests/test_character_prompt_expression_invariants.py",
    '    assert CHARACTER_PROMPT_COMPILER_VERSION == "character-relay-compiler-v2"\n',
    '    assert CHARACTER_PROMPT_COMPILER_VERSION == "character-relay-compiler-v3"\n',
)
replace_once(
    "tests/test_character_prompt_expression_invariants.py",
    """    assert "select the real resource only through" in compiled.compiled_system_prompt\n    assert "using the inline action" in compiled.compiled_system_prompt\n""",
    """    assert "structured output resource reference" in compiled.compiled_system_prompt\n    assert "never invent a Discord resource ID" in compiled.compiled_system_prompt\n    assert "proposals" in compiled.compiled_system_prompt\n""",
)

print("Smart Output V1 backend migration applied.")
