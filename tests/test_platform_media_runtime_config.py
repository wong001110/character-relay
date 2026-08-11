from echo_masque import platform_media
from echo_masque.platform_media import YtDlpMediaResolver


def test_ytdlp_options_explicitly_enable_installed_node(monkeypatch) -> None:
    def which(name: str) -> str | None:
        if name == "node":
            return "/usr/local/bin/node"
        return None

    monkeypatch.setattr(platform_media.shutil, "which", which)
    options = YtDlpMediaResolver._yt_dlp_options()

    assert options["js_runtimes"] == {
        "node": {"path": "/usr/local/bin/node"},
    }
    assert options["skip_download"] is True
    assert options["ignore_no_formats_error"] is True


def test_bilibili_412_is_the_only_impersonation_retry_case() -> None:
    assert YtDlpMediaResolver._should_retry_bilibili_with_impersonation(
        "https://www.bilibili.com/video/BV1abc123",
        RuntimeError("HTTP Error 412: Precondition Failed"),
    )
    assert not YtDlpMediaResolver._should_retry_bilibili_with_impersonation(
        "https://www.bilibili.com/video/BV1abc123",
        RuntimeError("HTTP Error 404: Not Found"),
    )
    assert not YtDlpMediaResolver._should_retry_bilibili_with_impersonation(
        "https://www.youtube.com/watch?v=abc",
        RuntimeError("HTTP Error 412: Precondition Failed"),
    )
