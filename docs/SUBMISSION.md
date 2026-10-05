# Devpost/lablab.ai submission text — Callismatic

Ready-to-paste copy for the hackathon forms below. The core Devpost "Story" text (Inspiration
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

Callismatic is a **personal and phone secretary AI agent** — not just a filter. It triages a
folder of voicemail recordings (or an incoming SMS/WhatsApp message) one at a time, then
carries that same judgment into the follow-up work a human assistant would normally do. For
each message it:

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
  the human with full context — then turns the outcome into meeting notes, a to-do, a synced
  Google Sheets CRM row, and Google Calendar availability/booking, with reminders delivered
  back over WhatsApp.

### How we built it

Python, the Strands Agents SDK for the agent loop and tool-calling, running on **Amazon
Bedrock and Amazon Nova** as model providers, AssemblyAI for voicemail transcription, the
CALL-E SDK for placing real outbound callbacks, and Pydantic for the structured-output schema
Strands enforces on every response. Around that core: a Google Sheets CRM sync and Google
Calendar availability/booking (both via a shared service-account credential), a Twilio-backed
SMS/verify number for a second, independent carrier-intelligence signal, and a WhatsApp
Business Cloud API receiver/sender running the same triage pipeline on incoming messages.

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

Since this draft: a hosted dashboard + API deployed live on AWS Lambda
([awpfsufk4dofdncv6cgqsaifwy0kvolm.lambda-url.us-east-1.on.aws](https://awpfsufk4dofdncv6cgqsaifwy0kvolm.lambda-url.us-east-1.on.aws/)),
a credential-free demo of real triage output on [Hugging Face
Spaces](https://huggingface.co/spaces/SKS1213/callismatic), a Google Sheets CRM sync verified
against a real spreadsheet, Google Calendar availability/booking verified against a real
calendar, and a WhatsApp receiver/sender verified directly against Meta's Cloud API — though
Meta actually auto-forwarding real incoming messages to it still needs Business Verification
(a separate identity/document review process), not yet done. A Twilio Lookup
carrier-intelligence signal is wired and tested but currently blocked by Twilio's own
trial-account quota. Still ahead: real inbound telephony (Twilio recording webhooks) instead
of a local sample folder, and a folder-watcher/background-service mode instead of a batch run.

### Roadmap: AMD + Kubernetes

A Kubernetes-orchestrated fine-tuning pipeline on AMD GPU infrastructure is planned next, to
train a proprietary, sandboxed model on Callismatic's own accumulated triage decisions and
human corrections — turning the Personal Secretary & Phone Manager algorithm from a prompted
agent into a purpose-trained, horizontally scalable one. Design is written up in
[`docs/AMD_ACT3_ARCHITECTURE.md`](AMD_ACT3_ARCHITECTURE.md) and targets the separate AMD
Developer Hackathon: ACT III submission below; as of this writing no AMD compute has been
provisioned and no training has run.

### Track

**Professional Agents** — the audience is exactly the person forced into "block all unknown
numbers" as their only defense against call volume: a solo consultant, freelancer, or
small-business owner without staff to screen calls for them.

### Built With

python, strands-agents, amazon-bedrock, amazon-nova, assemblyai, calle, pydantic, boto3,
google-sheets-api, google-calendar-api, twilio, whatsapp-business-cloud-api, aws-lambda,
docker, gradio, huggingface-spaces

---

## Agents for Humans — additional fields — **SUBMITTED** (founder-confirmed, 2026-09-14)

- **Try it out (repo)**: https://github.com/axxess-triaxis/callismatic
- **License**: MIT (in repo)
- **AWS Builder ID**: official@triaxisventures.com

---

## Call-E — additional fields — **SUBMITTED** (founder-confirmed, 2026-09-14)

- **Pull request URL**: https://github.com/CALLE-AI/awesome-phone-call-agents/pull/527
- **CALL-E account email**: [founder to fill in]
- **Demo video**: ~3 min, focused specifically on `apps/python/voicemail-triage-callback`
  (the extracted callback piece), not the whole pipeline — see docs/DEMO_SCRIPT.md's note at
  the bottom.

---

## AssemblyAI Voice Agent Hackathon (lablab.ai) — different form, different fields

Confirmed directly from the actual submission page (lablab.ai/event/assemblyai-voice-agent-hackathon):

- **Project title**: Callismatic
- **Short description** (one line): A personal and phone secretary AI agent that listens to
  the voicemails you'd never check, decides what needs you, and quietly handles or blocks the
  rest — built on AssemblyAI, Strands/Bedrock/Nova, and CALL-E.
- **Long description**: reuse the Inspiration + What it does sections above.
- **Technology & category tags**: AssemblyAI, Amazon Bedrock, Amazon Nova, Strands Agents SDK,
  CALL-E, Google Sheets, Google Calendar, Twilio, WhatsApp Business, Python
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
  a live Bedrock call running under the Lambda's own IAM role. A second, credential-free demo
  of the same real triage output is also live on [Hugging Face
  Spaces](https://huggingface.co/spaces/SKS1213/callismatic) for judges who'd rather not need
  an API key to look.

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

## SerpApi India Hackathon 2026 — submit by Oct 10, 2026, 23:59 IST

Rules confirmed from serpapi.github.io/serpapi-india-hackathon-2026 (rules.html):
- existing projects are accepted when SerpApi makes a *material contribution* and the
  relevant work can be identified and reviewed;
- a pre-existing project must be disclosed;
- the demo must be under 3 minutes and show the project running locally;
- exposing API keys or personal data in public materials is grounds for disqualification.

- **Track**: AI Agents.
- **Project name**: Callismatic.
- **Pre-existing project disclosure** (required): *Callismatic existed before this
  hackathon. The SerpApi integration is new work built for it, in PR #1 (caller
  verification during triage) and PR #2 (pre-meeting briefs, places near a meeting, MCP
  tools, demo samples). Both are listed in the README's "SerpApi web intelligence" section.*
- **One-line description**: A personal-secretary AI agent that screens unknown callers.
  SerpApi lets it check what the web says about a caller before deciding whether to block
  them, call them back, or wake you up, then briefs you before your meetings.
- **Project description**:

  Callismatic listens to the voicemails and messages you'd never check, decides which ones
  need you, and quietly handles or blocks the rest. Until now it judged a stranger only by what
  they *said* and their phone line type. With SerpApi it checks the outside world, the way a
  sharp human assistant would:

  - **Is the caller who they say they are?** When a caller claims an organisation, the
    agent's `check_web_intel` tool searches Google (via SerpApi) for the number and the
    organisation. The result is one of three signals:
    - **corroborated**: the number is published on that organisation's own site;
    - **contradicted**: the number appears on scam-report pages, or the organisation
      doesn't exist;
    - **inconclusive**, still carrying the facts found: the organisation's official site and
      whether the caller's number appears on it.
    That evidence feeds the block / callback / escalate decision and is recorded with it.
  - **What should I know before this meeting?** For upcoming calendar meetings, Callismatic
    identifies the organisation (from attendee email domains) and sends a WhatsApp brief 30
    minutes before: who they are (Google knowledge panel) and their latest news (Google
    News).
  - **Where should we meet?** It finds well-rated places near a meeting's location (Google
    Maps), with ratings, addresses and hours.

  **Safety.** Search results are treated as untrusted. They are truncated and stripped of
  links, and the agent is told to ignore any instructions in them. Web evidence can never
  block a caller on its own. Searches are cached and capped per day to stay within the free
  plan.
- **SerpApi engines used**: Google Search (organic results, knowledge graph), Google News,
  Google Maps.
- **Public repository**: https://github.com/axxess-triaxis/callismatic
- **AI tools disclosure** (required): Claude Code (Anthropic) was used to design and write the
  SerpApi integration, tests and documentation, under the founder's direction and review.
  Callismatic's runtime agent uses the Strands Agents SDK. The demo runs on Groq's free tier
  (OpenAI gpt-oss-120b, falling back to gpt-oss-20b); Amazon Bedrock (Nova Pro) and Nebius
  Token Factory (NVIDIA Nemotron) remain supported as opt-in fallbacks.

### Demo video script (under 3 minutes, recorded running locally)

Use only the sample voicemails: they feature fictional people and fictional `+1555…`
numbers. Never show `.env`, a terminal with `SERPAPI_API_KEY`, or a real person's number.

**Before recording (off camera), in PowerShell from the repo folder:**

```powershell
# GROQ_API_KEY and SERPAPI_API_KEY must be in .env (free tiers, no card). No AWS login needed.
mkdir ..\serpapi-demo -Force; copy sample_voicemails\trai_* ..\serpapi-demo; copy sample_voicemails\zomato_* ..\serpapi-demo
python -m callismatic.cli ..\serpapi-demo --no-callbacks   # dry run: warms the search cache
```

`python -m callismatic.cli` is the same program as the `callismatic` command; use it if
`callismatic` isn't on your PATH. On Groq (gpt-oss-120b, free tier) the two voicemails took
65–108 s across test runs, including transcription. Run them one at a time (no `--concurrent`): the free
tier allows 8,000 tokens a minute, and parallel runs hit that limit and slow down. Wait a
minute after the dry run before recording.
`--no-callbacks` keeps the run from placing a real phone call to the fictional numbers.

1. **0:00–0:20, the problem.** Unknown calls are mostly scams, so people block them, and then
   miss real clients, deliveries and leads. Callismatic answers them for you.
2. **0:20–1:20, caller verification.** Run `python -m callismatic.cli ..\serpapi-demo --no-callbacks` and show:
   - the **TRAI disconnection scam** blocked. Point out `web_evidence`: TRAI is real, its
     official site is trai.gov.in, and the caller's number appears nowhere on it. The block
     itself rests on the transcript's scam markers; the web evidence supports it, never
     decides it alone;
   - the **Zomato partnerships lead** *not* blocked: the web confirms Zomato is a real
     company (official site zomato.com), so it becomes a lead, escalated to you with a
     suggested callback (or an automatic callback, depending on the run).
3. **1:20–1:40, the evidence itself.** Run
   `python -m callismatic.cli web-intel --phone +15550007777 --company TRAI` to show the raw web evidence
   and the untrusted-content header.
4. **1:40–2:20, briefs.** Run `python -m callismatic.cli brief --company Zomato` to show the knowledge-panel
   summary and the latest Google News headlines. Mention that with Google Calendar it does
   this automatically 30 minutes before each meeting, over WhatsApp.
5. **2:20–2:45, places.** Run `python -m callismatic.cli places "quiet cafe" --near "Koramangala, Bengaluru"`.
6. **2:45–3:00, close.** Three SerpApi engines feed one agent's real decisions. It's open
   source, and the repo link is in the description.

Credit budget for recording: about 10 searches, and re-runs within 24 h are served from the
local cache.

---

## Founder-only steps (need your login, not something Claude can do)

1. ~~Record the demo video(s) per docs/DEMO_SCRIPT.md.~~ Done.
2. ~~Submit Agents for Humans and Call-E.~~ **Both submitted 2026-09-14.**
3. Still open: AssemblyAI Voice Agent Hackathon (lablab.ai) submission, and AMD Developer
   Hackathon: ACT III (deadline Oct 18, 2026) — needs an AMD AI Developer Program account and
   AMD compute credit approval before any training work can start.
4. **SerpApi India Hackathon 2026, due Oct 10, 23:59 IST:**
   - create a SerpApi account (free plan) and put `SERPAPI_API_KEY` in the local, git-ignored
     `.env`;
   - record the demo video above;
   - submit at serpapi.github.io/serpapi-india-hackathon-2026/submit.html (sign in with
     GitHub). The form asks for personal details, the pre-existing-project disclosure and the
     AI-tools disclosure.
