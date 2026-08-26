"""Draft generator for application follow-up emails."""

import os
from pathlib import Path
from typing import Optional
from google import genai

from pipeline.models import Application


DRAFT_PROMPT_TEMPLATE = """
You are drafting a professional, concise, direct follow-up email on behalf of Matt for a job application.

CRITICAL VOICE & STYLE RULES:
- Never use generic filler like "I hope this email finds you well" or "I am writing to express my enthusiasm".
- Keep it under 100 words. Be respectful of their time, crisp, confident, and natural.
- Sound like a high-performing senior professional, not a desperate job seeker.
- Two follow-ups maximum have been sent; this is a clean, low-friction check-in.

Application Details:
- Company: {company}
- Role: {role}
- Stage: {stage}
- Source: {source}
- Referrer: {referrer}
- Last Contact Date: {last_contact_date}
- Last Contact Summary: {last_contact_summary}
- Target Recipient: {recipient}

Thread History / Additional Context:
{thread_context}

Output format:
Subject: <crisp subject line>

<email body>
"""


def generate_followup_draft(
    app: Application,
    thread_context: Optional[str] = None,
    output_dir: Path = Path("out/drafts"),
) -> Path:
    """
    Generates a follow-up email draft using Gemini and saves it to output_dir.
    Returns the Path to the generated draft file.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    recipient = "Hiring Team"
    if app.contacts:
        recipient = f"{app.contacts[0].name} ({app.contacts[0].role.value})"

    if not thread_context:
        # Check if thread history file exists in threads/
        thread_file = Path("threads") / f"{app.slug}.md"
        if thread_file.exists():
            thread_context = thread_file.read_text(encoding="utf-8")
        else:
            thread_context = "No previous thread context recorded."

    api_key = os.getenv("GEMINI_API_KEY")

    if api_key:
        try:
            client = genai.Client()
            prompt = DRAFT_PROMPT_TEMPLATE.format(
                company=app.company,
                role=app.role,
                stage=app.stage.value,
                source=app.source.value,
                referrer=app.referrer or "N/A",
                last_contact_date=app.last_contact.date.isoformat() if app.last_contact else "N/A",
                last_contact_summary=app.last_contact.summary if app.last_contact else "N/A",
                recipient=recipient,
                thread_context=thread_context,
            )
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=prompt,
            )
            draft_text = response.text.strip()
        except Exception as e:
            draft_text = _fallback_draft_template(app, recipient)
    else:
        draft_text = _fallback_draft_template(app, recipient)

    out_file = output_dir / f"{app.slug}-followup.md"
    out_content = f"""# Follow-up Draft: {app.company} ({app.role})

**Date Drafted:** {app.stage_changed_on.isoformat()}  
**Target Recipient:** {recipient}  
**Stage:** `{app.stage.value}`  

---

{draft_text}
"""
    out_file.write_text(out_content, encoding="utf-8")
    return out_file


def _fallback_draft_template(app: Application, recipient: str) -> str:
    """Fallback draft generator when LLM API key is not present."""
    if app.stage == "screen_done":
        return f"""Subject: Following up — {app.company} ({app.role})

Hi {recipient.split(' ')[0]},

Following up on our recent screen for the {app.role} position at {app.company}. I really enjoyed our conversation.

Please let me know if there are any additional details I can provide or if there's an update on next steps with the team.

Best,
Matt"""
    else:
        return f"""Subject: Re: {app.role} application — {app.company}

Hi {recipient.split(' ')[0]},

Checking in on my application for the {app.role} position submitted recently. I remain very interested in {app.company}'s work in this space.

Happy to provide any additional context if helpful. Look forward to hearing from you.

Best,
Matt"""
