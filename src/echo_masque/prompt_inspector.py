"""Authoritative, secret-free Character Prompt inspection and export."""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict

from echo_masque.matrix import PromptVersionView
from echo_masque.persistence import MatrixRepository, Repository
from echo_masque.targets import PromptModelConfig

PromptExportFormat = Literal["text", "markdown", "json", "openai"]


class PromptMessageView(BaseModel):
    model_config = ConfigDict(frozen=True)

    role: Literal["system"] = "system"
    content: str


class CharacterPromptView(BaseModel):
    model_config = ConfigDict(frozen=True)

    character_card_id: str
    display_name: str
    target_id: str
    runtime_kind: Literal["prompt_model"] = "prompt_model"
    provider: str
    base_url: str
    model: str
    temperature: float
    system_prompt: str
    messages: list[PromptMessageView]
    prompt_version_id: str | None
    prompt_version: int | None
    prompt_version_label: str | None
    config_hash: str | None


class PromptUnavailable(RuntimeError):
    """Raised when a Character Card has no Provider-backed System Prompt."""


class CharacterPromptInspector:
    def __init__(
        self,
        repository: Repository,
        matrix_repository: MatrixRepository,
    ) -> None:
        self.repository = repository
        self.matrix_repository = matrix_repository

    def inspect(self, owner_id: str, card_id: str) -> CharacterPromptView | None:
        card = self.repository.get_character_card(card_id, owner_id)
        if card is None:
            return None
        target = self.repository.get_target(card.target_id)
        if target is None:
            raise PromptUnavailable("Character Target binding was not found.")
        if target.target_kind != "prompt_model":
            raise PromptUnavailable(
                "This Character Card uses a deterministic or external Target and has no "
                "Provider System Prompt."
            )
        config = PromptModelConfig.model_validate_json(target.config_json)
        versions = self.matrix_repository.list_prompt_versions(owner_id, card_id) or []
        active = next((item for item in versions if item.is_active), None)
        return CharacterPromptView(
            character_card_id=card.id,
            display_name=card.display_name,
            target_id=target.id,
            provider=config.provider,
            base_url=config.base_url,
            model=config.model,
            temperature=config.temperature,
            system_prompt=config.system_prompt,
            messages=[PromptMessageView(content=config.system_prompt)],
            prompt_version_id=active.id if active is not None else None,
            prompt_version=active.version if active is not None else None,
            prompt_version_label=active.label if active is not None else None,
            config_hash=active.config_hash if active is not None else None,
        )


def render_prompt_export(
    prompt: CharacterPromptView,
    export_format: PromptExportFormat,
) -> tuple[str, str, str]:
    """Return body, media type, and extension for a secret-free Prompt export."""

    if export_format == "text":
        return prompt.system_prompt.rstrip() + "\n", "text/plain; charset=utf-8", "txt"
    if export_format == "markdown":
        body = "\n".join(
            (
                f"# {prompt.display_name} — Runtime System Prompt",
                "",
                f"- Provider: `{prompt.provider}`",
                f"- Model: `{prompt.model}`",
                f"- Temperature: `{prompt.temperature}`",
                f"- Target ID: `{prompt.target_id}`",
                f"- Prompt version: `{prompt.prompt_version or 'unversioned'}`",
                f"- Config hash: `{prompt.config_hash or 'unavailable'}`",
                "",
                "## Exact System Message",
                "",
                "````text",
                prompt.system_prompt.rstrip(),
                "````",
                "",
            )
        )
        return body, "text/markdown; charset=utf-8", "md"
    if export_format == "openai":
        body = json.dumps(
            {
                "model": prompt.model,
                "temperature": prompt.temperature,
                "messages": [item.model_dump(mode="json") for item in prompt.messages],
            },
            ensure_ascii=False,
            indent=2,
        )
        return body + "\n", "application/json; charset=utf-8", "openai.json"
    body = prompt.model_dump_json(indent=2)
    return body + "\n", "application/json; charset=utf-8", "json"


def prompt_export_filename(
    prompt: CharacterPromptView,
    extension: str,
) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", prompt.display_name.casefold()).strip("-")
    safe_slug = slug or "character"
    return f"{safe_slug}-runtime-prompt.{extension}"


__all__ = [
    "CharacterPromptInspector",
    "CharacterPromptView",
    "PromptExportFormat",
    "PromptMessageView",
    "PromptUnavailable",
    "prompt_export_filename",
    "render_prompt_export",
]
