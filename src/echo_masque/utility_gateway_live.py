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


class _GeminiOpenAIProvider(OpenAICompatibleProvider):
    @property
    def endpoint(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"


class ExistingProviderUtilityCaller(UtilityProviderCaller):
    """Keep network credential handling inside the existing provider implementation."""

    @staticmethod
    def _base_url(route: UtilityRoute) -> str:
        if route.provider == "gemini":
            return "https://generativelanguage.googleapis.com/v1beta/openai"
        return route.base_url

    @classmethod
    def _provider(cls, route: UtilityRoute) -> OpenAICompatibleProvider:
        base_url = cls._base_url(route)
        provider_type = (
            _GeminiOpenAIProvider
            if route.provider == "gemini"
            else OpenAICompatibleProvider
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
        temperature: float,
    ) -> ProviderCompletion:
        provider = cls._provider(route)
        return await provider.complete(
            messages=(
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=user_prompt),
            ),
            model=route.model,
            temperature=temperature,
        )

    @staticmethod
    def _run(coroutine: object) -> ProviderCompletion:
        return asyncio.run(coroutine)  # type: ignore[arg-type]

    def call(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        del max_output_tokens
        future = _EXECUTOR.submit(
            self._run,
            self._complete(
                route,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                temperature=temperature,
            ),
        )
        try:
            completion = future.result(timeout=8.0)
        except ProviderRateLimitError as exc:
            raise UtilityCallFailed("quota", detail=str(exc)) from exc
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
        except TimeoutError as exc:
            future.cancel()
            raise UtilityCallFailed("timeout", detail="utility caller timeout") from exc
        return UtilityCallReply(
            text=completion.text,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens or 0,
            output_tokens=completion.output_tokens or 0,
        )


__all__ = ["ExistingProviderUtilityCaller"]
