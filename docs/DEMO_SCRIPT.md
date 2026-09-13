# Demo video script / shot list

Hard limit: **5 minutes**. Target ~3:30–4:00 so there's no risk of running over.
Fill in the [TIMING] brackets once recorded against the real, live Bedrock run —
don't guess run time in the final cut.

---

### 1. Cold open — the problem (0:00–0:30)

Screen: a cluttered folder of documents (use `sample_inbox/` — 5 files).

Voiceover: "If you run a small consultancy, every week brings a pile of paperwork —
invoices, contracts, vendor forms, newsletters. Almost none of it needs you to actually
do anything. Finding the couple that do means reading all of it. That's Deskwork Agent's
job instead."

### 2. What it is (0:30–1:00)

Screen: README architecture diagram (mermaid), rendered.

Voiceover: "It's built on the Strands Agents SDK, running on Amazon Bedrock. Point it at
a folder — it reads each document, including ones that turn out to be surprisingly hard
to read, reasons about whether a human needs to act, and stays quiet unless the answer
is yes."

### 3. Live run (1:00–2:30) — the core of the demo

Screen: terminal, `deskwork sample_inbox` running live, full output visible.

Narrate over it as it runs:
- "Five documents: an overdue invoice, a paid invoice, a contract waiting on a
  signature, an incomplete vendor form, and a newsletter."
- When output appears: point at the two flagged items (contract + overdue invoice +
  incomplete form — whichever the live run actually flags) and the three filed
  silently.
- Call out one tool call specifically if the trace is visible: "notice it called
  `get_today` to work out the invoice was actually overdue, not just due soon."

### 4. The harder case — OCR fallback (2:30–3:15)

Screen: a second run against a PDF with no text layer (a "Print to PDF" style export —
use a synthetic redacted example, not a real personal document, for anything recorded).

Voiceover: "Not every PDF has real extractable text. This one doesn't — a common export
artifact. Instead of failing, it rasterizes the page and runs OCR, then reasons over
that instead."

### 5. Why this track (3:15–3:45)

Screen: README track section, or just talk to camera/voiceover.

Voiceover: "This is a Professional Agent — for the freelancer or small-business owner
who doesn't have staff to triage their own paperwork. The bar for 'good' here isn't a
clever answer to a question you asked — it's silence, except for the handful of times
it actually matters."

### 6. Close (3:45–4:00)

Screen: GitHub repo README.

Voiceover: "Code, README, and architecture diagram are all in the repo — MIT licensed.
Thanks for watching."

---

## Recording checklist

- [ ] Record the live run against `sample_inbox/` with real Bedrock calls — no mocked
      or pre-recorded output pretending to be live.
- [ ] Confirm on screen which two (or however many) documents actually get flagged —
      don't narrate a result that doesn't match what's on screen.
- [ ] Use only synthetic/redacted documents on camera — nothing from the developer's
      real inbox.
- [ ] Keep total runtime under 5:00 including any intro/outro.
