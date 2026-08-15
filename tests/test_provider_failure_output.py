import asyncio
from types import SimpleNamespace
from typing import Any, cast

from echo_masque.connector_runtime import DiscordConnectorRuntime
from echo_masque.domain import TargetResponse


class FailingSmartContext:
    def parse_and_resolve(self, *_: object, **__: object) -> tuple[None, str]:
        raise AssertionError("Provider failure must bypass Smart Output parsing and repair.")


def test_provider_failure_is_not_repaired_as_character_ignore() -> None:
    runtime = object.__new__(DiscordConnectorRuntime)
    prepared = SimpleNamespace(
        resolved=SimpleNamespace(
            payload=SimpleNamespace(expression_candidates=[]),
            deployment=SimpleNamespace(id="deployment-1"),
            target=SimpleNamespace(),
            target_record=SimpleNamespace(target_kind="prompt_model"),
        ),
        smart_context=FailingSmartContext(),
        prompt="unused",
    )
    response = TargetResponse(
        text='[[CR_OUTPUT {"action":"ignore"}]]',
        latency_ms=0,
        trace={"provider_failure": "provider_timeout"},
    )

    output = asyncio.run(
        runtime.resolve_character_output(cast(Any, prepared), response)
    )

    assert output.smart_output.action == "ignore"
    assert output.smart_reason == "provider_turn_failed:provider_timeout"
    assert output.final_response is response
