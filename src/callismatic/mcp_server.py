"""Exposes Callismatic as a real MCP (Model Context Protocol) server, over
Streamable HTTP -- the same underlying functions the CLI and web.py already
use, not new business logic.

Built for the Amazon Developer Hackathon's Alexa+ track: "MCP is the open
standard that powers Alexa+ integrations." Protocol version is negotiated
per-request via the client's `MCP-Protocol-Version` header (see
mcp.server.streamable_http) -- this SDK (mcp 2.1.1, LATEST_PROTOCOL_VERSION
2026-07-28) already handles 2025-11-25+ correctly whenever a client declares
it; nothing here needs to force a version.

Same security posture as web.py: every tool here is read-only, or -- for
triage_message -- defaults to place_callbacks=False, so a voice assistant
calling this server can never place a real phone call or mutate the
blocklist/todos without an explicit opt-in. Tools that actually change state
(completing a to-do, unblocking a number) are deliberately NOT exposed here
yet, the same "no public mutating endpoint without a real auth story"
judgment call web.py already makes for its own public routes.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from mcp.server.mcpserver import MCPServer
from mcp.server.transport_security import TransportSecuritySettings

from callismatic.agent import build_agent
from callismatic.digest_report import BLOCKLIST_PATH, DIGEST_PATH, generate_weekly_digest
from callismatic.todos import list_todos
from callismatic.tools import check_past_decisions as _check_past_decisions
from callismatic.tools import check_corrections as _check_corrections
from callismatic.triage import triage_text_message


def _load_json(path: Path) -> list[dict]:
    # Deliberately not imported from web.py -- web.py mounts this module's ASGI
    # app, so importing back from web.py here would be a circular import. Same
    # three lines as web.py's own _load_json; not worth a shared module for.
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))

mcp = MCPServer(
    name="callismatic",
    version="0.2.0",
    instructions=(
        "Callismatic is a personal and phone secretary agent. It listens to voicemails "
        "and messages you'd otherwise leave blocked, decides what needs a human, and "
        "quietly handles or blocks the rest. Use these tools to check what it's done, "
        "or to have it triage a new message live."
    ),
)

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


@mcp.tool()
def get_weekly_digest(days: int = 7) -> str:
    """Returns a plain-text summary of everything Callismatic has triaged in the last
    N days: how many messages needed a decision, how many got a callback, how many
    numbers were blocked, and how many were filed away with no action needed.

    Args:
        days: how many days back to summarize (default 7).
    """
    return generate_weekly_digest(days=days)


@mcp.tool()
def list_blocked_numbers() -> list[dict]:
    """Lists every phone number Callismatic has blocked as a confirmed scam or spam
    source, most recent first, with the reason it was blocked."""
    return list(reversed(_load_json(BLOCKLIST_PATH)))


@mcp.tool()
def list_open_todos() -> list[dict]:
    """Lists every open to-do Callismatic created from a voicemail or message that
    needed a human decision -- these are the things still waiting on you."""
    return list_todos()


@mcp.tool()
def check_caller(phone_number: str) -> str:
    """Checks what Callismatic already knows about a phone number: any past triage
    decisions about it, and any human corrections that should override its own
    judgment for that caller.

    Args:
        phone_number: the caller's phone number, e.g. in E.164 format (+15551234567).
    """
    decisions = _check_past_decisions(phone_number)
    corrections = _check_corrections(phone_number)
    return f"{decisions}\n\n{corrections}"


@mcp.tool()
def triage_message(text: str, sender: str = "unknown") -> dict:
    """Runs a real, live triage of a voicemail transcript or message through
    Callismatic's actual agent (Strands Agents SDK on Amazon Bedrock/Nova) -- the
    same reasoning it applies to every real voicemail. Returns the category (scam,
    spam, lead, important, routine), a summary, whether a human needs to decide,
    and whether the number should be blocked. Never places a real outbound call or
    mutates the blocklist as a side effect of this tool -- it only decides and reports.

    Args:
        text: the voicemail transcript or message text to triage.
        sender: the caller's phone number, if known.
    """
    agent = _get_agent()
    result = triage_text_message(
        agent, "sms", sender, f"mcp:{sender}", text, place_callbacks=False
    )
    return {
        "category": result.triage.category if result.triage else None,
        "summary": result.triage.summary if result.triage else None,
        "needs_decision": result.triage.needs_decision if result.triage else None,
        "block_recommended": result.triage.block_recommended if result.triage else None,
        "callback_recommended": result.triage.callback_recommended if result.triage else None,
        "urgency": result.triage.urgency if result.triage else None,
        "error": result.error,
    }


def build_app(*, stateless: bool = True):
    """Returns the ASGI app for the Streamable HTTP transport.

    stateless=True (the default) is deliberate for the Lambda deployment: Lambda's
    request/response execution model doesn't hold a long-lived process between
    invocations the way a persistent server would, so per-session state on the MCP
    server itself would silently break across cold starts. Streamable HTTP supports
    a stateless mode for exactly this reason -- json_response=True disables the
    SSE-streaming path in favor of plain request/response, which is what a stateless
    Lambda deployment actually needs.
    """
    # DNS-rebinding Host-header validation, ON by default in this SDK, rejects any
    # Host it doesn't recognize with 421 "Invalid Host header" -- and a Lambda
    # Function URL's hostname is assigned dynamically by AWS at function creation,
    # not something to hardcode into an allow-list. Found by faithfully simulating
    # a real Lambda Function URL event through the actual Mangum handler locally
    # (not guessed): a POST to /mcp/ with the real deployed hostname came back 421,
    # body "Invalid Host header" -- the redirect loop curl showed against the live
    # URL is this same rejection interacting badly with Starlette's redirect
    # handling, not a separate bug. Disabling it here is a deliberate trade-off,
    # not a blanket "turn off security": this protection exists to stop a
    # malicious webpage from using DNS rebinding to reach a server that trusts
    # `localhost`/cookie-based auth -- this server has no cookie or session-based
    # auth for rebinding to exploit, and every route is already public/read-mostly
    # by the same posture web.py's own docstring already states for the rest of
    # this app.
    security = TransportSecuritySettings(enable_dns_rebinding_protection=False)
    http_app = mcp.streamable_http_app(
        streamable_http_path="/",
        json_response=stateless,
        stateless_http=stateless,
        transport_security=security,
    )
    # Belt-and-suspenders: this sub-app has exactly one route, registered at "/",
    # so there's no real ambiguity for slash-redirection to resolve -- disabled
    # outright rather than left to interact with the parent Mount's own handling.
    http_app.router.redirect_slashes = False
    return http_app


app = build_app()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("MCP_PORT", "8001")))
