"""Low-frequency model Judge for ambiguous semantic routing decisions."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from time import perf_counter
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from echo_masque.admin_runtime import SemanticJudgeEndpoint, SemanticRoutingJudgeProfile
from echo_masque.config import Settings
from echo_masque.persistence import Repository
from echo_masque.services.runtime import RuntimeService, SemanticCredentialKind

_JSON_OBJECT = re.compile(r"\{.*\}", re.DOTALL)


class RagJudgePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

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
        return f"{root}/chat/completions" if root.endswith("/v1") else f"{root}/v1/chat/completions"

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
        payload: dict[str, object] = {
            "model": endpoint.model,
            "temperature": 0,
            "max_tokens": config.max_output_tokens,
            "messages": [
                {"role": "system", "content": config.system_prompt},
                {"role": "user", "content": prompt[: config.max_input_chars]},
            ],
        }
        if self._deepseek(endpoint.base_url):
            payload["thinking"] = {"type": "disabled"}
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
                return None, f"http_{response.status_code}"
            body = response.json()
            content = body["choices"][0]["message"]["content"]
            if not isinstance(content, str):
                return None, "invalid_content"
            parsed = self._parse(content)
            return parsed, "ok" if parsed is not None else "invalid_json"
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return None, "provider_error"

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
        context = contextual_query if contextual_query != current_message else "(same as current)"
        return (
            "Decide whether Knowledge should be injected into the CURRENT turn.\n\n"
            f"CURRENT MESSAGE:\n{current_message[:1800]}\n\n"
            f"PRIOR/CONTEXTUAL QUERY (continuity evidence only):\n{context[:2200]}\n\n"
            f"ELIGIBLE KNOWLEDGE ROUTES:\n{routes}\n\n"
            f"E5 dense score: {dense_score:.6f}\n"
            f"Sparse score: {sparse_score:.6f}\n\n"
            "Return JSON only."
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
        attempts = 0

        attempts += 1
        primary, primary_status = self._call(
            endpoint=config.primary,
            credential_kind="semantic_primary",
            config=config,
            prompt=prompt,
        )
        if primary is not None and primary.confidence >= config.confidence_threshold:
            return RagJudgeDecision(
                need_knowledge=primary.need_knowledge,
                confidence=primary.confidence,
                reason=primary.reason,
                model=config.primary.model,
                tier="primary",
                attempts=attempts,
                latency_ms=round((perf_counter() - started) * 1000),
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
                return RagJudgeDecision(
                    need_knowledge=fallback.need_knowledge,
                    confidence=fallback.confidence,
                    reason=fallback.reason,
                    model=config.availability_fallback.model,
                    tier="availability",
                    attempts=attempts,
                    latency_ms=round((perf_counter() - started) * 1000),
                )

        attempts += 1
        quality, _ = self._call(
            endpoint=config.quality_escalation,
            credential_kind="semantic_quality",
            config=config,
            prompt=prompt,
        )
        if quality is None:
            return None
        return RagJudgeDecision(
            need_knowledge=quality.need_knowledge,
            confidence=quality.confidence,
            reason=quality.reason,
            model=config.quality_escalation.model,
            tier="quality",
            attempts=attempts,
            latency_ms=round((perf_counter() - started) * 1000),
        )


__all__ = ["RagJudgeDecision", "SemanticRoutingJudgeService"]
