from echo_masque.content_resolver import resolve_static_url


def test_facebook_reel_is_video_source() -> None:
    source = resolve_static_url("https://www.facebook.com/reel/123456789?utm_source=discord")

    assert source.kind == "video"
    assert source.platform == "facebook"
    assert source.source_key == "facebook:123456789"
    assert "utm_source" not in source.canonical_url


def test_instagram_reel_is_video_source() -> None:
    source = resolve_static_url("https://www.instagram.com/reel/ABCdef123/")

    assert source.kind == "video"
    assert source.platform == "instagram"
    assert source.source_key == "instagram:ABCdef123"


def test_vimeo_video_gets_canonical_id() -> None:
    source = resolve_static_url("https://vimeo.com/123456789")

    assert source.kind == "video"
    assert source.platform == "vimeo"
    assert source.source_key == "vimeo:123456789"
