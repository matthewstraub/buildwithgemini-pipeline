"""Cadence Engine for computing application next actions and stale status."""

from datetime import date
from typing import Optional
from pipeline.holidays import count_business_days_between
from pipeline.models import Application, SourceEnum, StageEnum


def compute_next_action(app: Application, today: Optional[date] = None) -> Application:
    """
    Computes `next_action` and updates `stage` to `stale` if follow-up limits are exceeded.
    Returns the updated Application object.
    """
    if today is None:
        today = date.today()

    # Terminal or passive stages require no computed follow-up
    if app.stage in (
        StageEnum.ACCEPTED,
        StageEnum.REJECTED,
        StageEnum.WITHDRAWN,
        StageEnum.STALE,
        StageEnum.RESEARCHING,
    ):
        app.next_action = None
        return app

    # Reference date is latest of stage_changed_on or last_contact date
    ref_date = app.stage_changed_on
    if app.last_contact and app.last_contact.date > ref_date:
        ref_date = app.last_contact.date

    elapsed_bd = count_business_days_between(ref_date, today)

    threshold_bd = None
    action_description = None

    if app.stage == StageEnum.APPLIED:
        if app.source == SourceEnum.COLD:
            threshold_bd = 10
            action_description = f"{elapsed_bd} business days since applied cold. Draft follow-up ready."
        elif app.source == SourceEnum.WARM_INTRO:
            threshold_bd = 7
            action_description = f"{elapsed_bd} business days since warm intro application. Draft follow-up ready."
        elif app.source == SourceEnum.REFERRAL:
            threshold_bd = 5
            ref_name = app.referrer or "referrer"
            action_description = f"{elapsed_bd} business days since referral. Nudge {ref_name} (not company)."
        elif app.source == SourceEnum.RECRUITER:
            threshold_bd = 4
            action_description = f"{elapsed_bd} business days since recruiter outreach. Draft follow-up ready."
        else:
            threshold_bd = 10
            action_description = f"{elapsed_bd} business days since applied. Draft follow-up ready."

    elif app.stage == StageEnum.SCREEN_DONE:
        threshold_bd = 5
        action_description = f"Screen completed {elapsed_bd} business days ago, no next step. Draft follow-up ready."

    elif app.stage == StageEnum.ONSITE_DONE:
        threshold_bd = 5
        action_description = f"Onsite completed {elapsed_bd} business days ago, no decision. Draft follow-up ready."

    elif app.stage in (StageEnum.SCREEN_SCHEDULED, StageEnum.ONSITE_SCHEDULED):
        # Recruiter quiet mid process
        threshold_bd = 4
        action_description = f"Recruiter quiet mid-process for {elapsed_bd} business days. Draft check-in ready."

    elif app.stage == StageEnum.OFFER:
        threshold_bd = 1
        action_description = "Outstanding offer. Daily reminder to check decision deadline."

    if threshold_bd is not None and elapsed_bd >= threshold_bd:
        if app.nudge_count >= 2:
            app.stage = StageEnum.STALE
            app.next_action = "Marked stale (exceeded maximum 2 follow-up nudges)."
        else:
            app.next_action = action_description
    else:
        # Not yet due for follow up
        if threshold_bd is not None:
            remaining = threshold_bd - elapsed_bd
            app.next_action = f"Waiting ({remaining} business days until follow-up threshold)."
        else:
            app.next_action = None

    return app
