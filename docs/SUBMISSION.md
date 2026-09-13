# Devpost/lablab.ai submission text — Callismatic

Draft for the project description fields. Trim/adjust once the live
Bedrock + AssemblyAI + CALL-E run is confirmed and real numbers (run time,
call outcome) can be quoted instead of estimated.

---

## Inspiration

Scam and spam calls get bad enough that people and small businesses block
all unknown numbers outright. That also blocks the client, the delivery
driver, the interviewer, and the doctor's office — because those are unknown
numbers too until someone actually listens. 80–90% of what gets silently
blocked leaves a voicemail nobody ever checks. So instead of a chatbot you
have to remember to ask, we built an agent that listens to every voicemail
for you and only speaks up — or calls back — when it actually matters.

## What it does

Callismatic triages a folder of voicemail recordings one at a time. For
each one it:

- Transcribes it with real AssemblyAI speech-to-text.
- Reasons about it with tools: `get_today` (to judge staleness), `check_past_decisions`
  (so a caller already handled isn't re-flagged), and `check_number_intel` (a
  transcript-content scam-script scan — deliberately not a Truecaller-style
  lookup, since no public API for that exists for a third-party project).
- Returns a forced structured decision: caller category, summary, key facts,
  whether a human needs to decide, whether it's safe to auto-handle with a
  callback (with the exact task for the calling agent), and whether the
  number should be blocked.
- Acts on that decision deterministically: blocks confirmed scam/spam
  numbers, places a real callback via CALL-E for simple/automatable
  requests, or surfaces genuinely important calls to the human with full
  context.

## How we built it

Python, the Strands Agents SDK for the agent loop and tool-calling, Amazon
Bedrock (Claude) as the model provider, AssemblyAI for voicemail
transcription, the CALL-E SDK for placing real outbound callbacks, and
Pydantic for the structured-output schema Strands enforces on every
response.

## Challenges we ran into

The honest handling of "block this number" was the one we spent the most
time on: it would have been easy to fake a Truecaller-style lookup, but
Truecaller has no public developer API for third parties. Building a real,
defensible signal instead — scanning the transcript itself for concrete
scam-script markers rather than a black-box "trust us" verdict — was slower
but is something we can actually stand behind in the demo.

## What's next

Real inbound telephony (Twilio recording webhooks) instead of a local
sample folder, a folder-watcher/background-service mode instead of a batch
run, and a richer number-intelligence signal (e.g. a carrier lookup API)
alongside the transcript heuristic.

## Track

**Professional Agents** — the audience is exactly the person forced into
"block all unknown numbers" as their only defense against call volume: a
solo consultant, freelancer, or small-business owner without staff to screen
calls for them.

---

## Per-hackathon notes

- **Agents for Humans**: the submission above, in full — repo, README,
  architecture diagram, MIT license, demo video.
- **Call-E**: a standalone extraction of the callback piece
  (`src/callismatic/callback.py`), submitted as a PR to
  `CALLE-AI/awesome-phone-call-agents` following their contribution
  template, with its own short demo video showing a real call placed.
- **AssemblyAI Voice Agent Hackathon**: the voicemail-transcription piece
  (`src/callismatic/voicemails.py`) as the genuinely necessary voice-intelligence
  layer feeding the whole pipeline — check the actual lablab.ai submission
  form for exact requirements before finalizing this entry.
