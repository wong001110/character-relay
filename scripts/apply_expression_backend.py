from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    file = Path(path)
    text = file.read_text(encoding="utf-8")
    if old not in text:
        raise SystemExit(f"Patch anchor not found in {path}: {old[:180]!r}")
    file.write_text(text.replace(old, new, 1), encoding="utf-8")


# Persistence exports.
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '''from echo_masque.persistence.evaluation_repository import EvaluationRepository
from echo_masque.persistence.interaction_models import (''',
    '''from echo_masque.persistence.evaluation_repository import EvaluationRepository
from echo_masque.persistence.expression_models import (
    DiscordExpressionNodeRecord,
    DiscordExpressionRunRecord,
    DiscordExpressionSemanticRecord,
)
from echo_masque.persistence.expression_repository import ExpressionRepository
from echo_masque.persistence.interaction_models import (''',
)
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '''    "DiscordDeploymentScopeRecord",
    "DiscordIdentityRepository",''',
    '''    "DiscordDeploymentScopeRecord",
    "DiscordExpressionNodeRecord",
    "DiscordExpressionRunRecord",
    "DiscordExpressionSemanticRecord",
    "DiscordIdentityRepository",''',
)
replace_once(
    "src/echo_masque/persistence/__init__.py",
    '''    "EvaluationRepository",
    "InteractionConflict",''',
    '''    "EvaluationRepository",
    "ExpressionRepository",
    "InteractionConflict",''',
)

# Application wiring.
replace_once(
    "src/echo_masque/api/__init__.py",
    '''    EvaluationRepository,
    InteractionRepository,''',
    '''    EvaluationRepository,
    ExpressionRepository,
    InteractionRepository,''',
)
replace_once(
    "src/echo_masque/api/__init__.py",
    '''    interaction_repository = InteractionRepository(database)
    provider_trace_repository = ProviderTraceRepository(''',
    '''    interaction_repository = InteractionRepository(database)
    expression_repository = ExpressionRepository(database)
    provider_trace_repository = ProviderTraceRepository(''',
)
replace_once(
    "src/echo_masque/api/__init__.py",
    '''        discord_identity_repository,
        interaction_repository,
    )''',
    '''        discord_identity_repository,
        interaction_repository,
        expression_repository,
    )''',
)
replace_once(
    "src/echo_masque/api/__init__.py",
    '''    app.state.interaction_repository = interaction_repository
    app.state.provider_trace_repository = provider_trace_repository''',
    '''    app.state.interaction_repository = interaction_repository
    app.state.expression_repository = expression_repository
    app.state.provider_trace_repository = provider_trace_repository''',
)

# Account lifecycle cleanup and ownership transfer.
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''    EvaluationRepository,
    InteractionRepository,''',
    '''    EvaluationRepository,
    ExpressionRepository,
    InteractionRepository,''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''        interaction_repository: InteractionRepository | None = None,
    ) -> None:''',
    '''        interaction_repository: InteractionRepository | None = None,
        expression_repository: ExpressionRepository | None = None,
    ) -> None:''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''        self.interaction_repository = interaction_repository or InteractionRepository(database)
''',
    '''        self.interaction_repository = interaction_repository or InteractionRepository(database)
        self.expression_repository = expression_repository or ExpressionRepository(database)
''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''        interaction_counts = self.interaction_repository.delete_owner(user_id)
        identity_counts = self.discord_identity_repository.delete_owner(user_id)''',
    '''        interaction_counts = self.interaction_repository.delete_owner(user_id)
        expression_counts = self.expression_repository.delete_owner(user_id)
        identity_counts = self.discord_identity_repository.delete_owner(user_id)''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''            **interaction_counts,
            **identity_counts,''',
    '''            **interaction_counts,
            **expression_counts,
            **identity_counts,''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''        interaction_counts = self.interaction_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        combined = {''',
    '''        interaction_counts = self.interaction_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        expression_counts = self.expression_repository.claim_owner(
            "local-user",
            actor_user_id,
        )
        combined = {''',
)
replace_once(
    "src/echo_masque/evaluation_lifecycle.py",
    '''            **identity_counts,
            **interaction_counts,
        }''',
    '''            **identity_counts,
            **interaction_counts,
            **expression_counts,
        }''',
)

# Connector schemas.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''from pydantic import BaseModel, ConfigDict, Field
''',
    '''from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.expression_schemas import (
    DiscordCatalogEmoji,
    ExpressionCandidate,
    ExpressionContent,
    ExpressionDecision,
)
''',
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)
    stickers: list[DiscordCatalogSticker] = Field(default_factory=list, max_length=1000)''',
    '''    channels: list[DiscordCatalogChannel] = Field(default_factory=list, max_length=1000)
    emojis: list[DiscordCatalogEmoji] = Field(default_factory=list, max_length=1000)
    stickers: list[DiscordCatalogSticker] = Field(default_factory=list, max_length=1000)''',
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    text: str = Field(default="", max_length=10000)
    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)''',
    '''    text: str = Field(default="", max_length=10000)
    emojis: list[ExpressionContent] = Field(default_factory=list, max_length=20)
    stickers: list[DiscordStickerContent] = Field(default_factory=list, max_length=3)''',
)
# The same text/stickers anchor appears in DiscordInboundMessage after ContextMessage.
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    text: str = Field(default="", max_length=10000)
    mentioned_bot: bool = False''',
    '''    text: str = Field(default="", max_length=10000)
    emojis: list[ExpressionContent] = Field(default_factory=list, max_length=20)
    mentioned_bot: bool = False''',
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    interaction_target_display_name: str = Field(default="", max_length=160)


class DiscordConnectorReplyView(BaseModel):
    action: Literal["silent", "reply"]''',
    '''    interaction_target_display_name: str = Field(default="", max_length=160)
    expression_run_id: str = Field(default="", max_length=64)
    expression_candidates: list[ExpressionCandidate] = Field(default_factory=list, max_length=10)


class DiscordConnectorReplyView(BaseModel):
    action: Literal["silent", "reply", "expression"]''',
)
replace_once(
    "src/echo_masque/api/connector_schemas.py",
    '''    output_tokens: int | None = None''',
    '''    output_tokens: int | None = None
    expression: ExpressionDecision = Field(default_factory=ExpressionDecision)''',
)

# Runtime parser, prompt augmentation, and structured output.
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''import os
from collections.abc import Callable''',
    '''import json
import os
import re
from collections.abc import Callable''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordContextMessage,
    DiscordInboundMessage,
)''',
    '''from echo_masque.api.connector_schemas import (
    DiscordConnectorReplyView,
    DiscordContextMessage,
    DiscordInboundMessage,
)
from echo_masque.api.expression_schemas import ExpressionCandidate, ExpressionDecision''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        text = response.text.strip()
        if not text:
            return DiscordConnectorReplyView(
                action="silent",
                reason="empty_model_response",
                deployment_id=deployment.id,
                character_display_name=card.display_name,
            )

        self.deployment_repository.record_deployment_activity(deployment.id)
        return DiscordConnectorReplyView(
            action="reply",''',
    '''        text, expression = self._parse_expression_decision(
            response.text.strip(),
            payload.expression_candidates,
        )
        if not text and expression.action == "none":
            return DiscordConnectorReplyView(
                action="silent",
                reason="empty_model_response",
                deployment_id=deployment.id,
                character_display_name=card.display_name,
                expression=expression,
            )

        self.deployment_repository.record_deployment_activity(deployment.id)
        return DiscordConnectorReplyView(
            action="reply" if text else "expression",''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''            output_tokens=response.output_tokens,
        )

    @staticmethod
    def _should_reply''',
    '''            output_tokens=response.output_tokens,
            expression=expression,
        )

    @staticmethod
    def _parse_expression_decision(
        text: str,
        candidates: list[ExpressionCandidate],
    ) -> tuple[str, ExpressionDecision]:
        marker = re.search(r"\\[\\[CR_EXPRESSION\\s+(\\{.*?\\})\\s*\\]\\]\\s*$", text, re.DOTALL)
        if marker is None:
            return text.strip(), ExpressionDecision(reason="model_omitted_expression_control")
        clean_text = text[: marker.start()].rstrip()
        try:
            value = json.loads(marker.group(1))
            decision = ExpressionDecision.model_validate(value)
        except (json.JSONDecodeError, ValueError):
            return clean_text, ExpressionDecision(reason="invalid_expression_control")
        if decision.action == "none":
            return clean_text, decision
        candidate = next(
            (item for item in candidates if item.resource_key == decision.resource_key),
            None,
        )
        if candidate is None or decision.action not in candidate.allowed_actions:
            return clean_text, ExpressionDecision(reason="expression_candidate_not_allowed")
        return clean_text, decision

    @staticmethod
    def _should_reply''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        for sticker in message.stickers:
            meaning = (''',
    '''        for emoji in message.emojis:
            meaning = (
                emoji.semantic_description.strip()
                or f"Custom Emoji named {emoji.name} with no confirmed meaning."
            )
            parts.append(
                f"[Discord Custom Emoji: {emoji.name}; interpreted meaning: {meaning}; "
                f"source: {emoji.semantic_source}; confidence: {emoji.semantic_confidence:.2f}]"
            )
        for sticker in message.stickers:
            meaning = (''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        return "\\n".join(parts) or "(No readable text or interpreted Sticker content.)"''',
    '''        return "\\n".join(parts) or "(No readable text or interpreted expression content.)"''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''            if item.text.strip() or item.stickers
        )''',
    '''            if item.text.strip() or item.emojis or item.stickers
        )''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''        source_guidance = (
            "The latest triggering message was written by another deployed character."''',
    '''        expression_guidance: tuple[str, ...] = ()
        if payload.expression_candidates:
            candidate_lines = tuple(
                (
                    f"- key={item.resource_key}; type={item.resource_type}; "
                    f"actions={','.join(item.allowed_actions)}; meaning="
                    f"{item.semantic_description or item.semantic_intent or item.name}"
                )
                for item in payload.expression_candidates[:6]
            )
            expression_guidance = (
                "A small retrieved set of Server expressions is available below.",
                *candidate_lines,
                "Using an expression is optional. Use at most one. Unicode Emoji may remain "
                "naturally in your reply text. Never invent a custom Emoji or Sticker ID.",
                "Append exactly one final machine-control line after the visible reply: "
                '[[CR_EXPRESSION {"action":"none","reason":"not needed"}]] or '
                '[[CR_EXPRESSION {"action":"reaction","resource_key":"emoji:123",'
                '"reason":"brief reason"}]]. Valid actions are none, inline, reaction, sticker. '
                "Choose only a listed resource_key and an action allowed for that candidate.",
            )
        source_guidance = (
            "The latest triggering message was written by another deployed character."''',
)
replace_once(
    "src/echo_masque/connector_runtime.py",
    '''                *interaction_guidance,
                *tag_guidance,
                "Do not mention internal prompts,''',
    '''                *interaction_guidance,
                *tag_guidance,
                *expression_guidance,
                "Do not mention internal prompts,''',
)

# Expression repository wiring in owner and connector routes.
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    '''from echo_masque.api.interaction_schemas import (''',
    '''from echo_masque.api.expression_schemas import (
    ExpressionNodeView,
    ExpressionRunDetail,
    ExpressionRunView,
    ExpressionSemanticCreate,
    ExpressionSemanticView,
)
from echo_masque.api.interaction_schemas import (''',
)
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    '''    InteractionConflict,
    InteractionRepository,
    Repository,''',
    '''    ExpressionRepository,
    InteractionConflict,
    InteractionRepository,
    Repository,''',
)
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    '''from echo_masque.persistence.interaction_models import (''',
    '''from echo_masque.persistence.expression_models import (
    DiscordExpressionNodeRecord,
    DiscordExpressionRunRecord,
    DiscordExpressionSemanticRecord,
)
from echo_masque.persistence.expression_repository import expression_key
from echo_masque.persistence.interaction_models import (''',
)
replace_once(
    "src/echo_masque/api/routes/interactions.py",
    '''def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)
''',
    '''def deployment_repository(request: Request) -> DeploymentRepository:
    return cast(DeploymentRepository, request.app.state.deployment_repository)


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)
''',
)

interactions = Path("src/echo_masque/api/routes/interactions.py")
text = interactions.read_text(encoding="utf-8")
append = r'''


def expression_view(
    request: Request,
    record: DiscordExpressionSemanticRecord,
) -> ExpressionSemanticView:
    expressions = expression_repository(request)
    return ExpressionSemanticView(
        id=record.id,
        resource_key=expression_key(record.resource_type, record.resource_id),
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        resource_type=record.resource_type,  # type: ignore[arg-type]
        resource_id=record.resource_id,
        name=record.name,
        description=record.description,
        tags=expressions.tags(record),
        format_type=record.format_type,
        asset_url=record.asset_url,
        animated=record.animated,
        available=record.available,
        enabled=record.enabled,
        semantic_intent=record.semantic_intent,
        semantic_emotion=record.semantic_emotion,
        semantic_description=record.semantic_description,
        aliases=expressions.aliases(record),
        situations=expressions.situations(record),
        avoid_when=expressions.avoid_when(record),
        allowed_actions=expressions.allowed_actions(record),  # type: ignore[arg-type]
        semantic_source=record.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=record.semantic_confidence,
        last_seen_at=record.last_seen_at,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def expression_node_view(
    request: Request,
    record: DiscordExpressionNodeRecord,
) -> ExpressionNodeView:
    expressions = expression_repository(request)
    return ExpressionNodeView(
        id=record.id,
        node_name=record.node_name,
        node_index=record.node_index,
        attempt=record.attempt,
        status=record.status,  # type: ignore[arg-type]
        input_summary=expressions.node_input(record),
        output_summary=expressions.node_output(record),
        error=record.error,
        started_at=record.started_at,
        completed_at=record.completed_at,
    )


def expression_run_view(
    request: Request,
    record: DiscordExpressionRunRecord,
) -> ExpressionRunView:
    return ExpressionRunView(
        id=record.id,
        connection_id=record.connection_id,
        guild_id=record.guild_id,
        channel_id=record.channel_id,
        source_message_id=record.source_message_id,
        deployment_id=record.deployment_id,
        character_card_id=record.character_card_id,
        status=record.status,  # type: ignore[arg-type]
        current_node=record.current_node,
        attempt_count=record.attempt_count,
        selected_action=record.selected_action,  # type: ignore[arg-type]
        selected_resource_key=record.selected_resource_key,
        state=expression_repository(request).run_state(record),
        last_error=record.last_error,
        created_at=record.created_at,
        updated_at=record.updated_at,
        completed_at=record.completed_at,
    )


@router.get(
    "/discord/expression-dictionary",
    response_model=list[ExpressionSemanticView],
)
def list_expression_dictionary(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
    resource_type: str | None = Query(default=None, pattern="^(emoji|sticker)$"),
) -> list[ExpressionSemanticView]:
    return [
        expression_view(request, item)
        for item in expression_repository(request).list_resources(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
            resource_type=resource_type,
        )
    ]


@router.put(
    "/discord/expression-dictionary",
    response_model=ExpressionSemanticView,
)
def save_expression_dictionary_entry(
    payload: ExpressionSemanticCreate,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionSemanticView:
    try:
        record = expression_repository(request).upsert_manual_resource(
            owner_id=user.id,
            **payload.model_dump(),
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return expression_view(request, record)


@router.get(
    "/discord/expression-runs",
    response_model=list[ExpressionRunView],
)
def list_expression_runs(
    request: Request,
    user: CurrentUserDependency,
    connection_id: str | None = Query(default=None, max_length=64),
    guild_id: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[ExpressionRunView]:
    return [
        expression_run_view(request, item)
        for item in expression_repository(request).list_runs(
            user.id,
            connection_id=connection_id,
            guild_id=guild_id,
            limit=limit,
        )
    ]


@router.get(
    "/discord/expression-runs/{run_id}",
    response_model=ExpressionRunDetail,
)
def get_expression_run(
    run_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> ExpressionRunDetail:
    record = expression_repository(request).get_run(run_id, user.id)
    if record is None:
        raise HTTPException(status_code=404, detail="Expression run not found.")
    base = expression_run_view(request, record)
    return ExpressionRunDetail(
        **base.model_dump(),
        nodes=[
            expression_node_view(request, item)
            for item in expression_repository(request).list_nodes(run_id, user.id)
        ],
    )
'''
if "/discord/expression-dictionary" not in text:
    interactions.write_text(text + append, encoding="utf-8")

# Connector route imports and endpoints.
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''from echo_masque.api.connector_schemas import (''',
    '''from echo_masque.api.connector_schemas import (''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''from echo_masque.config import Settings''',
    '''from echo_masque.api.expression_schemas import (
    ExpressionCandidate,
    ExpressionContent,
    ExpressionNodeReport,
    ExpressionResolveRequest,
    ExpressionRetrievalView,
    ExpressionRetrieveRequest,
)
from echo_masque.config import Settings''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''    DeploymentRepository,
    DiscordIdentityRepository,
    InteractionRepository,''',
    '''    DeploymentRepository,
    DiscordIdentityRepository,
    ExpressionRepository,
    InteractionRepository,''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''from echo_masque.persistence.deployment_repository import decode_ids''',
    '''from echo_masque.persistence.deployment_repository import decode_ids
from echo_masque.persistence.expression_repository import expression_key''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)
''',
    '''def interaction_repository(request: Request) -> InteractionRepository:
    return cast(InteractionRepository, request.app.state.interaction_repository)


def expression_repository(request: Request) -> ExpressionRepository:
    return cast(ExpressionRepository, request.app.state.expression_repository)
''',
)
replace_once(
    "src/echo_masque/api/routes/connectors.py",
    '''        for server in payload.servers:
            interaction_repository(request).sync_sticker_catalog(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                stickers=[item.model_dump() for item in server.stickers],
            )''',
    '''        for server in payload.servers:
            interaction_repository(request).sync_sticker_catalog(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                stickers=[item.model_dump() for item in server.stickers],
            )
            expression_repository(request).sync_server_resources(
                connection_id=payload.connection_id,
                guild_id=server.guild_id,
                emojis=[item.model_dump() for item in server.emojis],
                stickers=[item.model_dump() for item in server.stickers],
            )''',
)

connectors = Path("src/echo_masque/api/routes/connectors.py")
text = connectors.read_text(encoding="utf-8")
marker = '''@router.post("/interaction-sessions/claim", response_model=DiscordInteractionClaimView)'''
endpoints = r'''


def expression_content(request: Request, record: object) -> ExpressionContent:
    item = cast("DiscordExpressionSemanticRecord", record)
    expressions = expression_repository(request)
    return ExpressionContent(
        resource_key=expression_key(item.resource_type, item.resource_id),
        resource_type=item.resource_type,  # type: ignore[arg-type]
        resource_id=item.resource_id,
        name=item.name,
        animated=item.animated,
        available=item.available,
        enabled=item.enabled,
        allowed_actions=expressions.allowed_actions(item),  # type: ignore[arg-type]
        semantic_intent=item.semantic_intent,
        semantic_emotion=item.semantic_emotion,
        semantic_description=item.semantic_description,
        semantic_source=item.semantic_source,  # type: ignore[arg-type]
        semantic_confidence=item.semantic_confidence,
        asset_url=item.asset_url,
        format_type=item.format_type,
    )


@router.post("/expressions/resolve", response_model=ExpressionContent)
def resolve_discord_expression(
    payload: ExpressionResolveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ExpressionContent:
    _authorize_connector(request, authorization)
    try:
        record = expression_repository(request).resolve_resource(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Discord connection not found.") from exc
    return expression_content(request, record)


@router.post("/expressions/retrieve", response_model=ExpressionRetrievalView)
def retrieve_discord_expressions(
    payload: ExpressionRetrieveRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> ExpressionRetrievalView:
    _authorize_connector(request, authorization)
    try:
        run, candidates = expression_repository(request).retrieve(**payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Expression workflow scope not found.") from exc
    return ExpressionRetrievalView(
        run_id=run.id,
        attempt=run.attempt_count,
        candidates=[ExpressionCandidate.model_validate(item) for item in candidates],
    )


@router.post(
    "/expressions/runs/{run_id}/nodes",
    status_code=status.HTTP_204_NO_CONTENT,
)
def record_expression_node(
    run_id: str,
    payload: ExpressionNodeReport,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> None:
    _authorize_connector(request, authorization)
    try:
        expression_repository(request).record_node(run_id=run_id, **payload.model_dump())
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Expression run not found.") from exc


'''
if "/expressions/retrieve" not in text:
    text = text.replace(marker, endpoints + marker, 1)
    # Runtime-only type import kept out of the main import block to avoid route cycles.
    text = text.replace(
        "from echo_masque.persistence.expression_repository import expression_key",
        "from echo_masque.persistence.expression_models import DiscordExpressionSemanticRecord\n"
        "from echo_masque.persistence.expression_repository import expression_key",
    )
    connectors.write_text(text, encoding="utf-8")

# Fix the conditional resource ID expression in the new repository.
replace_once(
    "src/echo_masque/persistence/expression_repository.py",
    '''                    resource_id = str(
                        item.get("emoji_id") if resource_type == "emoji" else item.get("sticker_id")
                        or ""
                    ).strip()''',
    '''                    raw_resource_id = (
                        item.get("emoji_id")
                        if resource_type == "emoji"
                        else item.get("sticker_id")
                    )
                    resource_id = str(raw_resource_id or "").strip()''',
)
