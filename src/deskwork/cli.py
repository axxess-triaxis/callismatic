"""Entrypoint: `deskwork run [inbox_dir]`.

Prints nothing for documents that need no action, and a clear, actionable
card for every one that does -- the point of the whole project is that this
output should be short.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from deskwork.agent import build_agent
from deskwork.triage import triage_inbox

URGENCY_MARKERS = {"none": "", "low": "[low]", "medium": "[MEDIUM]", "high": "[HIGH]"}


def _print_report(results):
    needs_action = [r for r in results if r.error is None and r.triage.needs_decision]
    filed = [r for r in results if r.error is None and not r.triage.needs_decision]
    errors = [r for r in results if r.error is not None]

    print(f"Triaged {len(results)} document(s): "
          f"{len(needs_action)} need your attention, {len(filed)} filed silently, "
          f"{len(errors)} unreadable.\n")

    if needs_action:
        print("=" * 60)
        print("NEEDS YOUR DECISION")
        print("=" * 60)
        for r in sorted(needs_action, key=lambda r: r.triage.urgency, reverse=True):
            marker = URGENCY_MARKERS.get(r.triage.urgency, "")
            print(f"\n{marker} {r.file_name}")
            print(f"  Summary: {r.triage.summary}")
            print(f"  Why: {r.triage.decision_reason}")
            print(f"  Suggested action: {r.triage.suggested_action}")
            if r.triage.deadline:
                print(f"  Deadline: {r.triage.deadline}")

    if errors:
        print("\n" + "=" * 60)
        print("COULD NOT READ")
        print("=" * 60)
        for r in errors:
            print(f"  {r.file_name}: {r.error}")

    if filed:
        print("\nFiled silently (no action needed): " + ", ".join(r.file_name for r in filed))


def main() -> None:
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inbox", nargs="?", default="sample_inbox", help="Folder of documents to triage")
    args = parser.parse_args()

    inbox_dir = Path(args.inbox)
    if not inbox_dir.is_dir():
        print(f"No such inbox folder: {inbox_dir}", file=sys.stderr)
        sys.exit(1)

    agent = build_agent()
    results = triage_inbox(agent, inbox_dir)
    _print_report(results)


if __name__ == "__main__":
    main()
