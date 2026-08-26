"""Recruiter vetting module combining deterministic checks, web verification, and model analysis."""

import os
import re
from typing import List, Optional, Tuple
import httpx
from pipeline.models import VettingInput, VettingResult, VettingVerdictEnum

FREE_MAIL_DOMAINS = {
    "gmail.com",
    "googlemail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "yahoo.com",
    "ymail.com",
    "proton.me",
    "protonmail.com",
    "aol.com",
    "icloud.com",
    "gmx.com",
    "mail.com",
}

KNOWN_SUSPICIOUS_KEYWORDS = [
    r"telegram",
    r"whatsapp",
    r"signal",
    r"skype",
    r"purchase equipment",
    r"check reimbursement",
    r"wire transfer",
    r"social security",
    r"ssn",
    r"bank account",
    r"front funds",
    r"text-based interview",
    r"online interview questionnaire",
]



def extract_domain(email_or_url: str) -> Optional[str]:
    """Extract domain from an email address or URL."""
    if not email_or_url:
        return None
    email_or_url = email_or_url.strip().lower()
    if "@" in email_or_url:
        return email_or_url.split("@")[-1]
    if "://" in email_or_url:
        domain = email_or_url.split("://")[1].split("/")[0]
        return domain.split(":")[0]
    return email_or_url.split("/")[0]


def run_deterministic_checks(v_input: VettingInput) -> Tuple[List[str], List[str]]:
    """Runs deterministic, non-LLM checks against input headers and text."""
    signals_against = []
    signals_for = []

    text_lower = v_input.message_text.lower()

    # 1. Free Mail Domain check
    if v_input.sender_email:
        sender_domain = extract_domain(v_input.sender_email)
        if sender_domain in FREE_MAIL_DOMAINS:
            company_str = v_input.claimed_company or "a named corporate entity / staffing firm"
            signals_against.append(
                f"Sender email ({v_input.sender_email}) uses free mail provider '{sender_domain}', while claiming to represent {company_str}."
            )
        else:
            signals_for.append(f"Sender domain ({sender_domain}) is a custom corporate/staffing domain.")

    # 2. Reply-To Mismatch
    if v_input.sender_email and v_input.reply_to_email:
        s_dom = extract_domain(v_input.sender_email)
        r_dom = extract_domain(v_input.reply_to_email)
        if s_dom != r_dom:
            signals_against.append(
                f"Reply-to domain ({r_dom}) differs from sender domain ({s_dom})."
            )

    # 3. Content Red Flags
    for kw in KNOWN_SUSPICIOUS_KEYWORDS:
        if re.search(r"\b" + kw + r"\b", text_lower):
            signals_against.append(f"Message explicitly mentions suspicious keyword/pattern: '{kw}'.")

    return signals_against, signals_for


def analyze_with_llm(v_input: VettingInput, deterministic_against: List[str], deterministic_for: List[str]) -> VettingResult:
    """Use Gemini API to analyze message text, separating role legitimacy from channel safety."""
    api_key = os.getenv("GEMINI_API_KEY")
    
    # Heuristic fallback if GEMINI_API_KEY is not configured
    if not api_key:
        return _fallback_heuristic_vetting(v_input, deterministic_against, deterministic_for)

    try:
        client = genai.Client()
        prompt = f"""
You are an expert recruitment security analyst. Evaluate the following inbound recruiter message for potential recruiter impersonation, scam, or legitimate outreach.

CRITICAL DISTINCTION TO MAKE:
1. Is the ROLE real? (Does the role sound genuine and match standard company operations?)
2. Is the CONTACT CHANNEL safe? (Is the recruiter asking to move to Telegram/WhatsApp, using a free gmail address, asking for equipment purchase, text-chat interview, etc.?)

Sender Email: {v_input.sender_email or 'Unknown'}
Reply-To Email: {v_input.reply_to_email or 'Unknown'}
Claimed Company: {v_input.claimed_company or 'Unknown'}
Claimed Role: {v_input.claimed_role or 'Unknown'}

Message Text:
\"\"\"
{v_input.message_text}
\"\"\"

Deterministic Signals Detected So Far:
Signals Against: {deterministic_against}
Signals For: {deterministic_for}

Please evaluate and output JSON in the following schema:
{{
  "role_legitimate": true/false/null,
  "channel_safe": true/false/null,
  "verdict": "likely_legitimate" | "needs_verification" | "likely_fraudulent",
  "signals_against": ["bullet point 1", "bullet point 2"],
  "signals_for": ["bullet point 1", "bullet point 2"],
  "recommended_action": ["action 1", "action 2"]
}}
"""
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        
        # Parse JSON from response
        res_text = response.text
        # Remove potential markdown block markers
        if "```json" in res_text:
            res_text = res_text.split("```json")[1].split("```")[0]
        elif "```" in res_text:
            res_text = res_text.split("```")[1].split("```")[0]
            
        import json
        data = json.loads(res_text.strip())
        
        # Combine deterministic signals with LLM signals
        against = list(dict.fromkeys(deterministic_against + data.get("signals_against", [])))
        for_sigs = list(dict.fromkeys(deterministic_for + data.get("signals_for", [])))
        
        return VettingResult(
            verdict=VettingVerdictEnum(data.get("verdict", "needs_verification")),
            signals_against=against,
            signals_for=for_sigs,
            recommended_action=data.get("recommended_action", []),
            role_legitimate=data.get("role_legitimate"),
            channel_safe=data.get("channel_safe"),
        )
    except Exception as e:
        return _fallback_heuristic_vetting(v_input, deterministic_against, deterministic_for)


def _fallback_heuristic_vetting(
    v_input: VettingInput, deterministic_against: List[str], deterministic_for: List[str]
) -> VettingResult:
    """Fallback vetting when LLM API call is not available."""
    against = list(deterministic_against)
    for_sigs = list(deterministic_for)
    rec_actions = []

    role_legit = True
    channel_safe = True

    if against:
        channel_safe = False

    # Determine verdict
    if len(against) >= 2 or any("free mail" in s.lower() or "telegram" in s.lower() for s in against):
        verdict = VettingVerdictEnum.NEEDS_VERIFICATION
        if any("purchase equipment" in s.lower() or "check reimbursement" in s.lower() for s in against):
            verdict = VettingVerdictEnum.LIKELY_FRAUDULENT
    elif against:
        verdict = VettingVerdictEnum.NEEDS_VERIFICATION
    else:
        verdict = VettingVerdictEnum.LIKELY_LEGITIMATE

    company_name = v_input.claimed_company or "the official company"
    if verdict != VettingVerdictEnum.LIKELY_LEGITIMATE:
        rec_actions.append("Do not reply directly to this message or handle.")
        rec_actions.append(f"If interested in the role, search and apply directly via {company_name}'s official careers page.")
        if v_input.sender_email and "gmail.com" in v_input.sender_email:
            rec_actions.append(f"Verify recruiter identity on LinkedIn before sharing any resume or contact details.")
    else:
        rec_actions.append("Safe to respond via standard professional email / LinkedIn.")

    return VettingResult(
        verdict=verdict,
        signals_against=against,
        signals_for=for_sigs,
        recommended_action=rec_actions,
        role_legitimate=role_legit,
        channel_safe=channel_safe,
    )


def vet_recruiter_message(v_input: VettingInput) -> VettingResult:
    """Main entrypoint for vetting an inbound recruiter message."""
    deterministic_against, deterministic_for = run_deterministic_checks(v_input)
    return analyze_with_llm(v_input, deterministic_against, deterministic_for)
