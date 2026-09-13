import json

from callismatic.tools import block_number, check_number_intel


def test_check_number_intel_flags_gift_card_scam():
    report = check_number_intel(
        "Please purchase a five hundred dollar Google Play gift card and call back with the code."
    )
    assert "gift-card" in report.lower()


def test_check_number_intel_flags_government_impersonation():
    report = check_number_intel(
        "This is an urgent notice from the Federal Fraud Prevention Department."
    )
    assert "government/agency impersonation" in report.lower()


def test_check_number_intel_clean_transcript():
    report = check_number_intel("Hi, just confirming your dentist appointment tomorrow at 2:30pm.")
    assert "no scam-script markers" in report.lower()


def test_block_number_persists_entry(tmp_path, monkeypatch):
    blocklist_path = tmp_path / "blocklist.json"
    monkeypatch.setattr("callismatic.tools.BLOCKLIST_PATH", blocklist_path)

    block_number("+15550001111", "Gift-card scam script detected.")

    entries = json.loads(blocklist_path.read_text(encoding="utf-8"))
    assert entries[0]["phone_number"] == "+15550001111"
    assert entries[0]["reason"] == "Gift-card scam script detected."
