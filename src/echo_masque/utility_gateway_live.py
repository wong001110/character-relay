"""Live Utility caller built on Character Relay's existing provider clients."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from echo_masque.providers.base import ChatMessage, ProviderCompletion
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderError,
    ProviderProtocolError,
    ProviderRateLimitError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from echo_masque.providers.openai_compatible import OpenAICompatibleProvider
from echo_masque.utility_gateway_contracts import UtilityRoute
from echo_masque.utility_gateway_router import (
    UtilityCallFailed,
    UtilityCallReply,
    UtilityProviderCaller,
)

_EXECUTOR = ThreadPoolExecutor(max_workers=4, thread_name_prefix="utility-gateway")
_JSON_OBJECT_PROVIDERS = {
    "openrouter",
    "groq",
    "cerebras",
    "mistral",
    "sambanova",
    "gemini",
}


class _GeminiOpenAIProvider(OpenAICompatibleProvider):
    @property
    def endpoint(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"


class ExistingProviderUtilityCaller(UtilityProviderCaller):
    """Keep network credential handling inside the existing provider implementation.

    Standard OpenAI-compatible Utility providers are first asked for JSON-object mode. If a
    provider rejects that request shape, the caller retries that provider once in prompt-only
    compatibility mode. Runtime still validates the returned Pydantic contract.
    """

    @staticmethod
    def _base_url(route: UtilityRoute) -> str:
        if route.provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return route.base_url

    @classmethod
    def _provider(cls, route: UtilityRoute) -> OpenAICompatibleProvider:
        base_url = cls._base_url(route)
        provider_type = (
            _GeminiOpenAIProvider if route.provider == "gemini" else OpenAICompatibleProvider
        )
        return provider_type(
            base_url=base_url,
            api_key=route.api_key,
            timeout_seconds=6.0,
            max_retries=0,
        )

    @classmethod
    async def _complete(
        cls,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
        json_object: bool,
    ) -> ProviderCompletion:
        provider = cls._provider(route)
        return await provider.complete(
            messages=(
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ),
            model=route.model,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
            response_format={"type": "json_object"} if json_object else None,
        )

    @staticmethod
    def _run(coroutine: object) -> ProviderCompletion:
        return asyncio.run(coroutine)  # type: ignore[arg-type]

    def _wait_for_completion(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
        json_object: bool,
    ) -> ProviderCompletion:
        future = _EXECUTOR.submit(
            self._run,
            self._complete(
                route,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
                json_object=json_object,
            ),
        )
        try:
            return future.result(timeout=8.0)
        except TimeoutError as exc:
            future.cancel()
            raise ProviderTimeoutError("utility caller timeout") from exc

    def call(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        use_json_object = route.provider in _JSON_OBJECT_PROVIDERS
        try:
            try:
                completion = self._wait_for_completion(
                    route,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    json_object=use_json_object,
                )
            except ProviderProtocolError:
                if not use_json_object:
                    raise
                completion = self._wait_for_completion(
                    route,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    json_object=False,
                )
        except ProviderRateLimitError as exc:
            resets = [item.reset_at for item in exc.quota_observations if item.reset_at is not None]
            reset_at = min(resets) if resets else None
            zero = next(
                (item for item in exc.quota_observations if item.remaining == 0),
                None,
            )
            raise UtilityCallFailed(
                "quota",
                detail=str(exc),
                remaining_value=zero.remaining if zero is not None else None,
                remaining_unit=zero.unit if zero is not None else "",
                reset_at=reset_at,
                quota_observations=exc.quota_observations,
            ) from exc
        except ProviderAuthenticationError as exc:
            raise UtilityCallFailed("authentication", detail=str(exc)) from exc
        except ProviderTimeoutError as exc:
            raise UtilityCallFailed("timeout", detail=str(exc)) from exc
        except ProviderUnavailableError as exc:
            raise UtilityCallFailed("unavailable", detail=str(exc)) from exc
        except ProviderProtocolError as exc:
            raise UtilityCallFailed("protocol", detail=str(exc)) from exc
        except ProviderError as exc:
            raise UtilityCallFailed("unavailable", detail=str(exc)) from exc
        return UtilityCallReply(
            text=completion.text,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens or 0,
            output_tokens=completion.output_tokens or 0,
            quota_observations=completion.quota_observations,
        )


__all__ = ["ExistingProviderUtilityCaller"]
