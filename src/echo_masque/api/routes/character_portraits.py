"""Character Card portrait upload and public delivery.

Portraits are deliberately stored outside the Character Card row so existing SQLite
installations do not need a destructive schema migration. Production uses the same
Railway /data volume that already protects the SQLite database; development uses a
local cache directory.
"""

from __future__ import annotations

import base64
import binascii
from functools import lru_cache
from io import BytesIO
from pathlib import Path
from time import time_ns
from typing import cast

from fastapi import APIRouter, HTTPException, Request, Response, status
from PIL import Image, ImageDraw, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field

from echo_masque.api.dependencies import CurrentUserDependency
from echo_masque.config import Settings
from echo_masque.persistence import Repository

router = APIRouter()

_MAX_UPLOAD_BYTES = 8 * 1024 * 1024
_MAX_OUTPUT_BYTES = 3 * 1024 * 1024
_MAX_PIXELS = 20_000_000
_MAX_EDGE = 1024
_PLACEHOLDER_PALETTES = {
    "lavender": ((237, 229, 255), (128, 106, 166)),
    "rose": ((252, 229, 236), (168, 101, 126)),
    "mint": ((225, 243, 233), (91, 139, 114)),
    "night": ((229, 228, 241), (82, 78, 112)),
}


class CharacterPortraitUpload(BaseModel):
    mime_type: str = Field(min_length=5, max_length=100, pattern=r"^image/")
    content_base64: str = Field(min_length=4, max_length=12_000_000)


class CharacterPortraitView(BaseModel):
    url: str


def _repository(request: Request) -> Repository:
    return cast(Repository, request.app.state.repository)


def _portrait_root(request: Request) -> Path:
    settings = cast(Settings, request.app.state.settings)
    root = (
        Path("/data/character-portraits")
        if settings.environment == "production"
        else Path(".cache/character-relay/portraits")
    )
    root.mkdir(parents=True, exist_ok=True)
    return root


def _portrait_path(request: Request, card_id: str) -> Path:
    return _portrait_root(request) / f"{card_id}.webp"


def _normalize_portrait(raw: bytes) -> bytes:
    if not raw or len(raw) > _MAX_UPLOAD_BYTES:
        raise ValueError("Character portrait must be between 1 byte and 8 MB.")
    try:
        with Image.open(BytesIO(raw)) as source:
            image = ImageOps.exif_transpose(source)
            if image.width <= 0 or image.height <= 0 or image.width * image.height > _MAX_PIXELS:
                raise ValueError("Character portrait dimensions are too large.")
            image.thumbnail((_MAX_EDGE, _MAX_EDGE), Image.Resampling.LANCZOS)
            if image.mode not in {"RGB", "RGBA"}:
                image = image.convert("RGBA" if "transparency" in image.info else "RGB")
            output = BytesIO()
            image.save(output, format="WEBP", quality=88, method=6)
            data = output.getvalue()
            if len(data) > _MAX_OUTPUT_BYTES:
                output = BytesIO()
                image.save(output, format="WEBP", quality=76, method=6)
                data = output.getvalue()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise ValueError("Uploaded portrait is not a supported image.") from exc
    if not data or len(data) > _MAX_OUTPUT_BYTES:
        raise ValueError("Character portrait is still too large after processing.")
    return data


@lru_cache(maxsize=4)
def _placeholder_portrait(variant: str) -> bytes:
    background, ink = _PLACEHOLDER_PALETTES.get(
        variant,
        _PLACEHOLDER_PALETTES["lavender"],
    )
    image = Image.new("RGB", (512, 512), background)
    draw = ImageDraw.Draw(image)
    # A quiet character-file silhouette rather than an application icon. It keeps the public
    # Discord fallback URL valid even before the creator uploads custom artwork.
    draw.ellipse((156, 86, 356, 286), fill=(255, 252, 246), outline=ink, width=10)
    draw.polygon(((178, 116), (217, 54), (244, 128)), fill=(255, 252, 246), outline=ink)
    draw.polygon(((268, 128), (298, 54), (338, 118)), fill=(255, 252, 246), outline=ink)
    draw.ellipse((211, 181, 230, 200), fill=ink)
    draw.ellipse((282, 181, 301, 200), fill=ink)
    draw.arc((238, 196, 276, 236), start=12, end=168, fill=ink, width=6)
    draw.rounded_rectangle((117, 300, 395, 480), radius=88, fill=(255, 252, 246), outline=ink, width=10)
    output = BytesIO()
    image.save(output, format="WEBP", quality=86, method=6)
    return output.getvalue()


@router.get("/portraits/{card_id}")
def get_character_portrait(card_id: str, request: Request) -> Response:
    # The image URL is intentionally public because Discord must be able to fetch it as a
    # webhook avatar. Card IDs are opaque UUIDs and deleted cards are never served.
    card = _repository(request).get_character_card(card_id)
    if card is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    path = _portrait_path(request, card_id)
    content = path.read_bytes() if path.is_file() else _placeholder_portrait(card.portrait_variant)
    return Response(
        content=content,
        media_type="image/webp",
        headers={"Cache-Control": "public, max-age=30, must-revalidate"},
    )


@router.put("/{card_id}/portrait", response_model=CharacterPortraitView)
def put_character_portrait(
    card_id: str,
    payload: CharacterPortraitUpload,
    request: Request,
    user: CurrentUserDependency,
) -> CharacterPortraitView:
    if _repository(request).get_character_card(card_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    try:
        raw = base64.b64decode(payload.content_base64, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise HTTPException(status_code=422, detail="Portrait payload is not valid base64.") from exc
    try:
        processed = _normalize_portrait(raw)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    path = _portrait_path(request, card_id)
    temporary = path.with_suffix(".tmp")
    temporary.write_bytes(processed)
    temporary.replace(path)
    version = time_ns()
    return CharacterPortraitView(url=f"/api/characters/portraits/{card_id}?v={version}")


@router.delete("/{card_id}/portrait", status_code=status.HTTP_204_NO_CONTENT)
def delete_character_portrait(
    card_id: str,
    request: Request,
    user: CurrentUserDependency,
) -> None:
    if _repository(request).get_character_card(card_id, user.id) is None:
        raise HTTPException(status_code=404, detail="Character Card not found.")
    _portrait_path(request, card_id).unlink(missing_ok=True)
