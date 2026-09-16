"""The single deployable app: a read-only dashboard, the WhatsApp webhook, and a
scoped, auth-gated JSON API over the same digest/blocklist/todos/reminders/corrections
data every CLI command already reads and writes.

Security posture, deliberate: GET routes (dashboard, /api/digest, /api/todos,
/api/blocklist) are public and read-only -- safe for anyone with the URL to view,
which is the point of a hosted demo. Every route with a side effect (completing a
todo, sending a reminder, recording a correction, or triggering a live triage run)
requires an `X-API-Key` header matching ADMIN_API_KEY. There is deliberately no public
"upload a voicemail and triage it" endpoint yet -- audio upload via a public Lambda
endpoint is real, unfinished scope, not an oversight; /api/triage/text (auth-gated,
dry-run by default) covers the SMS/WhatsApp-shaped case using the already-verified
triage_text_message path instead.
"""

from __future__ import annotations

import html
import json
import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel
from starlette.routing import Route

from callismatic.agent import build_agent
from callismatic.corrections import record_correction
from callismatic.digest_report import BLOCKLIST_PATH, DIGEST_PATH, generate_weekly_digest
from callismatic.mcp_server import app as mcp_asgi_app
from callismatic.mcp_server import mcp as mcp_server_instance
from callismatic.reminders import add_reminder, send_due_reminders
from callismatic.todos import TODOS_PATH, complete_todo, list_todos
from callismatic.tools import find_digest_entry, unblock_number
from callismatic.triage import triage_text_message
from callismatic.whatsapp_webhook import (
    parse_incoming_messages,
    verify_signature,
)


_mcp_session_cm = None  # holds the entered context manager alive -- see _lifespan


@asynccontextmanager
async def _lifespan(_app: FastAPI) -> AsyncIterator[None]:
    # A mounted ASGI sub-app's own lifespan is NOT triggered automatically by
    # Starlette's Mount -- found via a real live-client test that failed with
    # "Task group is not initialized. Make sure to use run()." on the very first
    # /mcp request through the full app, even though the standalone mcp_server.py
    # app (which uvicorn drives directly, invoking its lifespan itself) worked
    # fine. The MCP session manager's task group has to be entered explicitly
    # here instead.
    #
    # Entered via raw __aenter__, deliberately never __aexit__'d, with the context
    # manager object itself kept alive in a module global: found via two real
    # production failures in sequence, not guessed.
    #   1. A 502 on the *second* request after deploying to Lambda. Unlike a
    #      long-lived uvicorn process, Mangum runs the ASGI lifespan cycle (both
    #      startup AND shutdown) on every single invocation, not once per
    #      container -- so a plain `async with ...: yield` here tears the session
    #      manager's task group down at the end of the FIRST request, and
    #      StreamableHTTPSessionManager.run() also raises if entered a second
    #      time on the same instance ("can only be called once per instance")
    #      regardless. Fix: enter it exactly once for the process's whole life
    #      and never exit it -- Lambda freezes/thaws the container rather than
    #      cleanly shutting it down between invocations, so there's no real
    #      "shutdown" to run anyway.
    #   2. That fix alone still broke under a local 3-invocation simulation: the
    #      first `session_manager.run().__aenter__()` call's return value wasn't
    #      kept anywhere, so Python's garbage collector eventually finalized the
    #      orphaned context-manager object itself -- and its cleanup runs an
    #      anyio cancel-scope exit, which anyio requires happen in the same task
    #      it was entered from. GC runs on its own schedule, in whatever task
    #      happens to be current, which raised "Attempted to exit cancel scope in
    #      a different task than it was entered in". Fix: keep a strong
    #      module-level reference to the entered context manager so it's never
    #      garbage collected during the process's life.
    global _mcp_session_cm
    if _mcp_session_cm is None:
        _mcp_session_cm = mcp_server_instance.session_manager.run()
        await _mcp_session_cm.__aenter__()
    yield


app = FastAPI(title="Callismatic", lifespan=_lifespan)

# The MCP server (mcp_server.py) is the same read-only/safe tool set as the JSON
# API above, exposed over Streamable HTTP so an MCP client -- an Alexa+ Agent
# Skill, Claude Desktop, or any other MCP-speaking client -- can call it directly.
# Registered on the same already-deployed Lambda rather than standing up a
# second service, so it reuses the exact same Bedrock creds, Secrets Manager
# wiring, and IAM role the rest of this app already has.
#
# A direct Route at the exact path, NOT app.mount("/mcp", mcp_asgi_app) -- found
# by adding temporary debug logging and reading the real scope Lambda
# constructs, after three prior fix attempts (lifespan double-entry, DNS-
# rebinding host validation) were each real and each confirmed via local Mangum
# simulation, yet the live URL kept 307-redirecting /mcp/ to itself regardless.
# The actual cause: AWS Lambda Function URLs strip a trailing slash before
# Mangum ever constructs the ASGI scope -- confirmed directly from a live
# CloudWatch log line for a request sent to "/mcp/": `path='/mcp'`. A synthetic
# local test event can't reproduce this because it never goes through AWS's own
# normalization; only a real request does. Starlette's Mount, on seeing the
# request path exactly equal its own registered prefix with nothing left over,
# redirects to add a trailing slash -- and since every subsequent request also
# gets normalized back to no-trailing-slash by AWS itself, the redirect target
# is unreachable by construction: infinite loop, not a transient bug. A plain
# Route matches the exact literal path with no prefix-stripping or trailing-
# slash semantics to go wrong, sidestepping the mismatch entirely.
app.router.routes.append(Route("/mcp", endpoint=mcp_asgi_app.routes[0].app, methods=None))

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def _require_admin(x_api_key: str | None) -> None:
    expected = os.environ.get("ADMIN_API_KEY")
    if not expected or x_api_key != expected:
        raise HTTPException(status_code=401, detail="Missing or invalid X-API-Key")


def _load_json(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return json.loads(path.read_text(encoding="utf-8"))


# --------------------------------------------------------------------------
# Dashboard (public, read-only)
# --------------------------------------------------------------------------


_CATEGORY_COLORS = {
    "scam": "#f85149",
    "spam": "#db6d28",
    "lead": "#58a6ff",
    "important": "#d29922",
    "routine": "#8b949e",
}

_URGENCY_COLORS = {
    "low": "#8b949e",
    "medium": "#d29922",
    "high": "#f85149",
}


def _within_days(timestamp_iso: str, since: datetime) -> bool:
    try:
        timestamp = datetime.fromisoformat(timestamp_iso)
    except ValueError:
        return False
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    return timestamp >= since


@app.get("/", response_class=Response)
def dashboard() -> Response:
    all_digest = _load_json(DIGEST_PATH)
    all_blocklist = _load_json(BLOCKLIST_PATH)
    digest = all_digest[-20:][::-1]
    blocklist = all_blocklist[-20:][::-1]
    todos = list_todos()

    since = datetime.now(timezone.utc) - timedelta(days=7)
    weekly = [e for e in all_digest if _within_days(e["triaged_at"], since)]
    needs_decision_count = sum(1 for e in weekly if e["triage"].get("needs_decision"))
    auto_handled_count = len(weekly) - needs_decision_count

    def esc(value: object) -> str:
        return html.escape(str(value))

    def badge(category: str) -> str:
        color = _CATEGORY_COLORS.get(category, "#8b949e")
        return f'<span class="badge" style="--badge-color:{color}">{esc(category)}</span>'

    def flag_tags(triage: dict) -> str:
        tags = []
        if triage.get("needs_decision"):
            tags.append('<span class="tag tag-decision">needs decision</span>')
        if triage.get("callback_recommended"):
            tags.append('<span class="tag">callback</span>')
        if triage.get("block_recommended"):
            tags.append('<span class="tag tag-blocked">blocked</span>')
        urgency = triage.get("urgency", "none")
        if urgency and urgency != "none":
            color = _URGENCY_COLORS.get(urgency, "#8b949e")
            tags.append(f'<span class="tag" style="--tag-color:{color}">{esc(urgency)} urgency</span>')
        return "".join(tags)

    def triage_card(e: dict) -> str:
        triage = e.get("triage") or {}
        category = triage.get("category", "routine")
        needs_decision = bool(triage.get("needs_decision"))
        card_class = "card triage-card" + (" needs-decision" if needs_decision else "")
        return f"""<div class="{card_class}" style="--accent-color:{_CATEGORY_COLORS.get(category, '#8b949e')}">
  <div class="card-top">
    {badge(category)}
    <span class="timestamp">{esc(e.get('triaged_at', ''))}</span>
  </div>
  <div class="card-source">{esc(e.get('file', ''))}</div>
  <p class="card-summary">{esc(triage.get('summary', ''))}</p>
  <div class="tag-row">{flag_tags(triage)}</div>
</div>"""

    digest_cards = "".join(triage_card(e) for e in digest) or '<p class="empty">No voicemails/messages triaged yet.</p>'

    blocklist_rows = "".join(
        f'<div class="list-row"><span class="mono">{esc(e["phone_number"])}</span>'
        f'<span class="muted">{esc(e["reason"])}</span></div>'
        for e in blocklist
    ) or '<p class="empty">Nothing blocked yet.</p>'

    todo_rows = "".join(
        f'<div class="list-row todo-row"><span class="todo-check">&#9744;</span>'
        f'<span>{esc(t["text"])}</span><span class="muted">{esc(t["source"])}</span></div>'
        for t in todos
    ) or '<p class="empty">No open to-dos.</p>'

    body = f"""<!doctype html>
<html><head><title>Callismatic</title>
<style>
:root {{
  --bg: #0b0f14;
  --bg-card: #12161c;
  --border: #242c36;
  --text: #e6edf3;
  --text-muted: #8b949e;
}}
* {{ box-sizing: border-box; }}
body {{
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", system-ui, sans-serif;
  margin: 0; padding: 2.5rem 1.5rem;
  background: var(--bg); color: var(--text);
}}
.wrap {{ max-width: 960px; margin: 0 auto; }}
header {{ margin-bottom: 2.5rem; }}
h1 {{ margin: 0 0 0.35rem; font-size: 1.6rem; letter-spacing: -0.02em; }}
p.tagline {{ color: var(--text-muted); margin: 0; font-size: 0.95rem; }}
h2 {{
  font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em;
  color: var(--text-muted); font-weight: 600; margin: 0 0 0.9rem;
}}
section {{ margin-bottom: 2.5rem; }}

.stat-grid {{
  display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
  gap: 0.85rem; margin-bottom: 2.5rem;
}}
.stat-card {{
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
  padding: 1.1rem 1.2rem;
}}
.stat-number {{ font-size: 1.9rem; font-weight: 650; line-height: 1.1; }}
.stat-label {{ color: var(--text-muted); font-size: 0.82rem; margin-top: 0.3rem; }}

.card {{
  background: var(--bg-card); border: 1px solid var(--border); border-radius: 10px;
  padding: 0.9rem 1.1rem; margin-bottom: 0.6rem;
}}
.triage-card {{ border-left: 3px solid var(--accent-color); }}
.triage-card.needs-decision {{ background: #161b1f; border-left-width: 4px; }}
.card-top {{ display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.45rem; }}
.timestamp {{ color: var(--text-muted); font-size: 0.78rem; }}
.card-source {{ font-size: 0.82rem; color: var(--text-muted); margin-bottom: 0.25rem; }}
.card-summary {{ margin: 0 0 0.5rem; font-size: 0.94rem; line-height: 1.4; }}

.badge {{
  display: inline-block; padding: 0.15rem 0.55rem; border-radius: 999px;
  font-size: 0.72rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.03em;
  color: var(--badge-color); background: color-mix(in srgb, var(--badge-color) 16%, transparent);
  border: 1px solid color-mix(in srgb, var(--badge-color) 40%, transparent);
}}
.tag-row {{ display: flex; flex-wrap: wrap; gap: 0.35rem; }}
.tag {{
  font-size: 0.72rem; padding: 0.1rem 0.5rem; border-radius: 6px;
  background: #1c2129; color: var(--tag-color, var(--text-muted)); border: 1px solid var(--border);
}}
.tag-decision {{ color: #d29922; border-color: color-mix(in srgb, #d29922 40%, transparent); }}
.tag-blocked {{ color: #f85149; border-color: color-mix(in srgb, #f85149 40%, transparent); }}

.list-row {{
  display: flex; justify-content: space-between; align-items: center; gap: 0.75rem;
  padding: 0.6rem 0.2rem; border-bottom: 1px solid var(--border); font-size: 0.88rem;
}}
.list-row:last-child {{ border-bottom: none; }}
.todo-row {{ justify-content: flex-start; }}
.todo-row span:nth-child(2) {{ flex: 1; }}
.todo-check {{ color: var(--text-muted); }}
.mono {{ font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 0.85rem; }}
.muted {{ color: var(--text-muted); font-size: 0.82rem; }}
.empty {{ color: var(--text-muted); font-size: 0.88rem; font-style: italic; margin: 0; }}
</style></head>
<body>
<div class="wrap">
<header>
<h1>Callismatic</h1>
<p class="tagline">The voicemails you'd never check &mdash; triaged, so you don't have to.</p>
</header>

<div class="stat-grid">
  <div class="stat-card"><div class="stat-number">{len(weekly)}</div><div class="stat-label">Triaged this week</div></div>
  <div class="stat-card"><div class="stat-number">{needs_decision_count}</div><div class="stat-label">Needs your decision</div></div>
  <div class="stat-card"><div class="stat-number">{auto_handled_count}</div><div class="stat-label">Auto-handled</div></div>
  <div class="stat-card"><div class="stat-number">{len(todos)}</div><div class="stat-label">Open to-dos</div></div>
</div>

<section>
<h2>Recent triage decisions</h2>
{digest_cards}
</section>

<section>
<h2>Blocked numbers</h2>
<div class="card">{blocklist_rows}</div>
</section>

<section>
<h2>Open to-dos</h2>
<div class="card">{todo_rows}</div>
</section>
</div>
</body></html>"""
    return Response(content=body, media_type="text/html")


# --------------------------------------------------------------------------
# Read-only JSON API (public)
# --------------------------------------------------------------------------


@app.get("/api/digest")
def api_digest(days: int = 7) -> dict:
    return {"summary": generate_weekly_digest(days=days), "entries": _load_json(DIGEST_PATH)[-50:]}


@app.get("/api/todos")
def api_todos() -> list[dict]:
    return list_todos()


@app.get("/api/blocklist")
def api_blocklist() -> list[dict]:
    return _load_json(BLOCKLIST_PATH)


# --------------------------------------------------------------------------
# Mutating JSON API (auth-gated)
# --------------------------------------------------------------------------


@app.post("/api/todos/{item_id}/complete")
def api_complete_todo(item_id: str, x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    if not complete_todo(item_id):
        raise HTTPException(status_code=404, detail=f"No open to-do with id {item_id}")
    return {"status": "completed", "id": item_id}


class ReminderRequest(BaseModel):
    text: str
    due_at: str
    to: str | None = None


@app.post("/api/reminders")
def api_add_reminder(body: ReminderRequest, x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    return add_reminder(body.text, body.due_at, to=body.to)


@app.post("/api/reminders/send")
def api_send_reminders(x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    sent = send_due_reminders()
    return {"sent_count": len(sent), "sent": sent}


class UnblockRequest(BaseModel):
    phone_number: str
    reason: str = "Manually unblocked -- not actually scam/spam."


@app.post("/api/correct/unblock")
def api_unblock(body: UnblockRequest, x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    removed = unblock_number(body.phone_number)
    record_correction(
        target=body.phone_number,
        original={"block_recommended": True},
        corrected={"block_recommended": False},
        reason=body.reason,
    )
    return {"phone_number": body.phone_number, "was_on_blocklist": removed}


class RecategorizeRequest(BaseModel):
    file_name: str
    category: str | None = None
    needs_decision: bool | None = None
    callback_recommended: bool | None = None
    block_recommended: bool | None = None
    reason: str = "Manually recategorized."


@app.post("/api/correct/recategorize")
def api_recategorize(body: RecategorizeRequest, x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    entry = find_digest_entry(body.file_name)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"No past decision found for {body.file_name}")
    corrected = {
        k: v
        for k, v in {
            "category": body.category,
            "needs_decision": body.needs_decision,
            "callback_recommended": body.callback_recommended,
            "block_recommended": body.block_recommended,
        }.items()
        if v is not None
    }
    if not corrected:
        raise HTTPException(status_code=400, detail="Provide at least one field to correct")
    record_correction(target=body.file_name, original=entry["triage"], corrected=corrected, reason=body.reason)
    return {"file_name": body.file_name, "corrected": corrected}


class TriageTextRequest(BaseModel):
    channel: Literal["sms", "whatsapp"]
    sender: str
    message_id: str
    text: str
    place_callbacks: bool = False  # safe by default -- an explicit opt-in to spend real CALL-E quota


@app.post("/api/triage/text")
def api_triage_text(body: TriageTextRequest, x_api_key: str | None = Header(None)) -> dict:
    _require_admin(x_api_key)
    agent = _get_agent()
    result = triage_text_message(
        agent, body.channel, body.sender, body.message_id, body.text, place_callbacks=body.place_callbacks
    )
    return {
        "file_name": result.file_name,
        "caller_number": result.caller_number,
        "triage": result.triage.model_dump() if result.triage else None,
        "callback_result": result.callback_result,
        "error": result.error,
    }


# --------------------------------------------------------------------------
# WhatsApp webhook (Meta's own auth: signature verification / verify token)
# --------------------------------------------------------------------------


@app.get("/webhook")
def whatsapp_verify(request: Request) -> Response:
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")
    expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and expected_token and token == expected_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def whatsapp_receive(request: Request, x_hub_signature_256: str | None = Header(None)) -> dict:
    raw_body = await request.body()
    app_secret = os.environ.get("WHATSAPP_APP_SECRET")
    if app_secret and not verify_signature(raw_body, x_hub_signature_256, app_secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    agent = _get_agent()
    for message in parse_incoming_messages(payload):
        triage_text_message(agent, "whatsapp", message["sender"], message["message_id"], message["text"])
    return {"status": "ok"}
