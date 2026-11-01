"""API-key checks shared by web.py and the MCP server.

Two keys, both read from os.environ at call time (Lambda loads them from Secrets Manager
at cold start, see lambda_handler.py):

- ADMIN_API_KEY: every route with a side effect, and everything a reader can do.
- READ_API_KEY: read-only access (the JSON read routes and /mcp), so a client that only
  needs to read -- an Alexa+ skill, a dashboard script -- never holds the admin key.

Both fail closed: an unset key matches nothing. Comparisons use hmac.compare_digest so
response timing doesn't leak how much of a guessed key was right.
"""

from __future__ import annotations

import hmac
import json
import os


def key_matches(provided: str | None, expected: str | None) -> bool:
    if not provided or not expected:
        return False
    return hmac.compare_digest(provided.encode("utf-8"), expected.encode("utf-8"))


def is_admin(provided: str | None) -> bool:
    return key_matches(provided, os.environ.get("ADMIN_API_KEY"))


def is_reader(provided: str | None) -> bool:
    return key_matches(provided, os.environ.get("READ_API_KEY")) or is_admin(provided)


def key_from_headers(headers: dict[str, str]) -> str | None:
    """X-API-Key, or `Authorization: Bearer <key>` for MCP clients that only support that."""
    if headers.get("x-api-key"):
        return headers["x-api-key"]
    scheme, _, token = headers.get("authorization", "").partition(" ")
    return token.strip() if scheme.lower() == "bearer" and token.strip() else None


class RequireReaderKey:
    """ASGI wrapper that rejects HTTP requests without a reader (or admin) key with 401."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
            if not is_reader(key_from_headers(headers)):
                body = json.dumps({"detail": "Missing or invalid API key"}).encode("utf-8")
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json"), (b"www-authenticate", b"Bearer")],
                })
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
