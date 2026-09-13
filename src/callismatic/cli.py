"""Entrypoint: `callismatic run [inbox_dir]`.

Prints nothing for voicemails that need no action, and a clear, actionable
card for every one that does -- plus a line for every callback actually
placed and every number blocked. The point of the whole project is that
this output should be short.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from callismatic.agent import build_agent
from callismatic.triage import triage_inbox

URGENCY_MARKERS = {"none": "", "low": "[low]", "medium": "[MEDIUM]", "high": "[HIGH]"}


def _print_report(results):
    ok = [r for r in results if r.error is None]
    needs_action = [r for r in ok if r.triage.needs_decision]
    callback_decided = [r for r in ok if r.triage.callback_recommended]
    callback_placed = [r for r in callback_decided if r.callback_result is not None]
    blocked = [r for r in ok if r.triage.block_recommended]
    filed = [
        r for r in ok
        if not r.triage.needs_decision and not r.triage.block_recommended and not r.triage.callback_recommended
    ]
    errors = [r for r in results if r.error is not None]

    print(
        f"Triaged {len(results)} voicemail(s): "
        f"{len(needs_action)} need your decision, {len(callback_decided)} recommended for callback "
        f"({len(callback_placed)} actually placed via CALL-E), "
        f"{len(blocked)} blocked, {len(filed)} filed silently, {len(errors)} unreadable.\n"
    )

    if needs_action:
        print("=" * 60)
        print("NEEDS YOUR DECISION")
        print("=" * 60)
        for r in sorted(needs_action, key=lambda r: r.triage.urgency, reverse=True):
            marker = URGENCY_MARKERS.get(r.triage.urgency, "")
            print(f"\n{marker} {r.file_name} (caller: {r.caller_number})")
            print(f"  Summary: {r.triage.summary}")
            print(f"  Why: {r.triage.decision_reason}")
            print(f"  Suggested action: {r.triage.suggested_action}")

    if callback_decided:
        print("\n" + "=" * 60)
        print("CALLBACK RECOMMENDED")
        print("=" * 60)
        for r in callback_decided:
            print(f"\n{r.file_name} (caller: {r.caller_number})")
            print(f"  Task: {r.triage.callback_task}")
            if r.callback_result is not None:
                print(f"  Result: placed via CALL-E -- status {r.callback_result.get('status', 'unknown')}")
            else:
                print("  Result: NOT placed (dry run / --no-callbacks, or unknown caller number)")

    if blocked:
        print("\nBlocked: " + ", ".join(f"{r.caller_number} ({r.file_name})" for r in blocked))

    if errors:
        print("\n" + "=" * 60)
        print("COULD NOT TRANSCRIBE")
        print("=" * 60)
        for r in errors:
            print(f"  {r.file_name}: {r.error}")

    if filed:
        print("\nFiled silently (no action needed): " + ", ".join(r.file_name for r in filed))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inbox", nargs="?", default="sample_voicemails", help="Folder of voicemail recordings to triage")
    parser.add_argument(
        "--no-callbacks",
        action="store_true",
        help="Decide callbacks but don't actually place them via CALL-E (dry run, saves free-call quota)",
    )
    args = parser.parse_args()

    inbox_dir = Path(args.inbox)
    if not inbox_dir.is_dir():
        print(f"No such inbox folder: {inbox_dir}", file=sys.stderr)
        sys.exit(1)

    agent = build_agent()
    results = triage_inbox(agent, inbox_dir, place_callbacks=not args.no_callbacks)
    _print_report(results)


if __name__ == "__main__":
    main()
