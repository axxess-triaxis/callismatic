import json

from callismatic.corrections import find_corrections, record_correction
from callismatic.tools import check_corrections, find_digest_entry, unblock_number


def test_record_and_find_correction(tmp_path, monkeypatch):
    path = tmp_path / "corrections.json"
    monkeypatch.setattr("callismatic.corrections.CORRECTIONS_PATH", path)

    record_correction(
        target="+15550001111",
        original={"block_recommended": True},
        corrected={"block_recommended": False},
        reason="Not actually a scam -- verified caller.",
    )

    matches = find_corrections("+15550001111")
    assert len(matches) == 1
    assert matches[0]["corrected"]["block_recommended"] is False


def test_find_corrections_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.corrections.CORRECTIONS_PATH", tmp_path / "corrections.json")
    assert find_corrections("+19998887777") == []


def test_check_corrections_tool_reports_match(tmp_path, monkeypatch):
    path = tmp_path / "corrections.json"
    monkeypatch.setattr("callismatic.corrections.CORRECTIONS_PATH", path)

    record_correction(
        target="+15550001111",
        original={"category": "scam"},
        corrected={"category": "lead"},
        reason="Verified real business.",
    )

    report = check_corrections("+15550001111")
    assert "ground truth" in report.lower()
    assert "lead" in report


def test_check_corrections_tool_no_match(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.corrections.CORRECTIONS_PATH", tmp_path / "corrections.json")
    report = check_corrections("+10000000000")
    assert "no human corrections" in report.lower()


def test_unblock_number_removes_matching_entry(tmp_path, monkeypatch):
    blocklist_path = tmp_path / "blocklist.json"
    blocklist_path.write_text(
        json.dumps([{"phone_number": "+15550001111", "reason": "scam", "blocked_at": "x"}]),
        encoding="utf-8",
    )
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", blocklist_path)

    removed = unblock_number("+15550001111")

    assert removed is True
    assert json.loads(blocklist_path.read_text(encoding="utf-8")) == []


def test_unblock_number_missing_returns_false(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", tmp_path / "blocklist.json")
    assert unblock_number("+15550009999") is False


def test_find_digest_entry_returns_latest_match(tmp_path, monkeypatch):
    digest_path = tmp_path / "digest.json"
    digest_path.write_text(
        json.dumps(
            [
                {"file": "a.wav", "triaged_at": "t1", "triage": {"category": "spam"}},
                {"file": "a.wav", "triaged_at": "t2", "triage": {"category": "scam"}},
            ]
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", digest_path)

    entry = find_digest_entry("a.wav")

    assert entry["triaged_at"] == "t2"


def test_find_digest_entry_missing_file_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr("callismatic.tools.DIGEST_PATH", tmp_path / "digest.json")
    assert find_digest_entry("nope.wav") is None
