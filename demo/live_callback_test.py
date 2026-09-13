"""One-off tool: runs the real pipeline (AssemblyAI -> Strands/Bedrock -> CALL-E)
against a single sample voicemail, but places the resulting callback to a
target phone number given on the command line instead of the fake number
embedded in the sample's filename -- useful for testing the real CALL-E
integration against a number you actually control.

AssemblyAI's role here is transcribing the voicemail that *triggers* the
call, not the live call itself: CALL-E's own call result only exposes
transcript_turns (text), no recording or audio, so there is no way to run
AssemblyAI over the live call's audio -- that's a real platform limitation,
not an oversight in this script.

Usage:
    python demo/live_callback_test.py sample_voicemails/package_delivery_+15550005555.wav --to +15551234567
"""

from __future__ import annotations

import argparse
import json

from dotenv import load_dotenv

from callismatic.agent import build_agent
from callismatic.callback import place_callback
from callismatic.schema import CallTriage
from callismatic.voicemails import transcribe_voicemail


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sample", help="Path to a sample voicemail audio file")
    parser.add_argument("--to", required=True, help="Real phone number (E.164) to place the callback to")
    args = parser.parse_args()

    print(f"Transcribing {args.sample} via AssemblyAI...")
    transcript = transcribe_voicemail(args.sample)
    print("Transcript:", transcript)

    print("\nReasoning with Strands agent (Bedrock)...")
    agent = build_agent()
    response = agent(
        f"Triage this voicemail.\n\nFile name: {args.sample}\n\nTranscript:\n{transcript}",
        structured_output_model=CallTriage,
    )
    triage: CallTriage = response.structured_output
    print("Category:", triage.category)
    print("Needs decision:", triage.needs_decision)
    print("Callback recommended:", triage.callback_recommended)
    print("Callback task:", triage.callback_task)

    if not triage.callback_recommended or not triage.callback_task:
        print("\nAgent did not recommend a callback for this voicemail -- not placing a call.")
        return

    print(f"\nPlacing real CALL-E call to {args.to}...")
    result = place_callback(triage.callback_task, args.to)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
