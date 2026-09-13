# Devpost/lablab.ai submission text — Callismatic

Ready-to-paste copy for four hackathon forms. The core Devpost "Story" text (Inspiration
through What's next) is shared between Agents for Humans and Call-E, since both use Devpost's
standard story format; per-platform sections below cover what differs. AMD Developer
Hackathon: ACT III is a separate, later submission (deadline Oct 18, 2026) built around
`docs/AMD_ACT3_ARCHITECTURE.md` rather than this shared story, since it targets a different
piece of the project (the training architecture, not the live triage pipeline).

---

## Shared Devpost story (Agents for Humans + Call-E)

### Inspiration

Scam and spam calls get bad enough that people and small businesses block all unknown numbers
outright. That also blocks the client, the delivery driver, the interviewer, and the doctor's
office — because those are unknown numbers too until someone actually listens. 80–90% of what
gets silently blocked leaves a voicemail nobody ever checks. So instead of a chatbot you have to
remember to ask, we built an agent that listens to every voicemail for you and only speaks up —
or calls back — when it actually matters.

### What it does

Callismatic triages a folder of voicemail recordings one at a time. For each one it:

- Transcribes it with real AssemblyAI speech-to-text.
- Reasons about it with tools: `get_today` (to judge staleness), `check_past_decisions` (so a
  caller already handled isn't re-flagged), `check_number_intel` (a transcript-content
  scam-script scan — deliberately not a Truecaller-style lookup, since no public API for that
  exists for a third-party project), and `check_corrections` (a human override always wins over
  the agent's own judgment for that caller).
- Returns a forced structured decision: caller category, summary, key facts, whether a human
  needs to decide, whether it's safe to auto-handle with a callback (with the exact task for the
  calling agent), and whether the number should be blocked.
- Acts on that decision deterministically: blocks confirmed scam/spam numbers, places a real
  callback via CALL-E for simple/automatable requests, or surfaces genuinely important calls to
  the human with full context.

### How we built it

Python, the Strands Agents SDK for the agent loop and tool-calling, Amazon Bedrock as the model
provider, AssemblyAI for voicemail transcription, the CALL-E SDK for placing real outbound
callbacks, and Pydantic for the structured-output schema Strands enforces on every response.

### Challenges we ran into

Three real ones, not hypotheticals:

1. **Honest scam detection.** It would have been easy to fake a Truecaller-style lookup, but
   Truecaller has no public developer API for third parties. We built a real, defensible signal
   instead — scanning the transcript itself for concrete scam-script markers, plus an optional
   second signal from Twilio Lookup's carrier/line-type data — rather than a black-box "trust us"
   verdict.
2. **Bedrock model access has two separate gates, not one.** Getting Claude working on Bedrock
   needed both the Anthropic use-case form *and* a valid AWS Marketplace payment method — we hit
   `AccessDeniedException: INVALID_PAYMENT_INSTRUMENT` even after the use-case form was approved,
   and fell back to Amazon Nova (no Marketplace subscription required) to keep testing while that
   gets resolved on the account side.
3. **"International" doesn't mean "works everywhere."** A real CALL-E call to an Indian number
   genuinely dialed (confirmed by a real `provider_call_id` and attempt log) but never rang —
   India is served through CALL-E's "International" tier, and local carrier-level filtering of
   unrecognized international caller IDs is a known, real phenomenon. That finding shaped our
   `call_router.py` design: a per-country provider registry so a regional partner can be plugged
   in later without touching calling code.

### Accomplishments that we're proud of

A real, verified end-to-end run: AssemblyAI transcribed an actual audio file, Strands/Bedrock
correctly classified four distinct voicemail types (scam, lead, appointment confirmation,
important client matter), and a real CALL-E call was genuinely placed to a real phone number —
not a mocked demo, an actual dial attempt with a provider-confirmed call ID.

### What's next

Since this draft: a hosted dashboard + API deployed live on AWS Lambda, a Google Sheets CRM
sync verified against a real spreadsheet, Google Calendar availability/booking verified
against a real calendar, and a WhatsApp receiver/sender verified directly against Meta's
Cloud API — though Meta actually auto-forwarding real incoming messages to it still needs
Business Verification (a separate identity/document review process), not yet done. A Twilio
Lookup carrier-intelligence signal is wired and tested but currently blocked by Twilio's own
trial-account quota. Still ahead: real inbound telephony (Twilio recording webhooks) instead
of a local sample folder, and a folder-watcher/background-service mode instead of a batch
run.

### Track

**Professional Agents** — the audience is exactly the person forced into "block all unknown
numbers" as their only defense against call volume: a solo consultant, freelancer, or
small-business owner without staff to screen calls for them.

### Built With

python, strands-agents, amazon-bedrock, amazon-nova, assemblyai, calle, pydantic, boto3

---

## Agents for Humans — additional fields

- **Try it out (repo)**: https://github.com/axxess-triaxis/callismatic
- **License**: MIT (in repo)
- **AWS Builder ID**: [founder to fill in]

---

## Call-E — additional fields

- **Pull request URL**: https://github.com/CALLE-AI/awesome-phone-call-agents/pull/527
- **CALL-E account email**: [founder to fill in]
- **Demo video**: ~3 min, focused specifically on `apps/python/voicemail-triage-callback`
  (the extracted callback piece), not the whole pipeline — see docs/DEMO_SCRIPT.md's note at
  the bottom.

---

## AssemblyAI Voice Agent Hackathon (lablab.ai) — different form, different fields

Confirmed directly from the actual submission page (lablab.ai/event/assemblyai-voice-agent-hackathon):

- **Project title**: Callismatic
- **Short description** (one line): An agent that listens to the voicemails you'd never check,
  decides what needs you, and quietly handles or blocks the rest — built on AssemblyAI,
  Strands/Bedrock, and CALL-E.
- **Long description**: reuse the Inspiration + What it does sections above.
- **Technology & category tags**: AssemblyAI, Amazon Bedrock, Strands Agents SDK, CALL-E, Python
- **Cover image**: [needs a static image — a screenshot of a triage run or the architecture
  diagram rendered as PNG]
- **Video presentation**: same demo video as Agents for Humans, or a trimmed cut
- **Slide presentation**: [not yet built]
- **Public GitHub repository**: https://github.com/axxess-triaxis/callismatic
- **Demo application platform / Application URL**: **closed** —
  https://awpfsufk4dofdncv6cgqsaifwy0kvolm.lambda-url.us-east-1.on.aws/ — a real, live AWS
  Lambda deployment (`web.py`), not a static page: a dashboard over real digest/blocklist/
  to-do data, plus a JSON API. Verified end-to-end after deployment — a real scam-script
  message posted to its `/api/triage/text` endpoint was correctly classified and blocked by
  a live Bedrock call running under the Lambda's own IAM role.

---

## AMD Developer Hackathon: ACT III (lablab.ai) — separate submission, later deadline

Confirmed from lablab.ai/event/amd-developer-hackathon-act-iii: theme "Build AI agents and
high-performance AI applications on AMD GPUs in the cloud," online build phase Oct 12–18,
2026, hybrid on-site optional, prize pool $5,000+, requires an AMD AI Developer Program (ADP)
account.

This submission is **not** the live triage pipeline (that's already built and running on
Bedrock/Nova) — it's the proprietary training architecture in
[`docs/AMD_ACT3_ARCHITECTURE.md`](AMD_ACT3_ARCHITECTURE.md): a Kubernetes-orchestrated LoRA
fine-tuning pipeline on AMD GPU infrastructure, trained on Callismatic's own accumulated
triage decisions (`digest.json`) and human corrections (`corrections.json`) — data already
being collected as a side effect of the correction feedback loop, not something built new for
this hackathon. As of this writing, **no AMD compute has been provisioned and no training has
run** — that document is the design ACT III's build window would build a first real slice of.

- **Project title**: Callismatic — Proprietary Triage Model on AMD GPUs
- **Short description**: A Kubernetes-orchestrated pipeline that fine-tunes a task-specific
  model on Callismatic's own accumulated call-triage decisions and human corrections, on AMD
  GPU infrastructure — plugged into the live agent via Strands' native `ModelRouter`/
  `FallbackStrategy`, with Bedrock/Nova staying as the safety net, not something replaced.
- **Long description**: reuse `docs/AMD_ACT3_ARCHITECTURE.md` directly — it's already written
  as a submission-ready design document, not internal notes.
- **What makes this proprietary, not a wrapper**: the training data itself — real triage
  decisions plus real human overrides, the exact shape of labeled fine-tuning data, already
  flowing from features (the correction feedback loop) built for a different reason.
- **Public GitHub repository**: https://github.com/axxess-triaxis/callismatic
  (`docs/AMD_ACT3_ARCHITECTURE.md`)
- **AMD AI Developer Program account**: [founder to create/confirm]

---

## Founder-only steps (need your login, not something Claude can do)

1. Record the demo video(s) per docs/DEMO_SCRIPT.md.
2. Create/confirm accounts: AWS Builder ID, CALL-E account, lablab.ai account, AMD AI Developer
   Program account (for ACT III specifically).
3. Submit each Devpost/lablab.ai form with the text above.
