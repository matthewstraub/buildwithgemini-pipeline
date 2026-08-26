"""Digest and summary generation for ntfy push notifications and reports."""

import os
from pathlib import Path
from typing import List, Tuple
import httpx

from pipeline.cadence import compute_next_action
from pipeline.models import Application, StageEnum


def build_daily_digest(apps: List[Application]) -> Tuple[str, List[Application]]:
    """Builds a concise daily digest text of applications needing attention."""
    attention_apps = []
    lines = []

    for app in apps:
        app = compute_next_action(app)
        if app.next_action and "Draft" in app.next_action or "nudge" in str(app.next_action).lower():
            attention_apps.append(app)

    if not attention_apps:
        return "0 applications need attention today. Pipeline is up to date.", []

    lines.append(f"{len(attention_apps)} application{'s' if len(attention_apps) > 1 else ''} need attention today\n")

    for app in attention_apps:
        lines.append(f"• {app.company}: {app.next_action}")

    lines.append("\nReview drafts in out/drafts/")
    digest_text = "\n".join(lines)
    return digest_text, attention_apps


def build_monday_summary(apps: List[Application]) -> str:
    """Builds a comprehensive Monday morning summary report."""
    by_stage = {}
    for stage in StageEnum:
        by_stage[stage.value] = []

    for app in apps:
        app = compute_next_action(app)
        by_stage[app.stage.value].append(app)

    lines = ["# Monday Pipeline Summary\n"]

    active_stages = [
        StageEnum.APPLIED,
        StageEnum.SCREEN_SCHEDULED,
        StageEnum.SCREEN_DONE,
        StageEnum.ONSITE_SCHEDULED,
        StageEnum.ONSITE_DONE,
        StageEnum.OFFER,
    ]

    lines.append("## Active Pipeline")
    active_count = 0
    for st in active_stages:
        st_apps = by_stage[st.value]
        if st_apps:
            lines.append(f"\n### `{st.value}` ({len(st_apps)})")
            for a in st_apps:
                active_count += 1
                lines.append(f"- **{a.company}** — {a.role} (Last contact: {a.last_contact.date if a.last_contact else 'N/A'})")

    if active_count == 0:
        lines.append("No active applications currently in flight.")

    lines.append("\n## Needing Attention This Week")
    attn_count = 0
    for app in apps:
        if app.next_action and ("Draft" in app.next_action or "nudge" in str(app.next_action).lower()):
            attn_count += 1
            lines.append(f"- **{app.company}**: {app.next_action}")
    if attn_count == 0:
        lines.append("No immediate nudges due.")

    lines.append("\n## Stale / Inactive")
    stale_apps = by_stage[StageEnum.STALE.value] + by_stage[StageEnum.REJECTED.value] + by_stage[StageEnum.WITHDRAWN.value]
    if stale_apps:
        for a in stale_apps:
            lines.append(f"- **{a.company}** ({a.role}) — `{a.stage.value}`")
    else:
        lines.append("None")

    return "\n".join(lines)


def send_ntfy_notification(topic: str, message: str, title: str = "Pipeline Daily Digest") -> bool:
    """Send ntfy notification if ntfy topic or URL is configured."""
    ntfy_url = os.getenv("NTFY_URL") or f"https://ntfy.sh/{topic}"
    try:
        response = httpx.post(
            ntfy_url,
            content=message.encode("utf-8"),
            headers={"Title": title},
            timeout=5.0,
        )
        return response.status_code == 200
    except Exception:
        return False
