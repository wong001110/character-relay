from io import BytesIO

import pytest
from PIL import Image

from echo_masque.api.routes.character_portraits import (
    _normalize_portrait,
    _placeholder_portrait,
)


def image_bytes(*, size: tuple[int, int] = (1800, 900)) -> bytes:
    image = Image.new("RGB", size, (221, 205, 244))
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def test_character_portrait_is_normalized_to_bounded_webp() -> None:
    normalized = _normalize_portrait(image_bytes())

    with Image.open(BytesIO(normalized)) as result:
        assert result.format == "WEBP"
        assert max(result.size) <= 1024


def test_character_portrait_rejects_non_image_bytes() -> None:
    with pytest.raises(ValueError, match="supported image"):
        _normalize_portrait(b"not-an-image")


def test_placeholder_portrait_is_a_valid_webp_for_each_palette() -> None:
    for variant in ("lavender", "rose", "mint", "night"):
        with Image.open(BytesIO(_placeholder_portrait(variant))) as result:
            assert result.format == "WEBP"
            assert result.size == (512, 512)
