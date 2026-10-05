"""A single-process, memory-only public device client for the official Relay service.

There is deliberately no target override, credential file, password login, Cookie
authentication, refresh token or daemon. Tests inject a transport for the same HTTPS
origin; that seam is not exposed through command-line arguments.
"""

import argparse
import json
import re
import sys
import time
from collections.abc import Callable, Sequence
from contextlib import closing
from typing import Any, Never, TextIO

import httpx

OFFICIAL_ORIGIN = "https://echo-masque-production.up.railway.app"
VERIFICATION_URI = f"{OFFICIAL_ORIGIN}/cli/authorize"
CLIENT_ID = "character-relay-cli"
SCOPES = ("identity:read", "rooms:read", "messages:read")
DEVICE_GRANT_TYPE = "urn:ietf:params:oauth:grant-type:device_code"
MAX_RESPONSE_BYTES = 1_048_576
_ROOM_ID = re.compile(r"[A-Za-z0-9_-]{1,64}\Z")
_USER_CODE = re.compile(r"[A-Z0-9]{5}-[A-Z0-9]{5}\Z")


class ClientError(Exception):
    """Only fixed, non-secret messages may reach the console."""


class SafeArgumentParser(argparse.ArgumentParser):
    def error(self, message: str) -> Never:
        # argparse's default error echoes unknown arguments, including pasted secrets.
        self.exit(2, "Invalid CLI arguments. Use --help for usage.\n")


def build_parser() -> argparse.ArgumentParser:
    parser = SafeArgumentParser(
        prog="character-relay-cli",
        description="Approve a temporary, read-only Relay session in your browser.",
    )
    parser.add_argument(
        "--room",
        action="append",
        required=True,
        metavar="ROOM_ID",
        help="Explicit Relay room ID; repeat for each requested room.",
    )
    parser.add_argument(
        "--revoke",
        action="store_true",
        help="Revoke this grant after the identity and room smoke reads.",
    )
    return parser


def _integer(value: object, minimum: int, maximum: int) -> int:
    if type(value) is not int or not minimum <= value <= maximum:
        raise ClientError("The service returned an invalid authorization response.")
    return value


def _credential(value: object, *, prefix: str | None = None) -> str:
    if (
        not isinstance(value, str)
        or not 24 <= len(value) <= 512
        or not value.isascii()
        or any(character.isspace() or ord(character) < 33 for character in value)
        or (prefix is not None and not value.startswith(prefix))
    ):
        raise ClientError("The service returned an invalid authorization response.")
    return value


def _request(
    client: httpx.Client,
    method: str,
    path: str,
    *,
    token: str | None = None,
    payload: dict[str, object] | None = None,
    form: dict[str, str] | None = None,
) -> tuple[int, dict[str, Any]]:
    # Never inherit a caller's base URL, redirect setting, Authorization or Cookie.
    # Clearing cookies on both sides also discards unsolicited Set-Cookie responses.
    client.cookies.clear()
    headers = {"Accept": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    request = httpx.Request(
        method,
        f"{OFFICIAL_ORIGIN}{path}",
        headers=headers,
        json=payload,
        data=form,
    )
    try:
        with closing(
            client.send(
                request,
                stream=True,
                follow_redirects=False,
                auth=None,
            )
        ) as response:
            if 300 <= response.status_code < 400:
                raise ClientError("The service redirected the request; access stopped.")
            if response.status_code == 204:
                return response.status_code, {}
            body = bytearray()
            for chunk in response.iter_bytes():
                body.extend(chunk)
                if len(body) > MAX_RESPONSE_BYTES:
                    raise ClientError("The service response exceeded the safe size limit.")
            try:
                result = json.loads(body)
            except (ValueError, UnicodeError):
                raise ClientError("The service returned an unreadable response.") from None
            if not isinstance(result, dict):
                raise ClientError("The service returned an unreadable response.")
            return response.status_code, result
    finally:
        client.cookies.clear()


def _success(status: int) -> None:
    if not 200 <= status < 300:
        raise ClientError("The service refused the request; access stopped.")


def run_session(
    client: httpx.Client,
    room_ids: Sequence[str],
    *,
    revoke: bool = False,
    output: TextIO | None = None,
    monotonic: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> None:
    """Approve, read bounded snapshots, optionally revoke, then discard credentials.

    The console shows counts and safe identity/grant metadata, not message bodies or
    raw server responses. The only credentials are local variables of this call.
    """
    output = output if output is not None else sys.stdout
    rooms = list(dict.fromkeys(room_ids))
    if (
        not rooms
        or len(rooms) > 32
        or any(not _ROOM_ID.fullmatch(room) or room.lower().startswith("crcli_") for room in rooms)
    ):
        raise ClientError("Specify between 1 and 32 valid, explicit Relay room IDs.")
    status, authorization = _request(
        client,
        "POST",
        "/api/cli-auth/device-authorizations",
        payload={"client_id": CLIENT_ID, "scopes": list(SCOPES), "room_ids": rooms},
    )
    _success(status)
    if authorization.get("verification_uri") != VERIFICATION_URI:
        raise ClientError("The service returned an unexpected approval URL; access stopped.")
    user_code = authorization.get("user_code")
    if not isinstance(user_code, str) or not _USER_CODE.fullmatch(user_code):
        raise ClientError("The service returned an invalid approval code.")
    device_code = _credential(authorization.get("device_code"))
    expires_in = _integer(authorization.get("expires_in"), 1, 600)
    interval = _integer(authorization.get("interval", 5), 1, 60)
    deadline = monotonic() + expires_in
    print(f"Open {VERIFICATION_URI}\nApproval code: {user_code}", file=output, flush=True)
    print("Waiting for your approval...", file=output, flush=True)
    token: str | None = None
    while monotonic() < deadline:
        remaining = deadline - monotonic()
        if remaining <= interval:
            sleep(max(remaining, 0))
            break
        sleep(interval)
        if monotonic() >= deadline:
            break
        try:
            status, exchange = _request(
                client,
                "POST",
                "/api/cli-auth/token",
                form={
                    "client_id": CLIENT_ID,
                    "device_code": device_code,
                    "grant_type": DEVICE_GRANT_TYPE,
                },
            )
        except httpx.TimeoutException:
            # RFC 8628: reduce polling frequency on connection timeout.
            interval = min(interval * 2, 600)
            continue
        if status == 200:
            if str(exchange.get("token_type", "")).lower() != "bearer":
                raise ClientError("The service returned an invalid authorization response.")
            _integer(exchange.get("expires_in"), 1, 900)
            token = _credential(exchange.get("access_token"), prefix="crcli_")
            break
        error = exchange.get("error")
        if status == 400 and error == "authorization_pending":
            continue
        if status == 400 and error == "slow_down":
            interval += 5
            continue
        if status == 400 and error == "access_denied":
            raise ClientError("Authorization was denied.")
        if status == 400 and error == "expired_token":
            raise ClientError("Authorization expired. Start a new session to try again.")
        raise ClientError("Authorization failed; access stopped.")
    if token is None:
        raise ClientError("Authorization expired. Start a new session to try again.")
    print("Approved. Reading the authorized identity and rooms...", file=output, flush=True)
    status, identity = _request(client, "GET", "/api/cli-auth/me", token=token)
    _success(status)
    safe_identity = {
        key: identity[key]
        for key in ("user_id", "display_name", "grant_id", "client_id", "expires_at")
        if isinstance(identity.get(key), str)
    }
    print(json.dumps({"identity": safe_identity}, ensure_ascii=True), file=output, flush=True)
    status, metadata = _request(client, "GET", "/api/cli/rooms", token=token)
    _success(status)
    listed_rooms = metadata.get("rooms")
    if not isinstance(listed_rooms, list) or not all(
        isinstance(item, dict) for item in listed_rooms
    ):
        raise ClientError("The service returned invalid room metadata.")
    authorized_ids = {item.get("id") for item in listed_rooms if isinstance(item.get("id"), str)}
    if not set(rooms).issubset(authorized_ids) or not authorized_ids.issubset(set(rooms)):
        raise ClientError("The service returned an unexpected room scope; access stopped.")
    for room_id in rooms:
        status, snapshot = _request(
            client,
            "GET",
            f"/api/cli/rooms/{room_id}/messages",
            token=token,
        )
        _success(status)
        messages = snapshot.get("messages")
        if (
            snapshot.get("room_id") != room_id
            or not isinstance(messages, list)
            or len(messages) > 64
        ):
            raise ClientError("The service returned an invalid bounded room snapshot.")
        print(
            json.dumps({"room_id": room_id, "message_count": len(messages)}),
            file=output,
            flush=True,
        )
    if revoke:
        status, _ = _request(client, "POST", "/api/cli-auth/revoke", token=token)
        _success(status)
        print("The current grant was revoked.", file=output, flush=True)
    else:
        print("Session complete; credentials were discarded from this process.", file=output)


def main(argv: Sequence[str] | None = None) -> int:
    arguments = build_parser().parse_args(argv)
    try:
        with httpx.Client(verify=True, follow_redirects=False, timeout=15.0) as client:
            run_session(client, arguments.room, revoke=arguments.revoke)
    except ClientError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except httpx.HTTPError:
        print("The secure service connection failed; access stopped.", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled; credentials were discarded from this process.", file=sys.stderr)
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
