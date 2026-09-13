from pathlib import Path

from deskwork.triage import caller_number_from_filename


def test_extracts_phone_number_from_filename():
    assert caller_number_from_filename(Path("scam_gift_card_+15550001111.wav")) == "+15550001111"


def test_missing_phone_number_returns_unknown():
    assert caller_number_from_filename(Path("no_number_here.wav")) == "unknown"
