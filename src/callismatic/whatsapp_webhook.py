"""Receives WhatsApp Business Cloud API webhooks and feeds incoming text
messages into the same triage pipeline a voicemail goes through
(triage_text_message in triage.py) -- no separate reasoning path, no
separate schema.

Meta calls this webhook two ways:
1. GET  -- a one-time verification challenge when you configure the webhook
   URL in the Meta App dashboard. We must echo back `hub.challenge` if
   `hub.verify_token` matches WHATSAPP_VERIFY_TOKEN.
2. POST -- every actual incoming message/status event, signed with
   X-Hub-Signature-256 (HMAC-SHA256 over the raw body, keyed with
   WHATSAPP_APP_SECRET). We verify that signature before trusting the body
   at all -- anyone who can guess this URL can otherwise POST fake messages.

Run it with: `uvicorn callismatic.whatsapp_webhook:app --port 8000`, then
point a public HTTPS URL at it (a tunnel like ngrok for testing, or a real
hosting provider for production) and register that URL + WHATSAPP_VERIFY_TOKEN
in Meta's WhatsApp -> Configuration -> Webhook settings.

Sending a reply (send_whatsapp_message) needs WHATSAPP_ACCESS_TOKEN and
WHATSAPP_PHONE_NUMBER_ID, neither of which this module requires just to
receive and triage messages -- receiving and triaging works without them.
"""

from __future__ import annotations

import hashlib
import hmac
import os
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request, Response

from callismatic.agent import build_agent
from callismatic.triage import triage_text_message

JsonObject = dict[str, Any]

# Unlike cli.py, this module is its own process entrypoint when run via
# `uvicorn callismatic.whatsapp_webhook:app` -- nothing else calls
# load_dotenv() first, so it has to happen here at import time.
load_dotenv()

app = FastAPI(title="Callismatic WhatsApp webhook")

_agent = None


def _get_agent():
    global _agent
    if _agent is None:
        _agent = build_agent()
    return _agent


def verify_signature(payload_bytes: bytes, signature_header: str | None, app_secret: str) -> bool:
    """Verifies Meta's X-Hub-Signature-256 header over the raw request body.

    Returns False (never raises) for a missing header or a malformed one --
    callers should treat any False as "reject the request," not attempt to
    read the body further.
    """
    if not signature_header or not signature_header.startswith("sha256="):
        return False
    expected = hmac.new(app_secret.encode("utf-8"), payload_bytes, hashlib.sha256).hexdigest()
    provided = signature_header.removeprefix("sha256=")
    return hmac.compare_digest(expected, provided)


def parse_incoming_messages(payload: JsonObject) -> list[JsonObject]:
    """Extracts text messages from a WhatsApp Cloud API webhook payload.

    Returns a list of {"sender": wa_id, "message_id": wamid, "text": body}
    dicts -- only for `type: "text"` messages. Non-text messages (images,
    voice notes, reactions, status updates) are skipped: a voice note could
    be transcribed via the same AssemblyAI path voicemails already use, but
    that's a future extension, not something this parser does today.
    """
    results: list[JsonObject] = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for message in value.get("messages", []):
                if message.get("type") != "text":
                    continue
                text_body = message.get("text", {}).get("body")
                if not text_body:
                    continue
                results.append(
                    {
                        "sender": message.get("from"),
                        "message_id": message.get("id"),
                        "text": text_body,
                    }
                )
    return results


def send_whatsapp_message(to: str, body: str) -> JsonObject:
    """Sends a WhatsApp text message via the Cloud API. Raises RuntimeError if
    WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID are not configured."""
    access_token = os.environ.get("WHATSAPP_ACCESS_TOKEN")
    phone_number_id = os.environ.get("WHATSAPP_PHONE_NUMBER_ID")
    if not access_token or not phone_number_id:
        raise RuntimeError("WHATSAPP_ACCESS_TOKEN/WHATSAPP_PHONE_NUMBER_ID are not set -- see README.md for setup.")

    import httpx

    response = httpx.post(
        f"https://graph.facebook.com/v21.0/{phone_number_id}/messages",
        headers={"Authorization": f"Bearer {access_token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to,
            "type": "text",
            "text": {"body": body},
        },
        timeout=30.0,
    )
    if response.status_code >= 400:
        # Meta's error body is genuinely diagnosable (e.g. code 131030 "Recipient phone
        # number not in allowed list" for an unverified test number) -- raise_for_status()
        # alone discards it and leaves only a generic "400 Bad Request", confirmed against
        # the real API this session.
        try:
            detail = response.json().get("error", {})
            message = f"{detail.get('message', response.text)} (code {detail.get('code', 'unknown')})"
        except ValueError:
            message = response.text
        raise RuntimeError(f"WhatsApp send failed: {message}")
    return response.json()


@app.get("/webhook")
def verify_webhook(request: Request) -> Response:
    """Meta's one-time webhook verification GET: `hub.mode`, `hub.verify_token`, and
    `hub.challenge` arrive as query params (not headers, not a JSON body) -- read directly
    from request.query_params. Must echo back hub.challenge verbatim on success."""
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")

    expected_token = os.environ.get("WHATSAPP_VERIFY_TOKEN")
    if mode == "subscribe" and expected_token and token == expected_token:
        return Response(content=challenge, media_type="text/plain")
    raise HTTPException(status_code=403, detail="Verification failed")


@app.post("/webhook")
async def receive_webhook(request: Request, x_hub_signature_256: str | None = Header(None)) -> JsonObject:
    raw_body = await request.body()
    app_secret = os.environ.get("WHATSAPP_APP_SECRET")
    if app_secret and not verify_signature(raw_body, x_hub_signature_256, app_secret):
        raise HTTPException(status_code=403, detail="Invalid signature")

    payload = await request.json()
    agent = _get_agent()

    for message in parse_incoming_messages(payload):
        triage_text_message(
            agent,
            "whatsapp",
            message["sender"],
            message["message_id"],
            message["text"],
        )

    return {"status": "ok"}
