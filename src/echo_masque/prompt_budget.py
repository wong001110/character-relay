"""Prompt-budget helpers for compact Discord turns and turn-time Tool selection."""

from __future__ import annotations

import re
from threading import Lock
from typing import TYPE_CHECKING

from echo_masque.character_invite_runtime import current_character_invite_turn
from echo_masque.config import Settings, get_settings
from echo_masque.semantic_participation import (
    FastEmbedSemanticEncoder,
    SemanticEmbeddingUnavailable,
    SemanticEncoder,
    _cosine,
)
from echo_masque.semantic_turn_runtime import SemanticTurnSignalStore
from echo_masque.smart_output import SmartOutputContext, _expression_aliases

if TYPE_CHECKING:
    from echo_masque.api.expression_schemas import ExpressionCandidate
    from echo_masque.tool_runtime import ToolExecutionContext, ToolRegistry

_TOOL_DENSE_MINIMUM = 0.48
_TOOL_DENSE_MAX_SELECTED = 4
_TOOL_VECTOR_CACHE: dict[tuple[str, str, int, str], list[float]] = {}
_TOOL_ENCODER: SemanticEncoder | None = None
_TOOL_ENCODER_LOCK = Lock()

_TOOL_USAGE_HINTS: dict[str, str] = {
    "utility.calculator": "arithmetic calculate math numeric equation sum percentage",
    "utility.current_time": "current date time clock timezone what time is it now",
    "web.search": "search look up current fresh latest public web information news facts",
    "web.fetch_page": "open read inspect summarize a specific public URL web page article link",
    "discord.search_messages": "search earlier Discord chat messages conversation history who said",
    "discord.create_poll": "create start open a poll vote voting choices in Discord",
    "weather.get": "weather rain temperature forecast tomorrow outdoor conditions",
    "random.roll": "roll dice random dice d20 d6 tabletop random number",
    "random.choose": "randomly choose pick select one option fairly",
    "image.search": "search find existing public images pictures photos references",
    "scheduler.remind": "remind notify later schedule a future reminder at a time",
    "scheduler.list": "list show existing reminders scheduled reminders",
    "scheduler.cancel": "cancel remove stop an existing scheduled reminder",
    "places.search": "find nearby restaurants cafes shops attractions places local businesses",
    "file.inspect": "inspect read attached file pdf csv json markdown document attachment",
    "watch.condition": "monitor a future condition notify when something changes becomes available",
    "character.invite": "another character should join contribute answer help react or participate",
    "image.generate": "generate create draw make a new image illustration picture artwork",
}

_EXPLICIT_INTENT_PATTERNS: dict[str, re.Pattern[str]] = {
    "utility.calculator": re.compile(
        r"(?:算(?:一下|下)?|计算|計算|calculator|calculate|\d\s*[+*/%-]\s*\d)", re.I
    ),
    "utility.current_time": re.compile(
        r"(?:几点|幾點|现在时间|現在時間|当地时间|當地時間|what\s+time|current\s+time|time\s+in\b)",
        re.I,
    ),
    "web.search": re.compile(
        r"(?:搜(?:一下|下)?|查(?:一下|下)?|搜索|搜尋|上网查|上網查|search\b|look\s+up|latest\b|最新)",
        re.I,
    ),
    "web.fetch_page": re.compile(
        r"(?:打开|打開|看看|读|讀|阅读|閱讀|open|read|inspect|summari[sz]e).{0,20}https?://|https?://\S+.{0,20}(?:看看|分析|总结|總結)",
        re.I,
    ),
    "discord.search_messages": re.compile(
        r"(?:搜|找|查).{0,12}(?:聊天|消息|訊息|记录|紀錄)|(?:之前|刚才|剛才).{0,12}(?:谁说|誰說)|search.{0,12}(?:discord|messages|chat)",
        re.I,
    ),
    "discord.create_poll": re.compile(
        r"(?:开|開|创建|建立|做|发|發).{0,8}(?:投票|票选|票選)|(?:poll|vote|voting).{0,12}(?:create|start|open)|(?:create|start|open).{0,12}(?:poll|vote)",
        re.I,
    ),
    "weather.get": re.compile(
        r"(?:天气|天氣|下雨|降雨|温度|溫度|气温|氣溫|weather|forecast|rain|temperature)", re.I
    ),
    "random.roll": re.compile(r"(?:掷骰|擲骰|骰子|roll.{0,8}dice|\b\d{0,2}d\d{1,4}\b)", re.I),
    "random.choose": re.compile(
        r"(?:随机|隨機).{0,8}(?:选|選|挑)|random(?:ly)?\s+(?:choose|pick|select)", re.I
    ),
    "image.search": re.compile(
        r"(?:搜图|搜圖|找图|找圖|找.{0,6}(?:图片|圖片|照片)|image\s+search|find.{0,10}(?:image|photo|picture))",
        re.I,
    ),
    "scheduler.remind": re.compile(
        r"(?:提醒我|提醒一下|记得叫我|記得叫我|到时叫我|到時叫我|之后叫我|之後叫我|remind\s+me|set.{0,10}reminder)",
        re.I,
    ),
    "scheduler.list": re.compile(
        r"(?:我的提醒|有哪些提醒|列出.{0,6}提醒|list.{0,10}reminders?|show.{0,10}reminders?)", re.I
    ),
    "scheduler.cancel": re.compile(
        r"(?:取消|撤销|撤銷|删除|刪除).{0,10}提醒|cancel.{0,10}reminder", re.I
    ),
    "places.search": re.compile(
        r"(?:附近|周边|周邊).{0,12}(?:餐厅|餐廳|咖啡|店|景点|景點|地方)|(?:find|search).{0,10}(?:nearby|restaurant|cafe|place|attraction)",
        re.I,
    ),
    "file.inspect": re.compile(
        r"(?:附件|文件|档案|檔案|pdf|csv|json|markdown).{0,16}(?:看|读|讀|分析|检查|檢查|inspect|read)|(?:inspect|read|analy[sz]e).{0,12}(?:file|pdf|attachment)",
        re.I,
    ),
    "watch.condition": re.compile(
        r"(?:一旦|如果|要是|等到).{0,40}(?:通知我|告诉我|告訴我|提醒我)|(?:监控|監控|持续关注|持續關注).{0,30}(?:通知|告诉|告訴)|(?:notify|tell|let\s+me\s+know)\s+me?\s*(?:when|if)|(?:monitor|watch).{0,30}(?:until|for|when)",
        re.I,
    ),
    "image.generate": re.compile(
        r"(?:生成|画|畫|绘制|繪製|做|制作|製作).{0,12}(?:图|圖|图片|圖片|插画|插畫|头像|頭像)|(?:generate|create|draw|make).{0,12}(?:image|picture|illustration|art)",
        re.I,
    ),
}


class BudgetSmartOutputContext(SmartOutputContext):
    """Same Runtime authority as SmartOutputContext with a smaller dynamic protocol prompt."""

    def prompt_guidance(self, candidates: list[ExpressionCandidate]) -> tuple[str, ...]:
        aliases = _expression_aliases(candidates)
        emoji_aliases = {
            alias: item for alias, item in aliases.items() if item.resource_type == "emoji"
        }
        sticker_aliases = {
            alias: item for alias, item in aliases.items() if item.resource_type == "sticker"
        }
        actions = list(self._available_actions(candidates))

        lines = [
            "Smart Output: choose exactly one natural Discord action; Runtime validates references.",
            f"Allowed actions this turn: {', '.join(actions)}.",
        ]
        if self.participation_required:
            lines.extend(
                (
                    "Runtime has already admitted this Character for the current turn.",
                    "Return one visible action. Silence/ignore is not available for this turn.",
                )
            )
        lines.extend(
            (
                "Return exactly one [[CR_OUTPUT {...}]] line and no reasoning or surrounding prose.",
                'Message shape: [[CR_OUTPUT {"action":"message","content":[{"text":"..."}]}]]',
                (
                    'Short message shape: [[CR_OUTPUT {"action":"short_message",'
                    '"content":[{"text":"..."}]}]]'
                ),
                (
                    "For message content, every array item must be one separate JSON object containing "
                    "exactly one of: text, emoji, mention. Never embed an emoji or mention object inside "
                    "a text string."
                ),
            )
        )
        if not self.participation_required:
            lines.append('Silence shape: [[CR_OUTPUT {"action":"ignore"}]]')
        references = ", ".join(self.message_alias_to_id.keys())
        lines.append(f"Message references: {references}.")
        if len(self.message_alias_to_id) > 1:
            lines.append(
                "For message/short_message/sticker, optional reply_to may use one supplied message reference."
            )

        if self.participant_alias_descriptions:
            lines.append(
                "Mentionable participants (use {\"mention\":\"pN\"} as its own message-content item):"
            )
            lines.extend(self.participant_alias_descriptions)

        if emoji_aliases or sticker_aliases:
            lines.append("Retrieved Server expressions:")
            for alias, item in aliases.items():
                meaning = (item.semantic_description or item.semantic_intent or item.name).strip()
                lines.append(
                    f"- {alias}; type={item.resource_type}; name={item.name}; "
                    f"actions={','.join(item.allowed_actions)}; meaning={meaning[:220]}"
                )
        if emoji_aliases:
            lines.extend(
                (
                    (
                        "Custom Emoji: inline Emoji MUST be its own content-array item, for example "
                        'content:[{"text":"前面的文字 "},{"emoji":"e1"},{"text":" 后面的文字"}].'
                    ),
                    (
                        'Never write an Emoji object inside a text value such as '
                        '{"text":"hello {\\"emoji\\":\\"e1\\"}"}. '
                        "For a reaction instead, use action=react with target + emoji when allowed."
                    ),
                )
            )
        if sticker_aliases:
            lines.append("Sticker: action=sticker with sticker=sN; it is the whole social action.")
        if self.participant_alias_descriptions or aliases:
            lines.append(
                "Never invent participant, message, Emoji, or Sticker aliases; never mention yourself."
            )
        return tuple(lines)


def _tool_encoder(settings: Settings) -> SemanticEncoder:
    global _TOOL_ENCODER
    if _TOOL_ENCODER is not None:
        return _TOOL_ENCODER
    with _TOOL_ENCODER_LOCK:
        if _TOOL_ENCODER is None:
            _TOOL_ENCODER = FastEmbedSemanticEncoder(
                model_name=settings.semantic_embedding_model,
                model_file=settings.semantic_embedding_model_file,
                cache_dir=settings.semantic_embedding_cache_dir,
                dimension=settings.semantic_embedding_dimension,
            )
        return _TOOL_ENCODER


def _tool_profile_text(
    tool_id: str,
    display_name: str,
    description: str,
    category: str,
    operation: str,
) -> str:
    hints = _TOOL_USAGE_HINTS.get(tool_id, "")
    return "\n".join(
        item
        for item in (
            f"Tool: {display_name}",
            f"Tool id: {tool_id}",
            f"Category: {category}",
            f"Operation: {operation}",
            f"Purpose: {description}",
            f"Typical requests: {hints}" if hints else "",
        )
        if item
    )


def _explicit_intent(tool_id: str, query: str) -> bool:
    pattern = _EXPLICIT_INTENT_PATTERNS.get(tool_id)
    return bool(pattern and pattern.search(query))


def _character_invite_available(context: ToolExecutionContext) -> bool:
    if context.initiator_is_bot:
        return False
    state = current_character_invite_turn()
    if state is None or state.deployment_id != context.deployment_id:
        return False
    return any(item.kind == "character" for item in state.participants)


def select_tool_ids_for_turn(
    registry: ToolRegistry,
    enabled_tool_ids: tuple[str, ...],
    context: ToolExecutionContext,
    *,
    settings: Settings | None = None,
    encoder: SemanticEncoder | None = None,
) -> tuple[str, ...]:
    """Select a bounded provider-visible subset without changing Deployment authorization."""

    assigned = tuple(dict.fromkeys(item for item in enabled_tool_ids if item))
    if not assigned:
        return ()
    resolved = settings or get_settings()
    # Development/test and explicit semantic-runtime disablement retain legacy Tool exposure.
    if not resolved.semantic_embedding_runtime_enabled:
        return assigned

    catalog = {
        item.id: item for item in registry.catalog() if item.id in assigned and item.available
    }
    available = tuple(item for item in assigned if item in catalog)
    if not available:
        return ()

    query = " ".join(context.trigger_text.split())[:4000]
    if not query:
        return (
            ("character.invite",)
            if "character.invite" in available and _character_invite_available(context)
            else ()
        )

    turn_signals = SemanticTurnSignalStore.get(context.deployment_id, context.message_id)
    continuation_tool_ids = set(
        turn_signals.continuation_tool_ids if turn_signals is not None else ()
    )

    forced: list[str] = []
    for tool_id in available:
        item = catalog[tool_id]
        if tool_id == "character.invite":
            if _character_invite_available(context):
                forced.append(tool_id)
            continue
        explicit = _explicit_intent(tool_id, query)
        continuation = tool_id in continuation_tool_ids
        # Side-effect schemas require either current explicit intent or a scoped semantic pending
        # continuation. Runtime still validates assignment/availability/execution authority later.
        if item.side_effect and not explicit and not continuation:
            continue
        if explicit or continuation:
            forced.append(tool_id)

    try:
        active_encoder = encoder or _tool_encoder(resolved)
        query_vector = active_encoder.embed_query(query)
    except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
        # Embedding outages must not remove capabilities; fall back to assigned/available tools.
        return available

    scored: list[tuple[float, str]] = []
    for tool_id in available:
        item = catalog[tool_id]
        if item.side_effect and tool_id not in forced:
            continue
        semantic_text = _tool_profile_text(
            tool_id,
            item.display_name,
            item.description,
            item.category,
            item.operation,
        )
        cache_key = (
            active_encoder.model_name,
            tool_id,
            active_encoder.dimension,
            semantic_text,
        )
        vector = _TOOL_VECTOR_CACHE.get(cache_key)
        if vector is None:
            try:
                vector = active_encoder.embed_passage(semantic_text)
            except (SemanticEmbeddingUnavailable, ValueError, RuntimeError):
                return available
            _TOOL_VECTOR_CACHE[cache_key] = vector
        dense = _cosine(query_vector, vector)
        if dense >= _TOOL_DENSE_MINIMUM:
            scored.append((dense, tool_id))

    scored.sort(key=lambda item: (-item[0], item[1]))
    selected = list(dict.fromkeys(forced))
    for _, tool_id in scored:
        if tool_id not in selected:
            selected.append(tool_id)
        if len(selected) >= _TOOL_DENSE_MAX_SELECTED:
            break

    selected_set = set(selected[:_TOOL_DENSE_MAX_SELECTED])
    return tuple(tool_id for tool_id in available if tool_id in selected_set)


__all__ = [
    "BudgetSmartOutputContext",
    "select_tool_ids_for_turn",
]
