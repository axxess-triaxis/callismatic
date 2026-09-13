# Demo video script / shot list

Hard limit: **5 minutes** (Agents for Humans). Target ~3:30–4:00 so there's no
risk of running over. A separate, shorter (~3 min) cut is needed for Call-E —
see the note at the bottom. Fill in the [TIMING] brackets once recorded
against the real, live Bedrock + AssemblyAI + CALL-E run — don't guess run
time or outcomes in the final cut.

---

### 1. Cold open — the problem (0:00–0:30)

Screen: a phone's "Block all unknown numbers" setting toggled on, then a
voicemail inbox with several unheard messages.

Voiceover: "Scam calls get bad enough that people just block every unknown
number. That also blocks the client, the delivery driver, the interviewer,
the doctor's office — because those are unknown numbers too, until someone
actually listens to the voicemail. Most people never do. Deskwork Agent
does, for you."

### 2. What it is (0:30–1:00)

Screen: README architecture diagram (mermaid), rendered.

Voiceover: "It's built on the Strands Agents SDK, running on Amazon Bedrock,
with AssemblyAI transcribing every voicemail and CALL-E placing real
callbacks. Point it at your voicemail inbox — it transcribes each one,
decides what kind of caller it is, and acts: block, call back, or surface it
to you."

### 3. Live run (1:00–3:00) — the core of the demo

Screen: terminal, `deskwork sample_voicemails` running live, full output
visible.

Narrate over it as it runs:
- "Four voicemails: a gift-card scam script, a new business lead, a routine
  appointment confirmation, and an important client matter."
- When output appears: point at the scam call getting blocked (`check_number_intel`
  flagging the gift-card marker), the lead and appointment-confirmation
  calls getting an actual callback placed via CALL-E, and the client matter
  surfaced for a real decision.
- Call out the CALL-E result specifically: show the real call's transcript/
  outcome returned by `client.calls.create_and_wait`.

### 4. Why not Truecaller (3:00–3:30)

Screen: `check_number_intel` docstring / README section.

Voiceover: "We didn't fake a Truecaller integration — there's no public API
for that. Instead this scans the actual transcript for real scam-script
markers: gift-card requests, urgency pressure, agency impersonation. It's a
signal the agent weighs, not a black box."

### 5. Why this track (3:30–3:50)

Voiceover: "This is a Professional Agent — for anyone who's had to choose
between constant scam-call disruption and missing the calls that actually
matter. The bar for 'good' here is: real threats get blocked, real
opportunities get handled or surfaced, and everything else stays quiet."

### 6. Close (3:50–4:00)

Screen: GitHub repo README.

Voiceover: "Code, README, and architecture diagram are all in the repo — MIT
licensed. Thanks for watching."

---

## Recording checklist

- [ ] Record the live run against `sample_voicemails/` with real Bedrock,
      AssemblyAI, and CALL-E calls — no mocked or pre-recorded output
      pretending to be live.
- [ ] Confirm on screen which voicemails actually get blocked / called back /
      surfaced — don't narrate a result that doesn't match what's on screen.
- [ ] Use only the synthetic sample voicemails on camera — nothing from a
      real personal or business voicemail inbox.
- [ ] The real CALL-E call must go to a number the founder controls or has
      explicit permission to call.
- [ ] Keep total runtime under 5:00 including any intro/outro.

## Call-E's separate demo video

Call-E requires its own ~3 minute video (YouTube/Vimeo, public), focused
specifically on the callback piece: show `callback.py`'s real call being
placed and completed, not the whole triage pipeline. Reuse the section-3
footage above, trimmed.
