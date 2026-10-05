"""Synthetic HTTPS transport tests for the independent memory-only client."""

import io
import json
from dataclasses import dataclass, field
from urllib.parse import parse_qs

import httpx
import pytest

from echo_masque import cli_client

DEVICE_CODE = "synthetic-private-device-credential-12345678"
ACCESS_TOKEN = "crcli_synthetic-private-access-credential-12345678"
SECRET_MESSAGE = "synthetic-private-message-not-for-console"


@dataclass
class Clock:
    now: float = 0
    waits: list[float] = field(default_factory=list)

    def monotonic(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.waits.append(seconds)
        self.now += seconds


def device_response(**changes: object) -> dict[str, object]:
    return {
        "device_code": DEVICE_CODE,
        "user_code": "ABCDE-FGHJK",
        "verification_uri": cli_client.VERIFICATION_URI,
        "expires_in": 600,
        "interval": 5,
        **changes,
    }


def token_response(**changes: object) -> dict[str, object]:
    return {
        "access_token": ACCESS_TOKEN,
        "token_type": "Bearer",
        "expires_in": 900,
        "refresh_token": "must-not-be-used-or-printed",
        **changes,
    }


def handler_for(
    requests: list[httpx.Request],
    *,
    authorization: dict[str, object] | None = None,
    exchanges: list[httpx.Response | Exception] | None = None,
    metadata: dict[str, object] | None = None,
    snapshot: dict[str, object] | None = None,
) -> httpx.MockTransport:
    exchanges = exchanges if exchanges is not None else [httpx.Response(200, json=token_response())]

    def handle(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        path = request.url.path
        assert request.url.scheme == "https"
        assert request.url.host == "echo-masque-production.up.railway.app"
        assert "cookie" not in request.headers
        if path == "/api/cli-auth/device-authorizations":
            assert "authorization" not in request.headers
            payload = json.loads(request.content)
            assert payload == {
                "client_id": cli_client.CLIENT_ID,
                "scopes": list(cli_client.SCOPES),
                "room_ids": ["room-one"],
            }
            return httpx.Response(
                200,
                json=authorization if authorization is not None else device_response(),
                headers={"Set-Cookie": "unwanted=synthetic-server-cookie; Path=/; Secure"},
            )
        if path == "/api/cli-auth/token":
            assert "authorization" not in request.headers
            assert parse_qs(request.content.decode()) == {
                "client_id": [cli_client.CLIENT_ID],
                "device_code": [DEVICE_CODE],
                "grant_type": [cli_client.DEVICE_GRANT_TYPE],
            }
            response = exchanges.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        # Do not include credentials in assertion failures/test reports.
        assert request.headers.get("authorization", "").startswith("Bearer crcli_")
        if path == "/api/cli-auth/me":
            return httpx.Response(
                200,
                json={
                    "user_id": "synthetic-user",
                    "display_name": "Synthetic User",
                    "grant_id": "synthetic-grant",
                    "client_id": cli_client.CLIENT_ID,
                    "expires_at": "2026-10-05T10:15:00Z",
                    "access_token": ACCESS_TOKEN,
                },
            )
        if path == "/api/cli/rooms":
            return httpx.Response(
                200,
                json=metadata
                if metadata is not None
                else {
                    "rooms": [{"id": "room-one", "name": "Synthetic room"}],
                },
            )
        if path == "/api/cli/rooms/room-one/messages":
            return httpx.Response(
                200,
                json=snapshot
                if snapshot is not None
                else {
                    "room_id": "room-one",
                    "history_limit": 64,
                    "messages": [{"id": "message-one", "text": SECRET_MESSAGE}],
                    "outbox": [{"access_token": ACCESS_TOKEN}],
                },
            )
        if path == "/api/cli-auth/revoke":
            return httpx.Response(204)
        raise AssertionError("Unexpected client route")

    return httpx.MockTransport(handle)


def run_mock(transport: httpx.MockTransport, **kwargs: object) -> tuple[Clock, str]:
    clock = Clock()
    output = io.StringIO()
    with httpx.Client(
        transport=transport,
        follow_redirects=True,
        auth=("do-not-inherit", "synthetic-basic-password"),
        headers={"Authorization": "Bearer inherited-do-not-send", "Cookie": "stale=unwanted"},
    ) as client:
        cli_client.run_session(
            client,
            ["room-one", "room-one"],
            output=output,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
            **kwargs,
        )
        assert not client.cookies
    return clock, output.getvalue()


def assert_no_secrets(output: str) -> None:
    # Boolean comparison keeps synthetic credentials out of pytest diagnostics.
    assert all(
        value not in output
        for value in (
            DEVICE_CODE,
            ACCESS_TOKEN,
            SECRET_MESSAGE,
            "must-not-be-used-or-printed",
            "synthetic-server-cookie",
            "inherited-do-not-send",
        )
    )


def test_session_uses_one_official_https_process_and_revoke_without_secret_output() -> None:
    requests: list[httpx.Request] = []
    clock, output = run_mock(handler_for(requests), revoke=True)
    assert clock.waits == [5]
    assert [request.url.path for request in requests] == [
        "/api/cli-auth/device-authorizations",
        "/api/cli-auth/token",
        "/api/cli-auth/me",
        "/api/cli/rooms",
        "/api/cli/rooms/room-one/messages",
        "/api/cli-auth/revoke",
    ]
    assert cli_client.VERIFICATION_URI in output
    assert "ABCDE-FGHJK" in output
    assert '"message_count": 1' in output
    assert "was revoked" in output
    assert_no_secrets(output)


def test_pending_slow_down_and_timeout_respect_polling_intervals() -> None:
    requests: list[httpx.Request] = []
    exchanges = [
        httpx.Response(400, json={"error": "authorization_pending"}),
        httpx.Response(400, json={"error": "slow_down"}),
        httpx.ReadTimeout("private details must not be displayed"),
        httpx.Response(200, json=token_response()),
    ]
    clock, output = run_mock(handler_for(requests, exchanges=exchanges))
    assert clock.waits == [5, 5, 10, 20]
    assert "credentials were discarded" in output
    assert_no_secrets(output)


@pytest.mark.parametrize("error", ["access_denied", "expired_token", "invalid_grant"])
def test_failed_exchange_stops_before_private_read(error: str) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(cli_client.ClientError) as failure:
        run_mock(
            handler_for(
                requests,
                exchanges=[
                    httpx.Response(
                        400,
                        json={
                            "error": error,
                            "error_description": ACCESS_TOKEN,
                            "device_code": DEVICE_CODE,
                        },
                    )
                ],
            )
        )
    assert len(requests) == 2
    assert_no_secrets(str(failure.value))


@pytest.mark.parametrize(
    "uri",
    [
        "http://echo-masque-production.up.railway.app/cli/authorize",
        "https://evil.example/cli/authorize",
        f"{cli_client.VERIFICATION_URI}?device_code=private",
        "https://echo-masque-production.up.railway.app@evil.example/cli/authorize",
    ],
)
def test_off_origin_or_secret_bearing_approval_url_is_never_displayed(uri: str) -> None:
    requests: list[httpx.Request] = []
    output = io.StringIO()
    with (
        httpx.Client(
            transport=handler_for(
                requests,
                authorization=device_response(
                    verification_uri=uri,
                ),
            )
        ) as client,
        pytest.raises(cli_client.ClientError),
    ):
        cli_client.run_session(client, ["room-one"], output=output)
    assert output.getvalue() == ""
    assert len(requests) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"user_code": "ABCD\nSECRET"},
        {"expires_in": 601},
        {"expires_in": True},
        {"interval": 0},
        {"device_code": "short"},
    ],
)
def test_bad_device_responses_do_not_poll(changes: dict[str, object]) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(cli_client.ClientError):
        run_mock(handler_for(requests, authorization=device_response(**changes)))
    assert len(requests) == 1


def test_poll_deadline_is_finite_and_does_not_request_after_expiry() -> None:
    requests: list[httpx.Request] = []
    clock = Clock()
    output = io.StringIO()
    with (
        httpx.Client(
            transport=handler_for(
                requests,
                authorization=device_response(expires_in=6),
                exchanges=[httpx.Response(400, json={"error": "authorization_pending"})],
            )
        ) as client,
        pytest.raises(cli_client.ClientError, match="expired"),
    ):
        cli_client.run_session(
            client,
            ["room-one"],
            output=output,
            monotonic=clock.monotonic,
            sleep=clock.sleep,
        )
    assert clock.waits == [5, 1]
    assert len(requests) == 2
    assert_no_secrets(output.getvalue())


@pytest.mark.parametrize("redirect_path", ["device-authorizations", "token", "me"])
def test_redirects_never_forward_authorization(redirect_path: str) -> None:
    requests: list[httpx.Request] = []
    base = handler_for(requests)

    def redirect(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(f"/{redirect_path}"):
            requests.append(request)
            return httpx.Response(307, headers={"Location": "https://evil.example/private"})
        return base.handle_request(request)

    with pytest.raises(cli_client.ClientError, match="redirected"):
        run_mock(httpx.MockTransport(redirect))
    assert all(request.url.host == "echo-masque-production.up.railway.app" for request in requests)


@pytest.mark.parametrize("rooms", [[], ["*"], ["../other"], ["room/other"], [""], ["r"] * 33])
def test_explicit_bounded_room_selection_precedes_network(rooms: list[str]) -> None:
    requests: list[httpx.Request] = []
    # Distinct entries trigger the limit; duplicate requests are deliberately deduplicated.
    if len(rooms) == 33:
        rooms = [f"room-{index}" for index in range(33)]
    with (
        httpx.Client(transport=handler_for(requests)) as client,
        pytest.raises(cli_client.ClientError),
    ):
        cli_client.run_session(client, rooms)
    assert not requests


def test_unexpected_room_scope_stops_before_messages() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(cli_client.ClientError, match="room scope"):
        run_mock(
            handler_for(
                requests,
                metadata={
                    "rooms": [
                        {"id": "room-one"},
                        {"id": "unapproved-room"},
                    ]
                },
            )
        )
    assert not any(request.url.path.endswith("/messages") for request in requests)


def test_more_than_64_messages_rejected() -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(cli_client.ClientError, match="bounded"):
        run_mock(
            handler_for(
                requests,
                snapshot={
                    "room_id": "room-one",
                    "messages": [{}] * 65,
                },
            )
        )


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(200, content=b"not-json"),
        httpx.Response(200, json=["unexpected-list"]),
        httpx.Response(200, content=b"x" * (cli_client.MAX_RESPONSE_BYTES + 1)),
    ],
)
def test_unreadable_or_excessive_responses_fail_without_echoing_body(
    response: httpx.Response,
) -> None:
    with pytest.raises(cli_client.ClientError) as failure:
        run_mock(httpx.MockTransport(lambda _request: response))
    assert_no_secrets(str(failure.value))


@pytest.mark.parametrize(
    "changes",
    [
        {"token_type": "Password"},
        {"expires_in": 901},
        {"access_token": "bad-prefix"},
    ],
)
def test_invalid_token_response_does_not_reach_identity(changes: dict[str, object]) -> None:
    requests: list[httpx.Request] = []
    with pytest.raises(cli_client.ClientError):
        run_mock(
            handler_for(
                requests,
                exchanges=[
                    httpx.Response(
                        200,
                        json=token_response(**changes),
                    )
                ],
            )
        )
    assert len(requests) == 2


def test_cli_has_no_target_password_token_or_insecure_switch() -> None:
    parser = cli_client.build_parser()
    arguments = parser.parse_args(["--room", "room-one", "--revoke"])
    assert arguments.room == ["room-one"]
    options = {option for action in parser._actions for option in action.option_strings}
    assert options == {"-h", "--help", "--room", "--revoke"}


@pytest.mark.parametrize("option", ["--token", "--device-code"])
def test_invalid_arguments_never_echo_pasted_credentials(option, capsys) -> None:
    with pytest.raises(SystemExit) as result:
        cli_client.main(["--room", "room-one", option, ACCESS_TOKEN, DEVICE_CODE])
    assert result.value.code == 2
    captured = capsys.readouterr()
    assert_no_secrets(captured.out + captured.err)
    assert "Invalid CLI arguments" in captured.err


def test_pasted_cli_token_cannot_become_a_room_request() -> None:
    requests: list[httpx.Request] = []

    def unexpected(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        raise RuntimeError("A pasted credential must be refused before transport")

    with httpx.Client(transport=httpx.MockTransport(unexpected)) as client:
        output = io.StringIO()
        with pytest.raises(cli_client.ClientError):
            cli_client.run_session(client, [ACCESS_TOKEN], output=output)
    assert requests == []
    assert output.getvalue() == ""


def test_main_never_prints_raw_transport_errors(monkeypatch: pytest.MonkeyPatch, capsys) -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"secret debug data: {ACCESS_TOKEN}", request=request)

    client = httpx.Client(transport=httpx.MockTransport(broken))
    monkeypatch.setattr(cli_client.httpx, "Client", lambda **_kwargs: client)
    assert cli_client.main(["--room", "room-one"]) == 1
    captured = capsys.readouterr()
    assert_no_secrets(captured.out + captured.err)
    assert "secure service connection failed" in captured.err


def test_main_explicitly_enables_tls_verification_and_disables_redirects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings: dict[str, object] = {}
    client = httpx.Client(transport=handler_for([]))

    def create_client(**kwargs: object) -> httpx.Client:
        settings.update(kwargs)
        return client

    monkeypatch.setattr(cli_client.httpx, "Client", create_client)
    monkeypatch.setattr(cli_client, "run_session", lambda *_args, **_kwargs: None)
    assert cli_client.main(["--room", "room-one"]) == 0
    assert settings == {"verify": True, "follow_redirects": False, "timeout": 15.0}
