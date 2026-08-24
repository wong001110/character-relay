from echo_masque.media_dependency import resolve_media_dependency


def test_reference_this_image_requires_source_perception() -> None:
    decision = resolve_media_dependency(text="参考这张试试", has_media=True)

    assert decision.dependency == "required"
    assert decision.locked is True


def test_reference_these_images_requires_source_perception() -> None:
    decision = resolve_media_dependency(text="这几张拿来参考一下", has_media=True)

    assert decision.dependency == "required"


def test_do_not_reference_media_stays_none() -> None:
    decision = resolve_media_dependency(text="不用参考这张", has_media=True)

    assert decision.dependency == "none"
    assert decision.locked is True
