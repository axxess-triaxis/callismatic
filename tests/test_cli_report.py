"""The triage report shows what SerpApi contributed, so it is visible without opening the digest."""

from callismatic.cli import _print_report
from callismatic.schema import CallTriage
from callismatic.triage import TriageResult


def result(file_name, caller, **triage):
    base = dict(category="routine", summary="s", key_facts={}, needs_decision=False)
    return TriageResult(file_name=file_name, caller_number=caller, triage=CallTriage(**{**base, **triage}))


def test_report_shows_web_evidence_for_decisions_and_blocks(capsys):
    _print_report([
        result("lead.wav", "+15550008888", category="lead", needs_decision=True, decision_reason="r",
               suggested_action="Call back", urgency="low",
               web_evidence="INCONCLUSIVE: Zomato is real (official site zomato.com) but the number is not on it."),
        result("scam.wav", "+15550007777", category="scam", block_recommended=True,
               web_evidence="INCONCLUSIVE: TRAI is real (official site trai.gov.in) but the number is not on it."),
    ])
    out = capsys.readouterr().out
    assert "  Web evidence (SerpApi): INCONCLUSIVE: Zomato is real" in out
    assert "  +15550007777: Web evidence (SerpApi): INCONCLUSIVE: TRAI is real" in out


def test_report_prints_no_web_line_when_the_agent_did_not_search(capsys):
    _print_report([result("appt.wav", "+15550003333", needs_decision=True, decision_reason="r", suggested_action="a",
                          urgency="low")])
    assert "Web evidence" not in capsys.readouterr().out
