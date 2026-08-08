"""Deployment-scoped Tool Calling registry and deterministic V1 utilities."""

from __future__ import annotations

import ast
import json
import math
from dataclasses import dataclass
from datetime import datetime
from time import perf_counter
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from echo_masque.providers import (
    ChatToolCall,
    ChatToolDefinition,
    ChatToolFunction,
)

ToolOperation = Literal["read", "write", "coordination"]
ToolRisk = Literal["low", "medium", "high"]
ToolExecutionStatus = Literal["completed", "failed", "rejected"]


class ToolCatalogItem(BaseModel):
    """Safe metadata exposed to the Portal for manual deployment assignment."""

    model_config = ConfigDict(frozen=True)
    id: str
    display_name: str
    description: str
    category: str
    operation: ToolOperation
    risk: ToolRisk
    side_effect: bool
    provider_function_name: str


class ToolExecutionTrace(BaseModel):
    """Privacy-safe Tool Calling trace; arguments and results are intentionally omitted."""

    model_config = ConfigDict(frozen=True)
    tool_id: str
    status: ToolExecutionStatus
    duration_ms: int = 0
    error: str = ""


class ToolExecutionResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    content: str
    trace: ToolExecutionTrace


@dataclass(frozen=True)
class ToolExecutionContext:
    owner_id: str
    deployment_id: str
    character_card_id: str
    platform: str


@dataclass(frozen=True)
class RegisteredTool:
    catalog: ToolCatalogItem
    provider_schema: ChatToolDefinition


class CalculatorInput(BaseModel):
    expression: str = Field(min_length=1, max_length=200)


class CurrentTimeInput(BaseModel):
    timezone: str = Field(default="UTC", min_length=1, max_length=120)


def _json_result(**values: object) -> str:
    return json.dumps(values, ensure_ascii=False, separators=(",", ":"))


def _number(value: object) -> float | int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("Only numeric literals are allowed.")
    numeric = float(value)
    if not math.isfinite(numeric) or abs(numeric) > 1e100:
        raise ValueError("Numeric literal is outside the supported range.")
    return value


def _evaluate_expression(expression: str) -> float | int:
    try:
        tree = ast.parse(expression, mode="eval")
    except SyntaxError as exc:
        raise ValueError("Expression is not valid arithmetic.") from exc
    if sum(1 for _ in ast.walk(tree)) > 60:
        raise ValueError("Expression is too complex.")

    def evaluate(node: ast.AST) -> float | int:
        if isinstance(node, ast.Expression):
            return evaluate(node.body)
        if isinstance(node, ast.Constant):
            return _number(node.value)
        if isinstance(node, ast.UnaryOp):
            operand = evaluate(node.operand)
            if isinstance(node.op, ast.UAdd):
                result: float | int = +operand
            elif isinstance(node.op, ast.USub):
                result = -operand
            else:
                raise ValueError("Unsupported unary operator.")
            return _checked_result(result)
        if isinstance(node, ast.BinOp):
            left = evaluate(node.left)
            right = evaluate(node.right)
            try:
                if isinstance(node.op, ast.Add):
                    result = left + right
                elif isinstance(node.op, ast.Sub):
                    result = left - right
                elif isinstance(node.op, ast.Mult):
                    result = left * right
                elif isinstance(node.op, ast.Div):
                    result = left / right
                elif isinstance(node.op, ast.FloorDiv):
                    result = left // right
                elif isinstance(node.op, ast.Mod):
                    result = left % right
                elif isinstance(node.op, ast.Pow):
                    if abs(float(right)) > 12:
                        raise ValueError("Exponent is outside the supported range.")
                    result = left**right
                else:
                    raise ValueError("Unsupported arithmetic operator.")
            except (OverflowError, ZeroDivisionError) as exc:
                raise ValueError("Arithmetic operation could not be completed.") from exc
            return _checked_result(result)
        raise ValueError("Only arithmetic literals and operators are allowed.")

    return evaluate(tree)


def _checked_result(value: float | int) -> float | int:
    numeric = float(value)
    if not math.isfinite(numeric) or abs(numeric) > 1e100:
        raise ValueError("Arithmetic result is outside the supported range.")
    if isinstance(value, float) and value.is_integer() and abs(value) < 9_007_199_254_740_992:
        return int(value)
    return value


def _calculator(arguments: dict[str, object]) -> str:
    payload = CalculatorInput.model_validate(arguments)
    result = _evaluate_expression(payload.expression)
    return _json_result(ok=True, expression=payload.expression, result=result)


def _current_time(arguments: dict[str, object]) -> str:
    payload = CurrentTimeInput.model_validate(arguments)
    try:
        timezone = ZoneInfo(payload.timezone)
    except ZoneInfoNotFoundError as exc:
        raise ValueError("Unknown IANA timezone.") from exc
    current = datetime.now(timezone)
    return _json_result(
        ok=True,
        timezone=payload.timezone,
        iso=current.isoformat(timespec="seconds"),
        date=current.date().isoformat(),
        time=current.timetz().isoformat(timespec="seconds"),
        utc_offset=current.strftime("%z")[:3] + ":" + current.strftime("%z")[3:],
    )


class ToolRegistry:
    """Small explicit registry. V1 intentionally does not use embedding-based Tool Retrieval."""

    def __init__(self) -> None:
        registered = (
            RegisteredTool(
                catalog=ToolCatalogItem(
                    id="utility.calculator",
                    display_name="Calculator",
                    description=(
                        "Perform deterministic arithmetic. Use it when an exact numeric result "
                        "is needed instead of relying on mental arithmetic."
                    ),
                    category="utility",
                    operation="read",
                    risk="low",
                    side_effect=False,
                    provider_function_name="utility_calculator",
                ),
                provider_schema=ChatToolDefinition(
                    function=ChatToolFunction(
                        name="utility_calculator",
                        description=(
                            "Calculate an arithmetic expression exactly. Use only for arithmetic; "
                            "do not put prose or code in the expression."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "expression": {
                                    "type": "string",
                                    "description": (
                                        "Arithmetic expression, for example "
                                        "(8 * 0.27) + 2."
                                    ),
                                }
                            },
                            "required": ["expression"],
                            "additionalProperties": False,
                        },
                    )
                ),
            ),
            RegisteredTool(
                catalog=ToolCatalogItem(
                    id="utility.current_time",
                    display_name="Current Time",
                    description=(
                        "Read the current real-world date and time for an IANA timezone. "
                        "Do not guess a user's location when the timezone is unknown."
                    ),
                    category="utility",
                    operation="read",
                    risk="low",
                    side_effect=False,
                    provider_function_name="utility_current_time",
                ),
                provider_schema=ChatToolDefinition(
                    function=ChatToolFunction(
                        name="utility_current_time",
                        description=(
                            "Get the current date and time. Pass an IANA timezone such as "
                            "Asia/Kuala_Lumpur when the location or timezone is known; otherwise "
                            "omit it and the tool returns UTC."
                        ),
                        parameters={
                            "type": "object",
                            "properties": {
                                "timezone": {
                                    "type": "string",
                                    "description": "IANA timezone name, e.g. Asia/Kuala_Lumpur.",
                                    "default": "UTC",
                                }
                            },
                            "additionalProperties": False,
                        },
                    )
                ),
            ),
        )
        self._by_id = {item.catalog.id: item for item in registered}
        self._by_provider_name = {
            item.catalog.provider_function_name: item for item in registered
        }

    def catalog(self) -> tuple[ToolCatalogItem, ...]:
        return tuple(item.catalog for item in self._by_id.values())

    def validate_ids(self, values: list[str] | tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in values if item.strip()))
        unknown = [item for item in normalized if item not in self._by_id]
        if unknown:
            raise ValueError(f"Unknown or unavailable Tool: {', '.join(unknown)}")
        return normalized

    def provider_tools(self, enabled_tool_ids: tuple[str, ...]) -> tuple[ChatToolDefinition, ...]:
        enabled = set(self.validate_ids(enabled_tool_ids))
        return tuple(
            item.provider_schema
            for tool_id, item in self._by_id.items()
            if tool_id in enabled
        )

    def tool_id_for_provider_name(self, provider_name: str) -> str | None:
        item = self._by_provider_name.get(provider_name)
        return item.catalog.id if item is not None else None

    def execute(
        self,
        call: ChatToolCall,
        *,
        enabled_tool_ids: tuple[str, ...],
        context: ToolExecutionContext,
    ) -> ToolExecutionResult:
        del context  # Reserved for platform/permission-aware tools in later V1 slices.
        started = perf_counter()
        registered = self._by_provider_name.get(call.function.name)
        if registered is None:
            return self._error_result(
                tool_id=call.function.name,
                status="rejected",
                error="unknown_tool",
                started=started,
            )
        tool_id = registered.catalog.id
        if tool_id not in set(enabled_tool_ids):
            return self._error_result(
                tool_id=tool_id,
                status="rejected",
                error="tool_not_assigned_to_deployment",
                started=started,
            )
        try:
            raw_arguments = json.loads(call.function.arguments or "{}")
            if not isinstance(raw_arguments, dict):
                raise ValueError("Tool arguments must be a JSON object.")
            arguments = {str(key): value for key, value in raw_arguments.items()}
            if tool_id == "utility.calculator":
                content = _calculator(arguments)
            elif tool_id == "utility.current_time":
                content = _current_time(arguments)
            else:  # pragma: no cover - registry and executor are changed together.
                raise ValueError("Tool executor is unavailable.")
        except (json.JSONDecodeError, ValidationError, ValueError, TypeError) as exc:
            return self._error_result(
                tool_id=tool_id,
                status="rejected",
                error=str(exc)[:300],
                started=started,
            )
        return ToolExecutionResult(
            content=content,
            trace=ToolExecutionTrace(
                tool_id=tool_id,
                status="completed",
                duration_ms=round((perf_counter() - started) * 1000),
            ),
        )

    @staticmethod
    def _error_result(
        *,
        tool_id: str,
        status: Literal["failed", "rejected"],
        error: str,
        started: float,
    ) -> ToolExecutionResult:
        safe_error = error[:300]
        return ToolExecutionResult(
            content=_json_result(ok=False, error=safe_error),
            trace=ToolExecutionTrace(
                tool_id=tool_id,
                status=status,
                duration_ms=round((perf_counter() - started) * 1000),
                error=safe_error,
            ),
        )


_DEFAULT_TOOL_REGISTRY = ToolRegistry()


def default_tool_registry() -> ToolRegistry:
    return _DEFAULT_TOOL_REGISTRY
