# Devpost submission text — Deskwork Agent

Draft for the project description field. Trim/adjust once the live Bedrock run is
confirmed and any real numbers (run time, doc count) can be quoted instead of estimated.

---

## Inspiration

Running a small consultancy or freelance practice means a steady drip of paperwork:
invoices, contracts, vendor forms, newsletters, "just checking in" emails. Almost none
of it needs a decision right now — but finding the handful that do means reading
everything. That's the exact shape of work the hackathon brief describes: routine,
repetitive, and only occasionally judgment-heavy. So instead of building a chatbot you
have to ask questions, we built an agent that reads the pile for you and only speaks up
when something actually needs a human call.

## What it does

Deskwork Agent triages a folder of documents — PDFs or text, invoices, contracts, forms,
correspondence — one at a time. For each document it:

- Extracts the text, including from PDFs with no real text layer at all (a genuine
  failure mode we hit building this: a browser "Print to PDF" export can contain
  vector-drawn glyphs with no Unicode mapping, so both `pypdf` and poppler's own
  `pdftotext` return empty. The fallback rasterizes the page and OCRs it instead of
  failing.)
- Reasons about it with two tools: `get_today` (so "due in 3 weeks" vs. "overdue" is
  computed against the real date, not guessed by the model) and `check_past_decisions`
  (so a vendor or invoice already handled in an earlier run isn't flagged again).
- Returns a forced structured decision — document type, plain-language summary, the
  concrete facts worth remembering, and a `needs_decision` boolean with a reason,
  suggested action, deadline, and urgency when it's true.

Everything gets logged. Only the documents that need a decision get surfaced to the
human — that's the whole point.

## How we built it

Python, the Strands Agents SDK for the agent loop and tool-calling, Amazon Bedrock
(Claude) as the model provider, `pypdf` for text-layer extraction, PyMuPDF + Tesseract
for the OCR fallback, and Pydantic for the structured-output schema that Strands
enforces on every response.

## Challenges we ran into

The OCR fallback wasn't a design decision made up front — it came from actually hitting
a PDF that both mainstream text-extraction paths returned empty on, then diagnosing why
(the images embedded in the PDF were tiny logos, not the content; the real content was
vector text with no Unicode mapping). That's the difference between "looks done" and
"actually handles the input you'll get in real life."

## What's next

A folder-watcher daemon instead of a batch run, email/drive ingestion instead of a local
folder, and a lighter model tier for documents that are obviously low-stakes (a
newsletter doesn't need the same model call as a contract).

## Track

**Professional Agents** — this targets exactly the audience the track names: solo
consultants, freelancers, and small-business owners doing repetitive, judgment-heavy
paperwork triage themselves because they don't have staff to delegate it to.
