"""Explicit restricted-credential boundary, independent of ordinary authentication."""

import re

CLI_TOKEN_PREFIX = "crcli_"
CLI_CLIENT_ID = "character-relay-cli"
CLI_CLIENT_NAME = "Character Relay CLI"
CLI_SCOPES = frozenset({"identity:read", "rooms:read", "messages:read"})


def restricted_credential(token: str) -> bool:
    return token.lower().startswith(CLI_TOKEN_PREFIX)


def restricted_authorization(header: str) -> bool:
    # Recognize tagged credentials even in malformed schemes/extra-token syntax.
    return any(restricted_credential(part) for part in header.split())


def allowed_cli_route(method: str, path: str) -> bool:
    if method == "POST":
        return path == "/api/cli-auth/revoke"
    if method != "GET":
        return False
    return path in {"/api/cli-auth/me", "/api/cli/rooms"} or bool(
        re.fullmatch(r"/api/cli/rooms/[A-Za-z0-9_-]{1,64}/(?:messages|events)", path)
    )
