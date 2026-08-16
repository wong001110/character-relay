"""Planner-only lightweight media understanding.

This layer gives Topic/Admission enough objective information to route a media-bearing turn
without granting that knowledge to any Character. Full content remains Character-visible only
through REQUIRED Runtime resolution or an explicit ``media.inspect`` Tool call.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from pydantic import BaseModel, ConfigDict, Field

from echo_masque.api.connector_schemas import DiscordInboundMessage
from echo_masque.content_resolver import ResolvedContentSource, resolve_static_url
from echo_masque.live_media import DiscordAttachment, LiveMediaContext
from echo_masque.live_media_enhanced import EnhancedLiveMediaContextService
from echo_masque.media_dependency import resolve_media_dependency
from echo_masque.media_runtime import MediaUnderstandingProvider, MediaUnderstandingService

PlannerMediaKind = Literal["image", "video", "article", "link", "file"]
PlannerMediaState = Literal["resolved", "preview_only", "unresolved"]


class PlannerMediaDescriptor(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    ref: str = Field(min_length=1, max_length=220)
    kind: PlannerMediaKind
    state: PlannerMediaState
    label: str = Field(default="", max_length=300)
    subject: str = Field(default="", max_length=500)
    summary: str = Field(default="", max_length=1200)
    source_key: str = Field(default="", max_length=500)
    source_url: str = Field(default="", max_length=3000)
    topic_evidence: bool = False

    def planning_line(self) -> str:
        if not self.topic_evidence or self.state != "resolved":
            return ""
        body = self.subject or self.summary or self.label
        if not body:
            return ""
        extra = self.summary if self.summary and self.summary != body else ""
        value = f"[{self.kind}] {body}"
        if extra:
            value += f" — {extra}"
        return value[:1400]


class PlannerMediaResult(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    descriptors: tuple[PlannerMediaDescriptor, ...] = ()
    dependency: Literal["required", "optional", "none"] = "none"
    dependency_reason: str = ""
    dependency_locked: bool = False
    planning_text: str = Field(default="", max_length=3000)


@dataclass(slots=True)
class PlannerMediaDescriptorService:
    """Resolve compact objective descriptors with shared cache/provenance infrastructure."""

    media: EnhancedLiveMediaContextService
    utility_provider: MediaUnderstandingProvider | None = None

    def __post_init__(self) -> None:
        self._utility = (
            MediaUnderstandingService(self.media.media_repository, self.utility_provider)
            if self.utility_provider is not None
            else None
        )

    @staticmethod
    def _from_context(
        *,
        ref: str,
        context: LiveMediaContext,
        source_url: str = "",
    ) -> PlannerMediaDescriptor:
        subject = context.label.strip() or context.summary.strip()
        summary = " ".join(context.summary.split())[:1200]
        return PlannerMediaDescriptor(
            ref=ref,
            kind=context.kind,
            state="resolved",
            label=context.label,
            subject=subject[:500],
            summary=summary,
            source_key=context.source_key,
            source_url=source_url,
            topic_evidence=bool(subject or summary),
        )

    @staticmethod
    def _preview_for_url(
        payload: DiscordInboundMessage,
        url: str,
        index: int,
    ) -> PlannerMediaDescriptor:
        matching = next(
            (
                item
                for item in payload.embeds
                if item.url.strip() == url.strip() or (item.title or item.description)
            ),
            None,
        )
        title = matching.title.strip() if matching is not None else ""
        description = matching.description.strip() if matching is not None else ""
        provider = matching.provider_name.strip() if matching is not None else ""
        return PlannerMediaDescriptor(
            ref=f"url:{index}",
            kind="link",
            state="preview_only" if title or description or provider else "unresolved",
            label=provider,
            subject=title[:500],
            summary=" ".join(description.split())[:1200],
            source_url=url,
            topic_evidence=False,
        )

    async def _utility_attachment_context(
        self,
        *,
        attachment: DiscordAttachment,
        media_type: Literal["image", "video"],
    ) -> LiveMediaContext | None:
        if self._utility is None:
            return None
        try:
            resolved = await self.media._resolve_attachment(attachment, media_type)
            analysis, _ = await self._utility.analyze(resolved.asset)
            return self.media._analysis_context(
                resolved.source_key,
                media_type,
                attachment.filename,
                analysis,
            )
        except Exception:
            return None

    async def _utility_public_context(
        self,
        *,
        source: ResolvedContentSource,
        media_type: Literal["image", "video"],
    ) -> LiveMediaContext | None:
        if self._utility is None:
            return None
        try:
            resolved = await self.media._resolve_public_media(source)
            analysis, _ = await self._utility.analyze(resolved.asset)
            return self.media._analysis_context(
                resolved.source_key,
                media_type,
                source.platform,
                analysis,
            )
        except Exception:
            return None

    async def resolve(self, payload: DiscordInboundMessage) -> PlannerMediaResult:
        attachments = await self.media._discord_attachments(payload)
        urls = self.media._extract_urls(payload.text)
        burst_ids = [item for item in payload.burst_media_message_ids[:2] if item.strip()]
        has_media = bool(attachments or urls or payload.embeds or burst_ids)
        dependency = resolve_media_dependency(text=payload.text, has_media=has_media)
        descriptors: list[PlannerMediaDescriptor] = []
        needs_objective_subject = not payload.text.strip() or dependency.dependency == "required"

        for index, attachment in enumerate(attachments[:2], start=1):
            media_type = self.media._media_type(attachment.content_type, attachment.filename)
            if media_type in {"image", "video"} and needs_objective_subject:
                context = await self._utility_attachment_context(
                    attachment=attachment,
                    media_type=cast(Literal["image", "video"], media_type),
                )
                if context is not None:
                    descriptors.append(
                        self._from_context(ref=f"attachment:{index}", context=context)
                    )
                    continue
            kind: PlannerMediaKind = cast(
                PlannerMediaKind,
                media_type if media_type in {"image", "video"} else "file",
            )
            label = attachment.filename.strip()
            descriptors.append(
                PlannerMediaDescriptor(
                    ref=f"attachment:{index}",
                    kind=kind,
                    state="preview_only",
                    label=label,
                    subject=label,
                    source_key=attachment.source_key,
                    source_url=attachment.url,
                    topic_evidence=False,
                )
            )

        for source_message_id in burst_ids:
            source_payload = payload.model_copy(
                update={
                    "message_id": source_message_id,
                    "text": "",
                    "attachments": [],
                    "embeds": [],
                    "burst_media_message_ids": [],
                }
            )
            source_attachments = await self.media._discord_attachments(source_payload)
            for attachment in source_attachments[:1]:
                media_type = self.media._media_type(attachment.content_type, attachment.filename)
                if media_type not in {"image", "video"}:
                    continue
                context = await self._utility_attachment_context(
                    attachment=attachment,
                    media_type=cast(Literal["image", "video"], media_type),
                )
                if context is not None:
                    descriptors.append(
                        self._from_context(
                            ref=f"burst:{source_message_id}",
                            context=context,
                        )
                    )

        for index, raw_url in enumerate(urls[:3], start=1):
            preview = self._preview_for_url(payload, raw_url, index)
            try:
                source = resolve_static_url(raw_url)
            except ValueError:
                descriptors.append(preview)
                continue
            context: LiveMediaContext | None = None
            try:
                context = await self.media._article_context(source)
            except Exception:
                context = None
            if (
                context is None
                and needs_objective_subject
                and source.kind in {"image", "video"}
            ):
                context = await self._utility_public_context(
                    source=source,
                    media_type=cast(Literal["image", "video"], source.kind),
                )
            if context is not None:
                descriptors.append(
                    self._from_context(
                        ref=f"url:{index}",
                        context=context,
                        source_url=source.canonical_url,
                    )
                )
                continue
            descriptors.append(
                preview.model_copy(
                    update={
                        "kind": (
                            source.kind
                            if source.kind in {"image", "video", "article"}
                            else "link"
                        ),
                        "source_key": source.source_key,
                        "source_url": source.canonical_url,
                    }
                )
            )

        lines = [item.planning_line() for item in descriptors]
        planning_text = "\n".join(item for item in lines if item)[:3000]
        return PlannerMediaResult(
            descriptors=tuple(descriptors[:6]),
            dependency=dependency.dependency,
            dependency_reason=dependency.reason,
            dependency_locked=dependency.locked,
            planning_text=planning_text,
        )


__all__ = [
    "PlannerMediaDescriptor",
    "PlannerMediaDescriptorService",
    "PlannerMediaResult",
]
