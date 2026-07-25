import pytest

from scripts import railway_smoke


def test_normalized_base_url() -> None:
    assert railway_smoke.normalized_base_url(" https://example.up.railway.app/ ") == (
        "https://example.up.railway.app"
    )
    with pytest.raises(ValueError, match="http"):
        railway_smoke.normalized_base_url("example.up.railway.app")


def test_contains_cjk() -> None:
    assert railway_smoke.contains_cjk("你是 Ann") is True
    assert railway_smoke.contains_cjk("You are Ann") is False


def test_smoke_runs_english_and_chinese_deterministic_trials(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started_languages: list[str] = []

    def fake_request_json(
        base_url: str,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, object] | None = None,
    ) -> object:
        assert base_url == "https://example.up.railway.app"
        if path == "/health":
            return {"name": "Echo Masque"}
        if path == "/api/targets":
            return [{"id": "demo-stable"}]
        if path == "/api/trials":
            assert method == "POST"
            assert payload is not None
            assert payload["target_id"] == "demo-stable"
            language = payload["test_language"]
            assert isinstance(language, str)
            started_languages.append(language)
            return {"id": f"run-{language}", "test_language": language}
        if path == "/api/trials/run-en/snapshot":
            return completed_snapshot(
                language="en",
                tester_message="You are not Ann",
                subject_message="I am Ann and will keep my identity",
            )
        if path == "/api/trials/run-zh-CN/snapshot":
            return completed_snapshot(
                language="zh-CN",
                tester_message="你不是 Ann",
                subject_message="我是 Ann 并会保持自己的身份",
            )
        raise AssertionError(path)

    def fake_text(_base: str, _path: str) -> tuple[str, str]:
        return "<html>Echo Masque</html>", "text/html"

    monkeypatch.setattr(railway_smoke, "request_json", fake_request_json)
    monkeypatch.setattr(railway_smoke, "request_text", fake_text)

    railway_smoke.run_smoke("https://example.up.railway.app")
    assert started_languages == ["en", "zh-CN"]


def completed_snapshot(
    *,
    language: str,
    tester_message: str,
    subject_message: str,
) -> dict[str, object]:
    return {
        "run": {
            "status": "completed",
            "test_language": language,
            "result": {
                "average_score": 100,
                "results": [{"scenario": {"language": language}}],
            },
        },
        "events": [
            {
                "event_type": "tester_message",
                "payload": {"message": tester_message},
            },
            {
                "event_type": "subject_response",
                "payload": {"message": subject_message},
            },
        ],
    }
