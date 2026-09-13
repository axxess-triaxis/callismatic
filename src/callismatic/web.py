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
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request, Response
from pydantic import BaseModel

from callismatic.agent import build_agent
from callismatic.corrections import record_correction
from callismatic.digest_report import BLOCKLIST_PATH, DIGEST_PATH, generate_weekly_digest
from callismatic.reminders import add_reminder, send_due_reminders
from callismatic.todos import TODOS_PATH, complete_todo, list_todos
from callismatic.tools import find_digest_entry, unblock_number
from callismatic.triage import triage_text_message
from callismatic.whatsapp_webhook import (
    parse_incoming_messages,
    verify_signature,
)

app = FastAPI(title="Callismatic")

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


@app.get("/", response_class=Response)
def dashboard() -> Response:
    digest = _load_json(DIGEST_PATH)[-20:][::-1]
    blocklist = _load_json(BLOCKLIST_PATH)[-20:][::-1]
    todos = list_todos()
    summary = html.escape(generate_weekly_digest(days=7))

    def esc(value: object) -> str:
        return html.escape(str(value))

    digest_rows = "".join(
        f"<tr><td>{esc(e['file'])}</td><td>{esc(e['triaged_at'])}</td>"
        f"<td>{esc(e['triage'].get('category', ''))}</td>"
        f"<td>{esc(e['triage'].get('summary', ''))}</td></tr>"
        for e in digest
    ) or "<tr><td colspan='4'>No voicemails/messages triaged yet.</td></tr>"

    blocklist_rows = "".join(
        f"<tr><td>{esc(e['phone_number'])}</td><td>{esc(e['reason'])}</td></tr>" for e in blocklist
    ) or "<tr><td colspan='2'>Nothing blocked yet.</td></tr>"

    todo_rows = "".join(
        f"<tr><td>{esc(t['id'])}</td><td>{esc(t['text'])}</td><td>{esc(t['source'])}</td></tr>" for t in todos
    ) or "<tr><td colspan='3'>No open to-dos.</td></tr>"

    body = f"""<!doctype html>
<html><head><title>Callismatic</title>
<style>
body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0b0f14; color: #e6edf3; }}
h1 {{ margin-bottom: 0.25rem; }}
p.tagline {{ color: #8b949e; margin-top: 0; }}
pre {{ background: #161b22; padding: 1rem; border-radius: 8px; white-space: pre-wrap; }}
table {{ border-collapse: collapse; width: 100%; margin-bottom: 2rem; }}
th, td {{ text-align: left; padding: 0.4rem 0.6rem; border-bottom: 1px solid #30363d; font-size: 0.9rem; }}
th {{ color: #8b949e; font-weight: 600; }}
h2 {{ border-bottom: 1px solid #30363d; padding-bottom: 0.3rem; }}
</style></head>
<body>
<h1>Callismatic</h1>
<p class="tagline">An agent that listens to the voicemails you'd never check, decides what needs you, and quietly handles or blocks the rest.</p>
<h2>Weekly digest</h2>
<pre>{summary}</pre>
<h2>Recent triage decisions</h2>
<table><tr><th>Source</th><th>Triaged at</th><th>Category</th><th>Summary</th></tr>{digest_rows}</table>
<h2>Blocked numbers</h2>
<table><tr><th>Number</th><th>Reason</th></tr>{blocklist_rows}</table>
<h2>Open to-dos</h2>
<table><tr><th>ID</th><th>Text</th><th>Source</th></tr>{todo_rows}</table>
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
