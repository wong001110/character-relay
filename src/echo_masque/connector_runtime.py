"""Runtime bridge from normalized connector messages to deployed characters."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from pydantic import SecretStr, ValidationError

from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.character_prompts import (
    CharacterPromptProfile,
    compile_character_prompt,
)
from echo_masque.character_turn_context_types import CharacterTurnContext
from echo_masque.credentials import CredentialStore
from echo_masque.discord_event_safety import safe_runtime_error_classification
from echo_masque.domain import TargetResponse
from echo_masque.expression_intent import ExpressionIntentResolver
from echo_masque.pending_actions import PendingActionContinuation, PendingActionService
from echo_masque.persistence import (
    DeploymentRepository,
    DeploymentToolRepository,
    Repository,
)
from echo_masque.persistence.deployment_models import CharacterDeploymentRecord
from echo_masque.persistence.models import CharacterCardRecord, TargetRecord
from echo_masque.prompt_budget import unavailable_assigned_side_effect_ids_for_turn
from echo_masque.providers import (
    ChatProvider,
    OpenAICompatibleProvider,
)
from echo_masque.providers.trace import provider_trace_scope
from echo_masque.room_context import RoomContextBundle, RoomContextService, bind_requester
from echo_masque.smart_output import (
    DiscordSmartOutputView,
    SmartOutputContext,
    expression_decision_for,
    legacy_message_output,
)
from echo_masque.targets import (
    PromptModelConfig,
    PromptModelTarget,
    PromptModelToolTurn,
    fragile_target,
    stable_target,
)
from echo_masque.targets.base import TargetAdapter
from echo_masque.tool_runtime import (
    ToolExecutionContext,
    ToolExecutionTrace,
    ToolRegistry,
    default_tool_registry,
)

type ConnectorProviderFactory = Callable[[str, SecretStr], ChatProvider]


def default_connector_provider_factory(base_url: str, api_key: SecretStr) -> ChatProvider:
    return OpenAICompatibleProvider(base_url=base_url, api_key=api_key)


class ConnectorRuntimeError(RuntimeError):
    """Raised when a deployment cannot produce a connector reply."""


@dataclass(slots=True)
class ResolvedCharacterTurn:
    """Transient resolved runtime dependencies for one Character turn."""

    payload: DiscordInboundMessage
    deployment: CharacterDeploymentRecord
    card: CharacterCardRecord
    target_record: TargetRecord
    target: TargetAdapter


@dataclass(slots=True)
class PreparedCharacterTurn:
    """Transient context/model inputs. Raw content never enters LangGraph state."""

    resolved: ResolvedCharacterTurn
    turn_context: CharacterTurnContext | None
    context_bundle: RoomContextBundle | None
    context_error: str
    smart_context: SmartOutputContext
    prompt: str
    prompt_manifest: dict[str, object]
    enabled_tools: tuple[str, ...]
    tool_context: ToolExecutionContext
    pending_action: PendingActionContinuation | None = None
    suppressed_side_effect_tool_ids: tuple[str, ...] = ()


@dataclass(slots=True)
class ResolvedCharacterOutput:
    """Transient model/output result awaiting deterministic Runtime authority."""

    final_response: TargetResponse
    smart_output: DiscordSmartOutputView
    smart_reason: str
    tool_traces: list[ToolExecutionTrace]


@dataclass(frozen=True, slots=True)
class RoleplayPrompt:
    """One provider-visible Roleplay prompt and privacy-safe composition metadata."""

    text: str
    manifest: dict[str, object]


class DiscordConnectorRuntime:
    """Resolve one Discord destination and generate one character response."""

    def __init__(
        self,
        repository: Repository,
        deployment_repository: DeploymentRepository,
        credential_store: CredentialStore,
        provider_factory: ConnectorProviderFactory = default_connector_provider_factory,
        context_service: RoomContextService | None = None,
        deployment_tool_repository: DeploymentToolRepository | None = None,
        tool_registry: ToolRegistry | None = None,
        pending_action_service: PendingActionService | None = None,
    ) -> None:
        self.repository = repository
        self.deployment_repository = deployment_repository
        self.credential_store = credential_store
        self.provider_factory = provider_factory
        self.context_service = context_service
        self.deployment_tool_repository = deployment_tool_repository
        self.tool_registry = tool_registry or default_tool_registry()
        self.pending_action_service = pending_action_service
        self.expression_resolver: ExpressionIntentResolver | None = None

    def resolve_character_turn(
        self,
        payload: DiscordInboundMessage,
    ) -> tuple[ResolvedCharacterTurn | None, DiscordConnectorReplyView | None]:
        """Resolve deployment/card/target without performing a provider call."""

        deployment = self.deployment_repository.deployment_matches_discord_destination(
            payload.deployment_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            category_id=payload.category_id,
        )
        if deployment is None:
            return None, DiscordConnectorReplyView(
                action="silent",
                reason="no_active_deployment",
                deployment_id=payload.deployment_id,
            )

        if payload.source_selection_id and self.context_service is not None:
            payload = bind_requester(payload, deployment, self.context_service.repository)
        if not payload.source_selection_id and not self._should_reply(deployment, payload):
            return None, DiscordConnectorReplyView(
                action="silent",
                reason="trigger_not_matched",
                deployment_id=deployment.id,
            )

        card = self.repository.get_character_card(
            deployment.character_card_id,
            deployment.owner_id,
        )
        if card is None:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                "Character Card is unavailable.",
            )
            raise ConnectorRuntimeError("Character Card is unavailable.")
        target_record = self.repository.get_target(card.target_id)
        if target_record is None:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                "Character target binding is unavailable.",
            )
            raise ConnectorRuntimeError("Character target binding is unavailable.")

        target = self._target(
            target_kind=target_record.target_kind,
            target_name=target_record.name,
            config_json=target_record.config_json,
            owner_id=deployment.owner_id,
            character_card_id=card.id,
            character_profile=CharacterPromptProfile.from_record(card),
        )
        return (
            ResolvedCharacterTurn(
                payload=payload,
                deployment=deployment,
                card=card,
                target_record=target_record,
                target=target,
            ),
            None,
        )

    def prepare_character_turn(
        self,
        resolved: ResolvedCharacterTurn,
    ) -> PreparedCharacterTurn:
        """Build scoped context/RAG and the bounded Tool execution context."""

        payload = resolved.payload
        deployment = resolved.deployment
        card = resolved.card
        v3_context = self.context_service.build(resolved) if self.context_service else None
        if v3_context is not None:
            payload = v3_context.payload
            resolved.payload = payload
        turn_context = v3_context.turn_context if v3_context is not None else None
        context_bundle = v3_context.bundle if v3_context is not None else None
        context_error = v3_context.error_reason if v3_context is not None else ""
        smart_context = (
            turn_context.smart_output
            if turn_context is not None
            else SmartOutputContext.from_payload(
                payload,
                character_name=card.display_name,
            )
        )
        focused_message_ids = (
            context_bundle.focused_message_ids
            if context_bundle is not None and not context_error
            else ()
        )
        roleplay_prompt = self._social_prompt_with_manifest(
            character_name=card.display_name,
            role_hint=card.subtitle,
            payload=payload,
            smart_context=smart_context,
            turn_context=turn_context,
            context_sections=(
                context_bundle.prompt_sections()
                if context_bundle is not None and not context_error
                else ()
            ),
            focused_message_ids=focused_message_ids,
        )
        enabled_tools = (
            self.deployment_tool_repository.get_enabled_tools_for_runtime(deployment.id)
            if self.deployment_tool_repository is not None
            else ()
        )
        tool_context = ToolExecutionContext(
            owner_id=deployment.owner_id,
            deployment_id=deployment.id,
            character_card_id=card.id,
            platform=deployment.platform,
            connection_id=deployment.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            thread_id=payload.thread_id,
            message_id=payload.message_id,
            category_id=payload.category_id,
            trigger_text=payload.text if payload.runtime_selection_origin in {"", "direct"} else "",
            request_origin=payload.runtime_selection_origin or "direct",
            initiator_is_bot=payload.runtime_requester_is_bot
            if payload.runtime_request_id
            else payload.author_is_bot,
            initiator_user_id=payload.runtime_requester_id
            if payload.runtime_request_id
            else payload.author_id,
            operation_id=payload.runtime_operation_id,
            step_id=payload.runtime_step_id,
        )
        prepared = PreparedCharacterTurn(
            resolved=resolved,
            turn_context=turn_context,
            context_bundle=context_bundle,
            context_error=context_error,
            smart_context=smart_context,
            prompt=roleplay_prompt.text,
            prompt_manifest=roleplay_prompt.manifest,
            enabled_tools=enabled_tools,
            tool_context=tool_context,
        )
        self._prepare_pending_action(prepared)
        return prepared

    def _prepare_pending_action(self, prepared: PreparedCharacterTurn) -> None:
        """Resolve one explicit-reply or unique-thread pending action after authorization."""

        service = self.pending_action_service
        if service is None or prepared.tool_context.request_origin != "direct":
            return
        resolved = prepared.resolved
        payload = resolved.payload
        deployment = resolved.deployment
        continuation = service.resolve_continuation(
            owner_id=deployment.owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            current_message=payload.text,
            requested_by_user_id=payload.runtime_requester_id
            if payload.runtime_request_id
            else payload.author_id,
            target_character_card_id=resolved.card.id,
            deployment_id=deployment.id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            reply_to_message_id=payload.reply_to_message_id,
            assigned_tool_ids=prepared.enabled_tools,
        )
        self._suppress_pending_side_effect_tools(prepared, continuation.suppressed_tool_ids)
        if continuation.action is not None and continuation.source in {
            "explicit_reply",
            "same_native_thread",
        }:
            catalog = {item.id: item for item in self.tool_registry.catalog()}
            item = catalog.get(continuation.tool_id)
            if (
                item is not None
                and item.available
                and continuation.tool_id in set(prepared.enabled_tools)
            ):
                claimed = service.repository.claim_pending_action_for_execution(
                    owner_id=deployment.owner_id,
                    action_id=continuation.action_id,
                )
                if claimed is not None:
                    prepared.pending_action = PendingActionContinuation(
                        claimed,
                        continuation.source,
                        continuation.confidence,
                        continuation.reason,
                    )
                else:
                    self._suppress_pending_side_effect_tools(prepared, (continuation.tool_id,))
            return
        if continuation.source == "cancelled":
            prepared.pending_action = continuation
            return

        # A known pending action was not safe to resume this turn.  Do not let
        # ordinary tool selection expose that side effect as a fallback.
        if continuation.suppressed_tool_ids:
            return

        # An unavailable side effect is preserved only when the user's current message
        # directly names exactly one currently assigned capability. It remains
        # provider-invisible until a later scoped continuation rechecks availability.
        unavailable = unavailable_assigned_side_effect_ids_for_turn(
            self.tool_registry,
            prepared.enabled_tools,
            prepared.tool_context,
        )
        if len(unavailable) != 1:
            return
        service.register(
            owner_id=deployment.owner_id,
            connection_id=payload.connection_id,
            guild_id=payload.guild_id,
            channel_id=payload.channel_id,
            discord_thread_id=payload.thread_id,
            source_message_id=payload.message_id,
            requested_by_user_id=payload.runtime_requester_id
            if payload.runtime_request_id
            else payload.author_id,
            target_character_card_id=resolved.card.id,
            deployment_id=deployment.id,
            tool_id=unavailable[0],
            intent_summary=payload.text,
            state="blocked_unavailable",
        )

    def _suppress_pending_side_effect_tools(
        self,
        prepared: PreparedCharacterTurn,
        tool_ids: tuple[str, ...],
    ) -> None:
        """Keep rejected pending side effects out of this provider turn."""

        if not tool_ids:
            return
        catalog = {item.id: item for item in self.tool_registry.catalog()}
        allowed = set(prepared.enabled_tools)
        suppressed = {
            tool_id
            for tool_id in tool_ids
            if tool_id in allowed
            and (item := catalog.get(tool_id)) is not None
            and item.side_effect
        }
        if suppressed:
            prepared.suppressed_side_effect_tool_ids = tuple(
                dict.fromkeys((*prepared.suppressed_side_effect_tool_ids, *suppressed))
            )

    def _forced_tool_ids(self, prepared: PreparedCharacterTurn) -> tuple[str, ...]:
        """Expose Runtime-owned reads plus a unique, authorized continuation Tool."""

        values = list(self._runtime_internal_tool_ids())
        continuation = getattr(prepared, "pending_action", None)
        suppressed = getattr(prepared, "suppressed_side_effect_tool_ids", ())
        if (
            continuation is not None
            and continuation.source in {"explicit_reply", "same_native_thread"}
            and continuation.tool_id
            and continuation.tool_id not in suppressed
        ):
            values.append(continuation.tool_id)
        return tuple(dict.fromkeys(values))

    def _runtime_internal_tool_ids(self) -> tuple[str, ...]:
        """Return Runtime-owned read tools without making them Deployment assignments."""

        getter = getattr(self.tool_registry, "internal_tool_ids", None)
        return tuple(getter()) if callable(getter) else ()

    def _enabled_tools_for_turn(self, prepared: PreparedCharacterTurn) -> tuple[str, ...]:
        suppressed = set(getattr(prepared, "suppressed_side_effect_tool_ids", ()))
        external_tools = tuple(
            tool_id for tool_id in prepared.enabled_tools if tool_id not in suppressed
        )
        return tuple(dict.fromkeys((*external_tools, *self._runtime_internal_tool_ids())))

    async def invoke_character_model(
        self,
        prepared: PreparedCharacterTurn,
    ) -> TargetResponse:
        """Invoke the existing model adapter and bounded ToolRuntime loop unchanged."""

        target = prepared.resolved.target
        deployment = prepared.resolved.deployment
        try:
            with provider_trace_scope(prompt_manifest=prepared.prompt_manifest):
                enabled_tools = self._enabled_tools_for_turn(prepared)
                if isinstance(target, PromptModelTarget) and enabled_tools:
                    return await target.send_with_tools(
                        prepared.prompt,
                        tool_registry=self.tool_registry,
                        enabled_tool_ids=enabled_tools,
                        tool_context=prepared.tool_context,
                        max_tool_rounds=2,
                        forced_tool_ids=self._forced_tool_ids(prepared),
                    )
                return await target.send(prepared.prompt)
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                deployment.id,
                safe_runtime_error_classification(exc),
            )
            raise

    async def start_character_tool_turn(
        self,
        prepared: PreparedCharacterTurn,
    ) -> PromptModelToolTurn | None:
        """Start an explicit bounded Tool session for LangGraph orchestration."""

        target = prepared.resolved.target
        enabled_tools = self._enabled_tools_for_turn(prepared)
        if not isinstance(target, PromptModelTarget) or not enabled_tools:
            return None
        try:
            with provider_trace_scope(prompt_manifest=prepared.prompt_manifest):
                return await target.start_tool_turn(
                    prepared.prompt,
                    tool_registry=self.tool_registry,
                    enabled_tool_ids=enabled_tools,
                    tool_context=prepared.tool_context,
                    max_tool_rounds=2,
                    forced_tool_ids=self._forced_tool_ids(prepared),
                )
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                prepared.resolved.deployment.id,
                safe_runtime_error_classification(exc),
            )
            raise

    async def advance_character_tool_model(
        self,
        prepared: PreparedCharacterTurn,
        turn: PromptModelToolTurn,
    ) -> TargetResponse | None:
        """Run one provider step while keeping provider history outside graph state."""

        target = prepared.resolved.target
        if not isinstance(target, PromptModelTarget):
            raise ConnectorRuntimeError("Character Tool session requires a prompt-model target.")
        try:
            with provider_trace_scope(prompt_manifest=prepared.prompt_manifest):
                return await target.advance_tool_model(turn)
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                prepared.resolved.deployment.id,
                safe_runtime_error_classification(exc),
            )
            raise

    async def execute_character_tools(
        self,
        prepared: PreparedCharacterTurn,
        turn: PromptModelToolTurn,
    ) -> int:
        """Execute pending proposals through the existing ToolRuntime authority."""

        target = prepared.resolved.target
        if not isinstance(target, PromptModelTarget):
            raise ConnectorRuntimeError("Character Tool execution requires a prompt-model target.")
        try:
            return await target.execute_pending_tools(turn)
        except Exception as exc:
            self.deployment_repository.record_deployment_error(
                prepared.resolved.deployment.id,
                safe_runtime_error_classification(exc),
            )
            raise

    async def resolve_character_output(
        self,
        prepared: PreparedCharacterTurn,
        response: TargetResponse,
    ) -> ResolvedCharacterOutput:
        """Parse/repair Smart Output without re-running side-effect Tools."""

        resolved = prepared.resolved
        payload = resolved.payload
        deployment = resolved.deployment
        target = resolved.target
        target_record = resolved.target_record
        smart_context = prepared.smart_context
        tool_traces = self._tool_traces(response.trace)
        self._finalize_pending_action(prepared, tool_traces)
        final_response = response
        smart_output, smart_reason = smart_context.parse_and_resolve(response.text.strip())
        if smart_output is None and target_record.target_kind == "prompt_model":
            retry_prompt = PromptModelTarget._compact_format_repair(
                "\n".join(
                    (
                        prepared.prompt,
                        "",
                        f"Your previous Smart Output was rejected ({smart_reason}).",
                        "Regenerate once. Return exactly one valid [[CR_OUTPUT {...}]] line "
                        "and nothing else. Use only the references supplied above.",
                    )
                )
            )
            try:
                # Formatting repair intentionally does not re-enable Tools. Tool results
                # from the original turn remain in target history, preventing duplicated
                # reads or side effects during repair.
                with provider_trace_scope(prompt_manifest=prepared.prompt_manifest):
                    retry_response = await target.send(retry_prompt)
                final_response = retry_response
                smart_output, smart_reason = smart_context.parse_and_resolve(
                    retry_response.text.strip()
                )
            except Exception as exc:
                self.deployment_repository.record_deployment_error(
                    deployment.id,
                    safe_runtime_error_classification(exc),
                )
                smart_reason = "smart_output_retry_failed"

        if smart_output is None and target_record.target_kind in {"stable", "fragile"}:
            smart_output = legacy_message_output(
                response.text, payload.runtime_target_message_id or payload.message_id
            )
            smart_reason = "deterministic_target_adapter"

        if smart_output is None:
            smart_output = DiscordSmartOutputView(action="ignore")
            smart_reason = f"invalid_smart_output:{smart_reason}"

        return ResolvedCharacterOutput(
            final_response=final_response,
            smart_output=smart_output,
            smart_reason=smart_reason,
            tool_traces=tool_traces,
        )

    def _finalize_pending_action(
        self,
        prepared: PreparedCharacterTurn,
        traces: list[ToolExecutionTrace],
    ) -> None:
        """Close only known-safe lifecycle transitions; uncertain side effects stay blocked."""

        continuation = prepared.pending_action
        service = self.pending_action_service
        if (
            continuation is None
            or service is None
            or continuation.source not in {"explicit_reply", "same_native_thread"}
            or not continuation.action_id
        ):
            return
        matching = [item for item in traces if item.tool_id == continuation.tool_id]
        if not matching:
            return
        trace = matching[-1]
        if trace.status == "completed":
            service.repository.update_pending_action_state(
                owner_id=prepared.resolved.deployment.owner_id,
                action_id=continuation.action_id,
                state="completed",
            )
        elif trace.status == "rejected" and trace.error == "tool_provider_not_configured":
            # Rejected before Tool execution: it is safe to remain resumable after
            # configuration changes. Failed/uncertain side effects deliberately remain
            # in_progress so Runtime never repeats them automatically.
            service.repository.update_pending_action_state(
                owner_id=prepared.resolved.deployment.owner_id,
                action_id=continuation.action_id,
                state="blocked_unavailable",
            )

    def authorize_character_output(
        self,
        prepared: PreparedCharacterTurn,
        output: ResolvedCharacterOutput,
    ) -> DiscordConnectorReplyView:
        """Apply deterministic Runtime authority and produce the platform command view."""

        resolved = prepared.resolved
        deployment = resolved.deployment
        card = resolved.card
        smart_output = output.smart_output
        if smart_output.expression_intent is not None:
            if self.expression_resolver is None:
                self.expression_resolver = ExpressionIntentResolver(self.repository.database)
            smart_output = self.expression_resolver.resolve(smart_output, prepared.tool_context)
        primary = resolved.payload.runtime_target_message_id or resolved.payload.message_id
        if smart_output.action == "message":
            smart_output = smart_output.model_copy(update={"reply_to_message_id": primary})
        elif smart_output.action in {"react", "sticker"}:
            smart_output = smart_output.model_copy(update={"target_message_id": primary})
        final_response = output.final_response
        expression = expression_decision_for(smart_output)
        text = prepared.smart_context.legacy_visible_text(smart_output)
        if smart_output.action == "ignore":
            return DiscordConnectorReplyView(
                action="silent",
                reason=(
                    "expression_" + smart_output.expression_resolution
                    if smart_output.expression_resolution in {"no_match", "scope_unavailable"}
                    else output.smart_reason
                    if output.smart_reason != "ok"
                    else "character_chose_ignore"
                ),
                deployment_id=deployment.id,
                character_display_name=card.display_name,
                latency_ms=final_response.latency_ms,
                input_tokens=final_response.input_tokens,
                output_tokens=final_response.output_tokens,
                expression=expression,
                smart_output=smart_output,
                context_trace=(
                    prepared.turn_context.trace if prepared.turn_context is not None else None
                ),
                tool_calls=output.tool_traces,
            )

        self.deployment_repository.record_deployment_activity(deployment.id)
        return DiscordConnectorReplyView(
            action="reply" if smart_output.action == "message" else "expression",
            reason="smart_output_generated",
            deployment_id=deployment.id,
            character_display_name=card.display_name,
            text=text or None,
            reply_to_message_id=smart_output.reply_to_message_id,
            latency_ms=final_response.latency_ms,
            input_tokens=final_response.input_tokens,
            output_tokens=final_response.output_tokens,
            expression=expression,
            smart_output=smart_output,
            context_trace=(
                prepared.turn_context.trace if prepared.turn_context is not None else None
            ),
            tool_calls=output.tool_traces,
        )

    async def respond(self, payload: DiscordInboundMessage) -> DiscordConnectorReplyView:
        """Legacy sequential path, now composed from reusable Phase 3 stage methods."""

        resolved, early_reply = self.resolve_character_turn(payload)
        if early_reply is not None:
            return early_reply
        if resolved is None:
            raise ConnectorRuntimeError("Character turn resolution produced no result.")
        prepared = self.prepare_character_turn(resolved)
        if prepared.context_error:
            return DiscordConnectorReplyView(
                action="silent",
                reason=prepared.context_error,
                deployment_id=resolved.deployment.id,
                character_display_name=resolved.card.display_name,
                context_trace=(
                    prepared.turn_context.trace if prepared.turn_context is not None else None
                ),
            )
        response = await self.invoke_character_model(prepared)
        output = await self.resolve_character_output(prepared, response)
        return self.authorize_character_output(prepared, output)

    @staticmethod
    def _tool_traces(trace: dict[str, object]) -> list[ToolExecutionTrace]:
        raw = trace.get("tool_calls", [])
        if not isinstance(raw, list):
            return []
        results: list[ToolExecutionTrace] = []
        for item in raw[:8]:
            try:
                results.append(ToolExecutionTrace.model_validate(item))
            except ValidationError:
                continue
        return results

    @staticmethod
    def _should_reply(
        deployment: CharacterDeploymentRecord,
        payload: DiscordInboundMessage,
    ) -> bool:
        mode = deployment.participation_mode
        if mode == "mention_only":
            return payload.mentioned_bot
        if mode == "reply_only":
            return payload.replied_to_bot
        if mode == "mention_and_reply":
            return payload.mentioned_bot or payload.replied_to_bot
        if mode == "smart":
            return payload.mentioned_bot or payload.replied_to_bot or payload.smart_candidate
        return False

    def _target(
        self,
        *,
        target_kind: str,
        target_name: str,
        config_json: str,
        owner_id: str,
        character_card_id: str,
        character_profile: CharacterPromptProfile,
    ) -> TargetAdapter:
        if target_kind == "stable":
            return stable_target()
        if target_kind == "fragile":
            return fragile_target()
        if target_kind != "prompt_model":
            raise ConnectorRuntimeError(
                f"Discord deployment does not support target kind {target_kind!r}."
            )

        config = PromptModelConfig.model_validate_json(config_json)
        credential = self.credential_store.get(owner_id, character_card_id)
        if credential is None:
            raise ConnectorRuntimeError("The deployed Character Card needs a provider credential.")
        compiled = compile_character_prompt(config.system_prompt, character_profile)
        return PromptModelTarget(
            config=config,
            provider=self.provider_factory(config.base_url, credential),
            runtime_system_prompt=compiled.compiled_system_prompt,
        )

    @staticmethod
    def _context_message_content(message: DiscordContextMessage) -> str:
        parts: list[str] = []
        if message.text.strip():
            parts.append(message.text.strip())
        for emoji in message.emojis:
            meaning = (
                emoji.semantic_intent.strip()
                or emoji.semantic_emotion.strip()
                or emoji.semantic_description.strip()
                or f"Custom Emoji named {emoji.name}."
            )
            parts.append(f"[Discord Custom Emoji: {emoji.name}; intent: {meaning}]")
        for sticker in message.stickers:
            meaning = (
                sticker.semantic_intent.strip()
                or sticker.semantic_emotion.strip()
                or sticker.semantic_description.strip()
                or sticker.description.strip()
                or f"Sticker named {sticker.name}."
            )
            parts.append(f"[Discord Sticker: {sticker.name}; intent: {meaning}]")
        return "\n".join(parts) or "(No readable text or interpreted expression content.)"

    @staticmethod
    def _social_prompt(
        *,
        character_name: str,
        role_hint: str = "",
        payload: DiscordInboundMessage,
        smart_context: SmartOutputContext | None = None,
        turn_context: CharacterTurnContext | None = None,
        context_sections: tuple[str, ...] = (),
        focused_message_ids: tuple[str, ...] = (),
    ) -> str:
        return DiscordConnectorRuntime._social_prompt_with_manifest(
            character_name=character_name,
            role_hint=role_hint,
            payload=payload,
            smart_context=smart_context,
            turn_context=turn_context,
            context_sections=context_sections,
            focused_message_ids=focused_message_ids,
        ).text

    @staticmethod
    def _social_prompt_with_manifest(
        *,
        character_name: str,
        role_hint: str = "",
        payload: DiscordInboundMessage,
        smart_context: SmartOutputContext | None = None,
        turn_context: CharacterTurnContext | None = None,
        context_sections: tuple[str, ...] = (),
        focused_message_ids: tuple[str, ...] = (),
    ) -> RoleplayPrompt:
        del turn_context
        smart_context = smart_context or SmartOutputContext.from_payload(
            payload,
            character_name=character_name,
        )
        # The Character interprets tone and social meaning from the selected raw evidence.
        # There is no second heuristic/director deciding whether it was challenged or invited.
        grounding_guidance = (
            "Quoted questions are not automatically requests to you. Role expertise does not "
            "imply a personal challenge, shared preferences, or authority to act.",
        )
        knowledge_guidance = tuple(
            section for section in context_sections if not section.startswith("LIVE CONTEXT\n")
        )
        live_context_suppressed = len(knowledge_guidance) != len(context_sections)
        all_recent_messages = list(payload.recent_messages)
        focused_ids = {item for item in focused_message_ids if item}
        focused_segment_applied = bool(focused_ids)
        messages = (
            [item for item in all_recent_messages if item.message_id in focused_ids]
            if focused_segment_applied
            else all_recent_messages
        )

        def readable_messages(
            values: list[DiscordContextMessage],
        ) -> list[DiscordContextMessage]:
            return [item for item in values if item.text.strip() or item.emojis or item.stickers]

        trigger_in_selected_segment = payload.message_id in focused_ids
        trigger_already_in_recent = any(item.message_id == payload.message_id for item in messages)
        include_trigger = not focused_segment_applied or trigger_in_selected_segment
        if include_trigger and not trigger_already_in_recent:
            messages.append(
                DiscordContextMessage(
                    message_id=payload.message_id,
                    author_id=payload.author_id,
                    author_display_name=payload.author_display_name,
                    text=payload.text,
                    emojis=payload.emojis,
                    stickers=payload.stickers,
                    is_bot=payload.author_is_bot,
                )
            )
        readable_transcript_messages = readable_messages(messages[-30:])
        transcript = "\n".join(
            (
                (
                    "[PRIMARY REPLY TARGET] "
                    if item.message_id == (payload.runtime_target_message_id or payload.message_id)
                    else ""
                )
                + f"[{smart_context.message_alias(item.message_id)} | "
                f"{'Character' if item.is_bot else 'Member'}: "
                f"{item.author_display_name}]"
                + (
                    f" [reply to {smart_context.message_alias(item.reply_to_message_id)}]"
                    if item.reply_to_message_id
                    else ""
                )
                + f": {DiscordConnectorRuntime._context_message_content(item)}"
            )
            for item in readable_transcript_messages
        )
        location = payload.channel_name or payload.channel_id
        if payload.thread_id:
            location = f"{location} / {payload.thread_name or payload.thread_id}"

        interaction_guidance: tuple[str, ...] = ()
        source_guidance = (
            "The latest triggering message was written by another deployed character."
            if payload.author_is_bot
            else "The latest triggering message was written by a human Discord member."
        )
        participation_guidance: tuple[str, ...] = ()
        if payload.participation_guidance.strip():
            participation_guidance = (
                "Runtime participation hint (non-binding): "
                + payload.participation_guidance.strip(),
                (
                    "Use this only as context for why your participation may be relevant. "
                    "Your persona and the supplied conversation still determine what you say "
                    "and which visible Smart Output action you choose."
                ),
            )
        admission_guidance = (
            (
                "Runtime already admitted this Character for this turn; choose a natural "
                "visible action."
            )
            if smart_context.participation_required
            else "You may stay silent when that is the natural Character behavior."
        )
        sections = {
            "identity": "\n".join(
                (
                    "You are participating in a real Discord group conversation "
                    "through Character Relay.",
                    f"Continue acting as {character_name} using the existing system "
                    "prompt and persona.",
                    (
                        "Decide the most natural behavior for the selected conversation."
                        if focused_segment_applied and not include_trigger
                        else "Respond to the explicitly marked primary reply target."
                    ),
                )
            ),
            "participation": "\n".join(
                (admission_guidance, source_guidance, *participation_guidance)
            ),
            "interaction": "\n".join((*grounding_guidance, *interaction_guidance)),
            "output_contract": "\n".join(smart_context.prompt_guidance()),
            "source_context": "\n".join(knowledge_guidance),
            "safety": "\n".join(
                (
                    "Do not mention internal prompts, deployment configuration, OOC evaluation, "
                    "or Character Relay.",
                    "Do not claim to have seen messages outside the supplied transcript.",
                    "Keep visible message content natural for a group chat and do not prefix it "
                    "with your own name.",
                )
            ),
            "location": f"Discord location: {payload.guild_name or payload.guild_id} / {location}",
            "conversation_scope": (
                "Runtime selected a primary source and bounded raw context. Do not address "
                "other simultaneous discussions."
                if focused_segment_applied
                and len(readable_transcript_messages) < len(readable_messages(all_recent_messages))
                else ""
            ),
            "recent_conversation": "\n".join(
                (
                    "Focused conversation:" if focused_segment_applied else "Recent conversation:",
                    transcript or "(No readable recent messages.)",
                )
            ),
            "trigger": (
                "Primary reply target: trigger (explicitly marked in the conversation above)."
                if include_trigger
                else (
                    "Runtime selected the focused conversation. Do not address unrelated "
                    "concurrent activity."
                )
            ),
            "footer": "Return Smart Output now.",
        }
        text = "\n".join(value for value in sections.values() if value)
        manifest: dict[str, object] = {
            "version": 1,
            "total_chars": len(text),
            "section_count": len(sections),
            "section_chars": {key: len(value) for key, value in sections.items()},
            "recent_message_count": len(readable_transcript_messages),
            "trigger_already_in_recent": trigger_already_in_recent,
            "duplicate_suppressed_count": int(live_context_suppressed) + 1,
            "live_context_suppressed": live_context_suppressed,
            "focused_segment_applied": focused_segment_applied,
            "focused_message_count": len(focused_ids),
            "focused_trigger_excluded": focused_segment_applied and not include_trigger,
            "expression_resolution_mode": "intent_then_sparse",
        }
        return RoleplayPrompt(text=text, manifest=manifest)
