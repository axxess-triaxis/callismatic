"""Entrypoint: `callismatic [inbox_dir]` to triage voicemails,
`callismatic correct ...` to record a human correction to a past decision, or
`callismatic digest` to print a summary of what the agent has done recently.

The triage report prints nothing for voicemails that need no action, and a
clear, actionable card for every one that does -- plus a line for every
callback actually placed and every number blocked. The point of the whole
project is that this output should be short.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

from callismatic import reminders, todos
from callismatic.agent import build_agent
from callismatic.corrections import record_correction
from callismatic.digest_report import generate_weekly_digest, send_digest
from callismatic.tools import find_digest_entry, unblock_number
from callismatic.triage import DEFAULT_MAX_CONCURRENCY, triage_inbox, triage_inbox_concurrent

URGENCY_MARKERS = {"none": "", "low": "[low]", "medium": "[MEDIUM]", "high": "[HIGH]"}


def _print_report(results):
    ok = [r for r in results if r.error is None]
    needs_action = [r for r in ok if r.triage.needs_decision]
    callback_decided = [r for r in ok if r.triage.callback_recommended]
    callback_placed = [r for r in callback_decided if r.callback_result is not None and r.callback_result.get("status") != "provider_error"]
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
            if r.callback_result is not None and r.callback_result.get("status") == "provider_error":
                print(f"  Result: FAILED to place -- {r.callback_result.get('error', 'unknown error')}")
            elif r.callback_result is not None:
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


def _run_correct(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="callismatic correct",
        description="Record a human correction to a past triage decision, so the agent stops repeating the same misjudgment for that caller.",
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    unblock_parser = subparsers.add_parser("unblock", help="Remove a number from the blocklist -- it isn't actually scam/spam.")
    unblock_parser.add_argument("phone_number")
    unblock_parser.add_argument("--reason", default="Manually unblocked -- not actually scam/spam.")

    recat_parser = subparsers.add_parser("recategorize", help="Correct a past voicemail's classification.")
    recat_parser.add_argument("file_name", help="The voicemail file name as it appears in outputs/digest.json")
    recat_parser.add_argument("--category", choices=["scam", "spam", "lead", "important", "routine"])
    recat_parser.add_argument("--needs-decision", choices=["true", "false"])
    recat_parser.add_argument("--callback-recommended", choices=["true", "false"])
    recat_parser.add_argument("--block-recommended", choices=["true", "false"])
    recat_parser.add_argument("--reason", default="Manually recategorized.")

    args = parser.parse_args(argv)

    if args.action == "unblock":
        removed = unblock_number(args.phone_number)
        record_correction(
            target=args.phone_number,
            original={"block_recommended": True},
            corrected={"block_recommended": False},
            reason=args.reason,
        )
        note = "was on the blocklist" if removed else "was not on the blocklist -- correction recorded anyway"
        print(f"Unblocked {args.phone_number} ({note}).")
        return

    entry = find_digest_entry(args.file_name)
    if entry is None:
        print(f"No past decision found for {args.file_name} in outputs/digest.json", file=sys.stderr)
        sys.exit(1)

    corrected: dict[str, object] = {}
    if args.category:
        corrected["category"] = args.category
    if args.needs_decision:
        corrected["needs_decision"] = args.needs_decision == "true"
    if args.callback_recommended:
        corrected["callback_recommended"] = args.callback_recommended == "true"
    if args.block_recommended:
        corrected["block_recommended"] = args.block_recommended == "true"
    if not corrected:
        print(
            "Provide at least one of --category/--needs-decision/--callback-recommended/--block-recommended",
            file=sys.stderr,
        )
        sys.exit(1)

    record_correction(target=args.file_name, original=entry["triage"], corrected=corrected, reason=args.reason)
    print(f"Recorded correction for {args.file_name}: {corrected}")


def _run_triage(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inbox", nargs="?", default="sample_voicemails", help="Folder of voicemail recordings to triage")
    parser.add_argument(
        "--no-callbacks",
        action="store_true",
        help="Decide callbacks but don't actually place them via CALL-E (dry run, saves free-call quota)",
    )
    parser.add_argument(
        "--concurrent",
        action="store_true",
        help="Triage every voicemail at once, each with its own freshly spawned sub-agent, instead of one at a time",
    )
    parser.add_argument(
        "--max-concurrency",
        type=int,
        default=DEFAULT_MAX_CONCURRENCY,
        help=f"With --concurrent, how many sub-agents may run at once (default: {DEFAULT_MAX_CONCURRENCY})",
    )
    args = parser.parse_args(argv)

    inbox_dir = Path(args.inbox)
    if not inbox_dir.is_dir():
        print(f"No such inbox folder: {inbox_dir}", file=sys.stderr)
        sys.exit(1)

    started_at = time.monotonic()
    if args.concurrent:
        results = asyncio.run(
            triage_inbox_concurrent(
                inbox_dir, place_callbacks=not args.no_callbacks, max_concurrency=args.max_concurrency
            )
        )
    else:
        agent = build_agent()
        results = triage_inbox(agent, inbox_dir, place_callbacks=not args.no_callbacks)
    elapsed = time.monotonic() - started_at

    _print_report(results)
    print(f"\n({'concurrent' if args.concurrent else 'sequential'} run, {elapsed:.1f}s)")


def _run_digest(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="callismatic digest",
        description="Print a summary of what the agent has done recently -- blocked, called back, needed your attention, filed silently.",
    )
    parser.add_argument("--days", type=int, default=7, help="How many days back to summarize (default: 7)")
    parser.add_argument("--channel", choices=["stdout", "file"], default="stdout")
    args = parser.parse_args(argv)

    text = generate_weekly_digest(days=args.days)
    send_digest(text, channel=args.channel)


def _run_todos(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(prog="callismatic todos", description="List or complete to-do items.")
    subparsers = parser.add_subparsers(dest="action")

    subparsers.add_parser("list", help="List open to-dos (default)")
    complete_parser = subparsers.add_parser("complete", help="Mark a to-do item done")
    complete_parser.add_argument("item_id")

    args = parser.parse_args(argv)

    if args.action == "complete":
        if todos.complete_todo(args.item_id):
            print(f"Completed {args.item_id}")
        else:
            print(f"No open to-do found with id {args.item_id}", file=sys.stderr)
            sys.exit(1)
        return

    items = todos.list_todos()
    if not items:
        print("No open to-dos.")
        return
    for item in items:
        print(f"[{item['id']}] {item['text']}  (from {item['source']})")


def _run_reminders(argv: list[str]) -> None:
    parser = argparse.ArgumentParser(
        prog="callismatic reminders", description="Add a reminder, or send every reminder that's now due."
    )
    subparsers = parser.add_subparsers(dest="action", required=True)

    add_parser = subparsers.add_parser("add", help="Schedule a reminder")
    add_parser.add_argument("text")
    add_parser.add_argument("--due", required=True, help="ISO 8601 timestamp, e.g. 2026-09-15T14:00:00+00:00")
    add_parser.add_argument("--to", help="WhatsApp number to deliver it to (E.164); omit to only print when due")

    subparsers.add_parser("send", help="Send every reminder that's now due")

    args = parser.parse_args(argv)

    if args.action == "add":
        item = reminders.add_reminder(args.text, args.due, to=args.to)
        print(f"Scheduled {item['id']}: \"{item['text']}\" due {item['due_at']}")
        return

    sent = reminders.send_due_reminders()
    print(f"Sent {len(sent)} due reminder(s)." if sent else "No reminders due.")


def main() -> None:
    load_dotenv()
    argv = sys.argv[1:]
    if argv and argv[0] == "correct":
        _run_correct(argv[1:])
    elif argv and argv[0] == "digest":
        _run_digest(argv[1:])
    elif argv and argv[0] == "todos":
        _run_todos(argv[1:])
    elif argv and argv[0] == "reminders":
        _run_reminders(argv[1:])
    else:
        _run_triage(argv)


if __name__ == "__main__":
    main()
