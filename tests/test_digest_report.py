import json
from datetime import datetime, timedelta, timezone

from callismatic.digest_report import generate_weekly_digest, send_digest


def _iso(dt: datetime) -> str:
    return dt.isoformat()


def test_generate_weekly_digest_counts_categories(tmp_path, monkeypatch):
    now = datetime(2026, 9, 20, tzinfo=timezone.utc)
    digest_path = tmp_path / "digest.json"
    blocklist_path = tmp_path / "blocklist.json"

    digest_path.write_text(
        json.dumps(
            [
                {
                    "file": "important_client.wav",
                    "triaged_at": _iso(now - timedelta(days=1)),
                    "triage": {"needs_decision": True, "summary": "Client dispute."},
                },
                {
                    "file": "lead.wav",
                    "triaged_at": _iso(now - timedelta(days=2)),
                    "triage": {"callback_recommended": True},
                },
                {
                    "file": "newsletter.wav",
                    "triaged_at": _iso(now - timedelta(days=3)),
                    "triage": {},
                },
                {
                    "file": "too_old.wav",
                    "triaged_at": _iso(now - timedelta(days=30)),
                    "triage": {"needs_decision": True},
                },
            ]
        ),
        encoding="utf-8",
    )
    blocklist_path.write_text(
        json.dumps(
            [
                {
                    "phone_number": "+15550001111",
                    "reason": "Gift-card scam.",
                    "blocked_at": _iso(now - timedelta(days=1)),
                }
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr("callismatic.digest_report.DIGEST_PATH", digest_path)
    monkeypatch.setattr("callismatic.digest_report.BLOCKLIST_PATH", blocklist_path)

    text = generate_weekly_digest(days=7, now=now)

    assert "Triaged: 3 voicemail(s)/message(s)" in text
    assert "1 needed your decision" in text
    assert "1 recommended for callback" in text
    assert "1 number(s) blocked" in text
    assert "1 filed silently" in text
    assert "too_old.wav" not in text


def test_generate_weekly_digest_empty_state(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.digest_report.DIGEST_PATH", tmp_path / "digest.json")
    monkeypatch.setattr("callismatic.digest_report.BLOCKLIST_PATH", tmp_path / "blocklist.json")

    text = generate_weekly_digest(days=7)

    assert "Triaged: 0 voicemail(s)/message(s)" in text


def test_send_digest_file_writes_to_path(tmp_path):
    target = tmp_path / "report.txt"
    send_digest("hello digest", channel="file", path=target)
    assert target.read_text(encoding="utf-8") == "hello digest"


def test_send_digest_stdout_prints(capsys):
    send_digest("hello digest", channel="stdout")
    assert "hello digest" in capsys.readouterr().out
