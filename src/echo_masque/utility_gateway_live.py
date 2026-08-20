"""Live Utility caller built on Character Relay's existing provider clients."""

from __future__ import annotations

import asyncio
from concurrent.futures import ThreadPoolExecutor

from pydantic import BaseModel

from echo_masque.provider_capabilities import ProviderModelCapabilityRegistry
from echo_masque.provider_io import complete_structured
from echo_masque.providers.base import ChatMessage, ProviderCompletion
from echo_masque.providers.errors import (
    ProviderAuthenticationError,
    ProviderBillingRequiredError,
    ProviderCapabilityUnsupportedError,
    ProviderError,
    ProviderInsufficientBalanceError,
    ProviderModelNotFoundError,
    ProviderProtocolError,
    ProviderQuotaExhaustedError,
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
    "cloudflare",
    "mistral",
    "sambanova",
    "gemini",
}


class _GeminiOpenAIProvider(OpenAICompatibleProvider):
    @property
    def endpoint(self) -> str:
        return f"{self._base_url.rstrip('/')}/chat/completions"


class ExistingProviderUtilityCaller(UtilityProviderCaller):
    """Run Utility calls with model-scoped structured-output compatibility learning."""

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

    @classmethod
    async def _complete_structured(
        cls,
        route: UtilityRoute,
        *,
        schema: type[BaseModel],
        schema_name: str,
        schema_version: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderCompletion:
        base_url = cls._base_url(route)
        return await complete_structured(
            cls._provider(route),
            provider_id=route.provider,
            base_url=base_url,
            model=route.model,
            schema=schema,
            schema_name=schema_name,
            schema_version=schema_version,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=temperature,
            max_output_tokens=max_output_tokens,
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

    def _wait_for_structured_completion(
        self,
        route: UtilityRoute,
        *,
        schema: type[BaseModel],
        schema_name: str,
        schema_version: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> ProviderCompletion:
        future = _EXECUTOR.submit(
            self._run,
            self._complete_structured(
                route,
                schema=schema,
                schema_name=schema_name,
                schema_version=schema_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            ),
        )
        try:
            return future.result(timeout=8.0)
        except TimeoutError as exc:
            future.cancel()
            raise ProviderTimeoutError("utility caller timeout") from exc

    @staticmethod
    def _reset_from_quota(exc: ProviderRateLimitError | ProviderQuotaExhaustedError):
        resets = [item.reset_at for item in exc.quota_observations if item.reset_at is not None]
        reset_at = min(resets) if resets else None
        zero = next((item for item in exc.quota_observations if item.remaining == 0), None)
        return reset_at, zero

    @classmethod
    def _reply(cls, completion: ProviderCompletion) -> UtilityCallReply:
        return UtilityCallReply(
            text=completion.text,
            latency_ms=completion.latency_ms,
            input_tokens=completion.input_tokens or 0,
            output_tokens=completion.output_tokens or 0,
            quota_observations=completion.quota_observations,
        )

    @classmethod
    def _raise_utility_failure(cls, exc: ProviderError) -> None:
        if isinstance(exc, (ProviderRateLimitError, ProviderQuotaExhaustedError)):
            reset_at, zero = cls._reset_from_quota(exc)
            raise UtilityCallFailed(
                "quota",
                detail=(
                    f"free_tier_exhausted:{exc}"
                    if isinstance(exc, ProviderQuotaExhaustedError) and exc.free_tier
                    else f"quota_exhausted:{exc}"
                ),
                remaining_value=(
                    0
                    if isinstance(exc, ProviderQuotaExhaustedError)
                    else (zero.remaining if zero is not None else None)
                ),
                remaining_unit=(zero.unit if zero is not None else "requests"),
                reset_at=reset_at,
                quota_observations=exc.quota_observations,
            ) from exc
        if isinstance(exc, ProviderBillingRequiredError):
            raise UtilityCallFailed("authentication", detail=f"billing_required:{exc}") from exc
        if isinstance(exc, ProviderInsufficientBalanceError):
            raise UtilityCallFailed("authentication", detail=f"insufficient_balance:{exc}") from exc
        if isinstance(exc, ProviderModelNotFoundError):
            raise UtilityCallFailed("authentication", detail=f"model_not_found:{exc}") from exc
        if isinstance(exc, ProviderAuthenticationError):
            raise UtilityCallFailed("authentication", detail=str(exc)) from exc
        if isinstance(exc, ProviderCapabilityUnsupportedError):
            raise UtilityCallFailed(
                "protocol",
                detail=f"capability_unsupported:{exc.capability}:{exc}",
            ) from exc
        if isinstance(exc, ProviderTimeoutError):
            raise UtilityCallFailed("timeout", detail=str(exc)) from exc
        if isinstance(exc, ProviderUnavailableError):
            raise UtilityCallFailed("unavailable", detail=str(exc)) from exc
        if isinstance(exc, ProviderProtocolError):
            raise UtilityCallFailed("protocol", detail=str(exc)) from exc
        raise UtilityCallFailed("unavailable", detail=str(exc)) from exc

    def call_structured(
        self,
        route: UtilityRoute,
        *,
        schema: type[BaseModel],
        schema_name: str,
        schema_version: str,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        try:
            completion = self._wait_for_structured_completion(
                route,
                schema=schema,
                schema_name=schema_name,
                schema_version=schema_version,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                max_output_tokens=max_output_tokens,
                temperature=temperature,
            )
        except ProviderError as exc:
            self._raise_utility_failure(exc)
            raise AssertionError("unreachable")
        return self._reply(completion)

    def call(
        self,
        route: UtilityRoute,
        *,
        system_prompt: str,
        user_prompt: str,
        max_output_tokens: int,
        temperature: float,
    ) -> UtilityCallReply:
        base_url = self._base_url(route)
        use_json_object = (
            route.provider in _JSON_OBJECT_PROVIDERS
            and ProviderModelCapabilityRegistry.allows(
                provider=route.provider,
                model=route.model,
                base_url=base_url,
                capability="json_object",
            )
        )
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
                if use_json_object:
                    ProviderModelCapabilityRegistry.observe(
                        provider=route.provider,
                        model=route.model,
                        base_url=base_url,
                        capability="json_object",
                        supported=True,
                    )
            except ProviderCapabilityUnsupportedError as exc:
                if not use_json_object or exc.capability != "json_object":
                    raise
                ProviderModelCapabilityRegistry.observe(
                    provider=route.provider,
                    model=route.model,
                    base_url=base_url,
                    capability="json_object",
                    supported=False,
                    detail=str(exc),
                )
                completion = self._wait_for_completion(
                    route,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    max_output_tokens=max_output_tokens,
                    temperature=temperature,
                    json_object=False,
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
        except ProviderError as exc:
            self._raise_utility_failure(exc)
            raise AssertionError("unreachable")
        return self._reply(completion)


__all__ = ["ExistingProviderUtilityCaller"]
