import pytest

from scripts import railway_smoke


def test_normalized_base_url() -> None:
    assert railway_smoke.normalized_base_url(" https://example.up.railway.app/ ") == (
        "https://example.up.railway.app"
    )
    with pytest.raises(ValueError, match="http"):
        railway_smoke.normalized_base_url("example.up.railway.app")


def test_smoke_runs_deterministic_trial(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
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
            return {"id": "run-1"}
        if path == "/api/trials/run-1/snapshot":
            return {
                "run": {
                    "status": "completed",
                    "result": {"average_score": 100},
                }
            }
        raise AssertionError(path)

    def fake_text(_base: str, _path: str) -> tuple[str, str]:
        return "<html>Echo Masque</html>", "text/html"

    monkeypatch.setattr(railway_smoke, "request_json", fake_request_json)
    monkeypatch.setattr(railway_smoke, "request_text", fake_text)

    railway_smoke.run_smoke("https://example.up.railway.app")
