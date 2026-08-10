from echo_masque.content_resolver import canonicalize_public_url, resolve_static_url


def test_canonicalize_public_url_strips_fragment_and_tracking_parameters() -> None:
    canonical = canonicalize_public_url(
        "HTTPS://Example.COM/news?id=7&utm_source=discord&fbclid=abc#comments"
    )
    assert canonical == "https://example.com/news?id=7"


def test_youtube_links_share_one_canonical_source_key() -> None:
    watch = resolve_static_url("https://www.youtube.com/watch?v=abc123&utm_source=chat")
    short = resolve_static_url("https://youtu.be/abc123?t=30")

    assert watch.source_key == "youtube:abc123"
    assert short.source_key == "youtube:abc123"
    assert watch.kind == "video"
    assert watch.media_type == "video"


def test_bilibili_and_x_get_platform_source_keys() -> None:
    bilibili = resolve_static_url("https://www.bilibili.com/video/BV1abcXYZ")
    post = resolve_static_url("https://x.com/example/status/123456789")

    assert bilibili.source_key == "bilibili:BV1abcXYZ"
    assert bilibili.kind == "video"
    assert post.source_key == "x:123456789"
    assert post.kind == "social_post"


def test_short_link_requires_network_resolution_later() -> None:
    source = resolve_static_url("https://b23.tv/example")

    assert source.platform == "bilibili"
    assert source.status == "partial"
    assert source.kind == "unknown"


def test_direct_media_and_generic_article_are_classified_without_fetching() -> None:
    image = resolve_static_url("https://cdn.example.com/assets/cat.webp?token=public")
    article = resolve_static_url("https://example.com/news/story")

    assert image.kind == "image"
    assert image.media_type == "image"
    assert article.kind == "article"
    assert article.source_key.startswith("url:https://example.com/news/story")
