"""Unit tests for recruiter vetting checks."""

from pathlib import Path
from pipeline.models import VettingInput, VettingVerdictEnum
from pipeline.vetting import run_deterministic_checks, vet_recruiter_message


def test_deterministic_freemail_and_telegram_detection():
    v_in = VettingInput(
        sender_email="recruiter@gmail.com",
        reply_to_email="jobs@scamdomain.com",
        claimed_company="Sterling Staffing Group",
        message_text="Urgent role! Contact director on Telegram for interview and equipment purchase check.",
    )
    against, for_sigs = run_deterministic_checks(v_in)
    assert any("gmail.com" in s for s in against)
    assert any("scamdomain.com" in s for s in against)
    assert any("telegram" in s for s in against)


def test_vetting_staffing_impersonation_fixture():
    fixture_path = Path("tests/fixtures/vetting_samples/staffing_impersonation.txt")
    text = fixture_path.read_text(encoding="utf-8")
    v_in = VettingInput(
        sender_email="sterling.talent.desk@gmail.com",
        reply_to_email="interview-desk@sterlingstaffing-careers.example.com",
        claimed_company="Sterling Staffing Group",
        message_text=text,
    )
    res = vet_recruiter_message(v_in)
    assert res.verdict in (VettingVerdictEnum.LIKELY_FRAUDULENT, VettingVerdictEnum.NEEDS_VERIFICATION)
    assert res.channel_safe is False
