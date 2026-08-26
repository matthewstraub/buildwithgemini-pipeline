"""Unit tests for cadence engine rules and business day calculations."""

from datetime import date
from pipeline.cadence import compute_next_action
from pipeline.holidays import add_business_days, count_business_days_between, is_business_day
from pipeline.models import Application, SourceEnum, StageEnum


def test_business_day_math():
    # 2026-08-21 is Friday, 2026-08-24 is Monday
    fri = date(2026, 8, 21)
    mon = date(2026, 8, 24)
    assert is_business_day(fri)
    assert is_business_day(mon)
    assert count_business_days_between(fri, mon) == 1
    assert add_business_days(fri, 1) == mon


def test_cadence_cold_application_threshold():
    # Applied cold on Aug 3 -> 10 business days later is Aug 17
    app = Application(
        company="Bellwether",
        role="CSM",
        applied_on=date(2026, 8, 3),
        stage=StageEnum.APPLIED,
        stage_changed_on=date(2026, 8, 3),
        source=SourceEnum.COLD,
    )
    # On Aug 10 (5 BD) -> Waiting
    compute_next_action(app, today=date(2026, 8, 10))
    assert "Waiting" in app.next_action

    # On Aug 18 (11 BD) -> Follow-up due
    compute_next_action(app, today=date(2026, 8, 18))
    assert "Draft follow-up ready" in app.next_action


def test_cadence_max_nudges_stale_transition():
    app = Application(
        company="QuietCo",
        role="CSM",
        applied_on=date(2026, 8, 1),
        stage=StageEnum.APPLIED,
        stage_changed_on=date(2026, 8, 1),
        source=SourceEnum.COLD,
        nudge_count=2,  # Already nudged twice
    )
    compute_next_action(app, today=date(2026, 8, 25))
    assert app.stage == StageEnum.STALE
    assert "Marked stale" in app.next_action
