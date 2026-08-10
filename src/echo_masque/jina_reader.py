"""Jina Reader integration for clean article extraction and factual summaries."""

from __future__ import annotations

import json
import re
from typing import Any

import httpx
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from echo_masque.network_safety import PublicUrlGuard, PublicUrlRejected

_JINA_READER_BASE = "https://r.jina.ai/"
_MAX_READER_CHARS = 16_000
_STRUCTURED_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "summary": {
            "type": "string",
            "description": "A concise 2-4 sentence factual summary of the main article.",
        },
        "content": {
            "type": "string",
            "description": (
                "The cleaned main article content with navigation, ads, cookie banners, and "
                "unrelated recommendations omitted. Preserve useful details."
            ),
        },
        "published_time": {"type": "string"},
    },
    "required": ["summary", "content"],
    "additionalProperties": False,
}
_READER_INSTRUCTION = (
    "Extract only the main article. Keep claims faithful to the source and do not infer facts "
    "that are not present. Produce a concise factual summary and retain enough cleaned article "
    "content for a downstream assistant to answer follow-up questions."
)


class JinaArticle(BaseModel):
    """Normalized article payload used by Character Relay."""

    model_config = ConfigDict(frozen=True)

    final_url: str = Field(default="", max_length=4096)
    title: str = Field(default="", max_length=500)
    summary: str = Field(min_length=1, max_length=4000)
    content: str = Field(min_length=1, max_length=_MAX_READER_CHARS)
    published_time: str = Field(default="", max_length=120)
    structured: bool = False


class JinaReaderUnavailable(RuntimeError):
    """Raised when Reader cannot provide useful public article content."""


class JinaReaderClient:
    """Read public pages through Jina Reader, with structured ReaderLM-v2 preferred."""

    def __init__(
        self,
        *,
        api_key: SecretStr | None = None,
        url_guard: PublicUrlGuard | None = None,
        http_transport: httpx.AsyncBaseTransport | None = None,
        timeout_seconds: float = 25.0,
    ) -> None:
        self.api_key = api_key
        self.url_guard = url_guard or PublicUrlGuard()
        self.http_transport = http_transport
        self.timeout_seconds = max(5.0, min(timeout_seconds, 60.0))

    async def read(self, url: str) -> JinaArticle:
        try:
            validated = await self.url_guard.validate(url.strip())
        except PublicUrlRejected as exc:
            raise JinaReaderUnavailable(str(exc)) from exc

        structured = await self._request(validated, structured=True)
        if structured is not None:
            return structured

        fallback = await self._request(validated, structured=False)
        if fallback is not None:
            return fallback
        raise JinaReaderUnavailable("Jina Reader did not return useful article content.")

    async def _request(self, target_url: str, *, structured: bool) -> JinaArticle | None:
        headers = {
            "Accept": "application/json",
            "X-Return-Format": "markdown",
            "X-Timeout": "20",
            "User-Agent": "CharacterRelay/0.4 ArticleReader",
        }
        if self.api_key is not None:
            value = self.api_key.get_secret_value().strip()
            if value:
                headers["Authorization"] = f"Bearer {value}"
        if structured:
            headers.update(
                {
                    "X-Respond-With": "readerlm-v2",
                    "X-Instruction": _READER_INSTRUCTION,
                    "X-JSON-Schema": json.dumps(_STRUCTURED_SCHEMA, separators=(",", ":")),
                }
            )

        endpoint = f"{_JINA_READER_BASE}{target_url}"
        try:
            async with httpx.AsyncClient(
                timeout=httpx.Timeout(self.timeout_seconds),
                transport=self.http_transport,
                follow_redirects=True,
            ) as client:
                response = await client.get(endpoint, headers=headers)
        except httpx.HTTPError:
            return None
        if response.is_error:
            return None

        try:
            body: Any = response.json()
        except ValueError:
            body = response.text
        return self._normalize(body, target_url=target_url, structured=structured)

    @classmethod
    def _normalize(
        cls,
        body: Any,
        *,
        target_url: str,
        structured: bool,
    ) -> JinaArticle | None:
        data: Any = body.get("data", body) if isinstance(body, dict) else body
        envelope_title = ""
        envelope_url = target_url
        envelope_published = ""
        if isinstance(data, dict):
            envelope_title = cls._string(data.get("title"), 500)
            envelope_url = cls._string(data.get("url"), 4096) or target_url
            envelope_published = cls._string(
                data.get("publishedTime") or data.get("published_time"),
                120,
            )
            content_value = data.get("content")
        else:
            content_value = data

        if structured:
            candidate = cls._structured_candidate(content_value)
            if candidate is None and isinstance(data, dict):
                candidate = data
            if isinstance(candidate, dict):
                content = cls._string(candidate.get("content"), _MAX_READER_CHARS)
                summary = cls._string(candidate.get("summary"), 4000)
                title = cls._string(candidate.get("title"), 500) or envelope_title
                published = (
                    cls._string(candidate.get("published_time"), 120) or envelope_published
                )
                if content and summary:
                    return JinaArticle(
                        final_url=envelope_url,
                        title=title,
                        summary=summary,
                        content=content,
                        published_time=published,
                        structured=True,
                    )

        raw = cls._string(content_value, _MAX_READER_CHARS)
        if not raw and isinstance(data, str):
            raw = data[:_MAX_READER_CHARS]
        if not raw:
            return None
        title, content = cls._split_reader_markdown(raw, envelope_title)
        if not content:
            return None
        return JinaArticle(
            final_url=envelope_url,
            title=title,
            summary=cls._lead_summary(content, title),
            content=content[:_MAX_READER_CHARS],
            published_time=envelope_published,
            structured=False,
        )

    @staticmethod
    def _structured_candidate(value: Any) -> dict[str, Any] | None:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return None
        text = value.strip()
        if text.startswith("```"):
            text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
            text = re.sub(r"\s*```$", "", text)
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            return None
        return decoded if isinstance(decoded, dict) else None

    @classmethod
    def _split_reader_markdown(cls, value: str, fallback_title: str) -> tuple[str, str]:
        title = fallback_title
        content = value.strip()
        title_match = re.search(r"(?mi)^Title:\s*(.+)$", content)
        if title_match and not title:
            title = title_match.group(1).strip()[:500]
        marker = re.search(r"(?mi)^Markdown Content:\s*$", content)
        if marker:
            content = content[marker.end() :].strip()
        return title, content

    @staticmethod
    def _lead_summary(content: str, title: str) -> str:
        cleaned = re.sub(r"\s+", " ", content).strip()
        if not cleaned:
            return title or "Public article"
        excerpt = cleaned[:900]
        sentence_end = max(
            excerpt.rfind("\u3002"),
            excerpt.rfind("\uff01"),
            excerpt.rfind("\uff1f"),
            excerpt.rfind(". "),
        )
        if sentence_end >= 180:
            excerpt = excerpt[: sentence_end + 1]
        if title and not excerpt.casefold().startswith(title.casefold()):
            return f"{title}: {excerpt}"[:4000]
        return excerpt[:4000]

    @staticmethod
    def _string(value: Any, limit: int) -> str:
        if not isinstance(value, str):
            return ""
        return value.strip()[:limit]
