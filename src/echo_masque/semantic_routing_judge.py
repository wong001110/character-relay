"""Low-frequency model Judge for ambiguous semantic routing decisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field

from echo_masque.admin_runtime import SemanticJudgeEndpoint, SemanticRoutingJudgeProfile
from echo_masque.config import Settings
from echo_masque.persistence import Repository
from echo_masque.provider_capabilities import ModelCapability, ProviderModelCapabilityRegistry
from echo_masque.provider_io import (
    StructuredOutputMode,
    provider_dialect,
    structured_response_format,
)
from echo_masque.services.runtime import RuntimeService, SemanticCredentialKind
from echo_masque.utility_structured_output import exact_json_contract

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class RagJudgePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need_knowledge: bool
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str = Field(default="", max_length=240)


@dataclass(frozen=True, slots=True)
class RagJudgeDecision:
    need_knowledge: bool
    confidence: float
    reason: str
    model: str
    tier: str
    attempts: int
    latency_ms: int


class SemanticRoutingJudgeService:
    """Primary -> availability fallback -> quality escalation Judge cascade."""

    def __init__(self, repository: Repository, settings: Settings) -> None:
        self.runtime = RuntimeService(repository, settings)

    @staticmethod
    def _endpoint(base_url: str) -> str:
        root = base_url.rstrip("/")
        if root.endswith("/v1"):
            return f"{root}/chat/completions"
        return f"{root}/v1/chat/completions"

    @staticmethod
    def _deepseek(base_url: str) -> bool:
        return (urlparse(base_url).hostname or "").casefold() == "api.deepseek.com"

    @staticmethod
    def _parse(text: str) -> RagJudgePayload | None:
        value = text.strip()
        match = _JSON_OBJECT.search(value)
        if match is not None:
            value = match.group(0)
        try:
            return RagJudgePayload.model_validate(json.loads(value))
        except (json.JSONDecodeError, TypeError, ValueError):
            return None

    @staticmethod
    def _capability(mode: StructuredOutputMode) -> ModelCapability | None:
        if mode == "json_schema":
            return "json_schema"
        if mode == "json_object":
            return "json_object"
        return None

    @staticmethod
    def _looks_like_structured_rejection(body: str) -> bool:
        normalized = body.casefold()
        return any(
            token in normalized
            for token in (
                "response_format",
                "json_schema",
                "json object",
                "json_object",
                "structured output",
                "unsupported",
                "not support",
            )
        )

    def _call(
        self,
        *,
        endpoint: SemanticJudgeEndpoint,
        credential_kind: SemanticCredentialKind,
        config: SemanticRoutingJudgeProfile,
        prompt: str,
    ) -> tuple[RagJudgePayload | None, str]:
        key, _ = self.runtime.semantic_credential(credential_kind)
        if key is None:
            return None, "missing_credential"
        base_payload: dict[str, object] = {
            "model": endpoint.model,
            "temperature": 0,
            "max_tokens": config.max_output_tokens,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{config.system_prompt}\n\n"
                        + exact_json_contract(
                            RagJudgePayload,
                            schema_version="semantic-routing-rag-v1",
                        )
                    ),
                },
                {"role": "user", "content": prompt[: config.max_input_chars]},
            ],
        }
        if self._deepseek(endpoint.base_url):
            base_payload["thinking"] = {"type": "disabled"}

        last_status = "provider_error"
        for mode in provider_dialect(endpoint.provider).structured_output_modes:
            capability = self._capability(mode)
            if capability is not None and not ProviderModelCapabilityRegistry.allows(
                provider=endpoint.provider,
                model=endpoint.model,
                base_url=endpoint.base_url,
                capability=capability,
            ):
                continue
            payload = dict(base_payload)
            response_format = structured_response_format(
                RagJudgePayload,
                schema_name="rag_judge",
                mode=mode,
            )
            if response_format is not None:
                payload["response_format"] = response_format
            try:
                with httpx.Client(timeout=config.timeout_seconds) as client:
                    response = client.post(
                        self._endpoint(endpoint.base_url),
                        json=payload,
                        headers={
                            "Authorization": f"Bearer {key.get_secret_value()}",
                            "Content-Type": "application/json",
                        },
                    )
                if response.status_code >= 400:
                    last_status = f"http_{response.status_code}"
                    if capability is not None and self._looks_like_structured_rejection(
                        response.text
                    ):
                        ProviderModelCapabilityRegistry.observe(
                            provider=endpoint.provider,
                            model=endpoint.model,
                            base_url=endpoint.base_url,
                            capability=capability,
                            supported=False,
                            detail=response.text[:500],
                        )
                        continue
                    return None, last_status
                body = response.json()
                content = body["choices"][0]["message"]["content"]
                if not isinstance(content, str):
                    last_status = "invalid_content"
                    if capability is not None:
                        continue
                    return None, last_status
                parsed = self._parse(content)
                if parsed is None:
                    last_status = "invalid_json"
                    if capability is not None:
                        continue
                    return None, last_status
                if capability is not None:
                    ProviderModelCapabilityRegistry.observe(
                        provider=endpoint.provider,
                        model=endpoint.model,
                        base_url=endpoint.base_url,
                        capability=capability,
                        supported=True,
                    )
                return parsed, "ok"
            except (
                httpx.HTTPError,
                KeyError,
                IndexError,
                TypeError,
                ValueError,
                json.JSONDecodeError,
            ):
                return None, "provider_error"
        return None, last_status

    @staticmethod
    def _prompt(
        *,
        current_message: str,
        contextual_query: str,
        route_labels: tuple[str, ...],
        dense_score: float,
        sparse_score: float,
    ) -> str:
        routes = "\n".join(f"- {item}" for item in route_labels[:8]) or "- none"
        context = (
            contextual_query
            if contextual_query != current_message
            else "(same as current)"
        )
        return (
            "Decide whether Knowledge should be injected into the CURRENT turn.\n\n"
            f"CURRENT MESSAGE:\n{current_message[:1800]}\n\n"
            "PRIOR/CONTEXTUAL QUERY (continuity evidence only):\n"
            f"{context[:2200]}\n\n"
            f"ELIGIBLE KNOWLEDGE ROUTES:\n{routes}\n\n"
            f"E5 dense score: {dense_score:.6f}\n"
            f"Sparse score: {sparse_score:.6f}\n\n"
            "Return JSON only."
        )

    def _decision(
        self,
        *,
        payload: RagJudgePayload,
        model: str,
        tier: str,
        attempts: int,
        started: float,
    ) -> RagJudgeDecision:
        return RagJudgeDecision(
            need_knowledge=payload.need_knowledge,
            confidence=payload.confidence,
            reason=payload.reason,
            model=model,
            tier=tier,
            attempts=attempts,
            latency_ms=round((perf_counter() - started) * 1000),
        )

    def decide(
        self,
        *,
        current_message: str,
        contextual_query: str,
        route_labels: tuple[str, ...],
        dense_score: float,
        sparse_score: float,
    ) -> RagJudgeDecision | None:
        config = self.runtime.semantic_routing_config()
        if not config.enabled or not config.rag_enabled:
            return None
        prompt = self._prompt(
            current_message=current_message,
            contextual_query=contextual_query,
            route_labels=route_labels,
            dense_score=dense_score,
            sparse_score=sparse_score,
        )
        started = perf_counter()
        attempts = 1
        primary, primary_status = self._call(
            endpoint=config.primary,
            credential_kind="semantic_primary",
            config=config,
            prompt=prompt,
        )
        if primary is not None and primary.confidence >= config.confidence_threshold:
            return self._decision(
                payload=primary,
                model=config.primary.model,
                tier="primary",
                attempts=attempts,
                started=started,
            )

        if primary is None and primary_status not in {"invalid_json", "invalid_content"}:
            attempts += 1
            fallback, _ = self._call(
                endpoint=config.availability_fallback,
                credential_kind="semantic_availability",
                config=config,
                prompt=prompt,
            )
            if fallback is not None and fallback.confidence >= config.confidence_threshold:
                return self._decision(
                    payload=fallback,
                    model=config.availability_fallback.model,
                    tier="availability",
                    attempts=attempts,
                    started=started,
                )

        attempts += 1
        quality, _ = self._call(
            endpoint=config.quality_escalation,
            credential_kind="semantic_quality",
            config=config,
            prompt=prompt,
        )
        if quality is None or quality.confidence < config.confidence_threshold:
            return None
        return self._decision(
            payload=quality,
            model=config.quality_escalation.model,
            tier="quality",
            attempts=attempts,
            started=started,
        )


__all__ = ["RagJudgeDecision", "SemanticRoutingJudgeService"]
