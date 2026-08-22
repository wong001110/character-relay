import json

import pytest

from scripts.live_phase16_acceptance import (
    validate_prompt_export,
    validate_prompt_inspection,
)

RAW_PROMPT = "You are the acceptance fixture."
COMPILED_PROMPT = f"Character contract\n\nRaw prompt:\n{RAW_PROMPT}"


def test_live_acceptance_validates_raw_and_compiled_prompt_contract() -> None:
    inspected = {
        "raw_system_prompt": RAW_PROMPT,
        "compiled_system_prompt": COMPILED_PROMPT,
        "system_prompt": COMPILED_PROMPT,
        "messages": [{"role": "system", "content": COMPILED_PROMPT}],
    }

    assert (
        validate_prompt_inspection(inspected, exact_prompt=RAW_PROMPT)
        == COMPILED_PROMPT
    )

    exports = {
        "raw": RAW_PROMPT + "\n",
        "text": COMPILED_PROMPT + "\n",
        "markdown": f"## Raw\n{RAW_PROMPT}\n## Compiled\n{COMPILED_PROMPT}\n",
        "json": json.dumps(inspected),
        "openai": json.dumps(
            {"messages": [{"role": "system", "content": COMPILED_PROMPT}]}
        ),
    }
    for export_format, body in exports.items():
        validate_prompt_export(
            export_format,
            body,
            raw_prompt=RAW_PROMPT,
            compiled_prompt=COMPILED_PROMPT,
        )


def test_live_acceptance_rejects_raw_prompt_as_runtime_message() -> None:
    inspected = {
        "raw_system_prompt": RAW_PROMPT,
        "compiled_system_prompt": COMPILED_PROMPT,
        "system_prompt": RAW_PROMPT,
        "messages": [{"role": "system", "content": RAW_PROMPT}],
    }

    with pytest.raises(RuntimeError, match="Runtime System Message was not compiled"):
        validate_prompt_inspection(inspected, exact_prompt=RAW_PROMPT)
