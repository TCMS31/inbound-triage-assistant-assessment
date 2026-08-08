"""The triage prompt and the provider-native output schemas.

Both schemas are generated from `MODEL_CATEGORIES` / `PRIORITIES` in
schemas.py, which are also what `TriageResult` validates against. The prompt
text lists the same tuples. There is therefore exactly one place to add a
category, which is the claim `RATIONALE.md` makes about extending the taxonomy.

`prompts/triage_prompt.md` mirrors this file for review; the code is the
source of truth.
"""

from __future__ import annotations

from triage_backend.schemas import (
    MAX_SUMMARY_CHARS,
    MODEL_CATEGORIES,
    PRIORITIES,
    InboundMessage,
)

CATEGORY_GUIDE: dict[str, str] = {
    "prospect": "a new business inquiry from someone who is not yet a client.",
    "existing_client": (
        "a request, question, or issue from someone who is already a client "
        "(they say so, or reference an account/portfolio/advisor relationship)."
    ),
    "vendor_partner": (
        "a vendor pitch, sales outreach, or referral/partnership proposal aimed at the firm."
    ),
    "noise_other": (
        "recruiting outreach, newsletters, automated mail, or anything that is not a "
        "real business message for the firm."
    ),
}

PRIORITY_GUIDE: dict[str, str] = {
    "high": (
        "an existing client who is upset, blocked, or has a hard deadline; "
        "or a clearly high-value warm prospect."
    ),
    "medium": "a normal request or inquiry with no urgent deadline.",
    "low": "cold outreach, recruiting, newsletters, or anything low-stakes/low-signal.",
}

# Fail loudly at import time if someone adds an enum value without a definition
# rather than silently shipping a prompt that omits it.
assert set(CATEGORY_GUIDE) == set(MODEL_CATEGORIES), "CATEGORY_GUIDE is out of sync"
assert set(PRIORITY_GUIDE) == set(PRIORITIES), "PRIORITY_GUIDE is out of sync"


def _bullets(guide: dict[str, str], order: tuple[str, ...]) -> str:
    return "\n".join(f"- {key}: {guide[key]}" for key in order)


SYSTEM_PROMPT = f"""\
You are the inbound-triage assistant for Northwind Advisors, an alternative-investment \
and family-office advisory firm. You read one inbound message at a time (email, \
web-form, LinkedIn, or voicemail transcript) and classify it so a human can route it \
quickly.

Categories (choose exactly one):
{_bullets(CATEGORY_GUIDE, MODEL_CATEGORIES)}

Priority (choose exactly one), based on urgency and stakes, independent of category:
{_bullets(PRIORITY_GUIDE, PRIORITIES)}

Notes on the data: from_org may contain the sentinel values "(individual)" or \
"(unknown)" — these are not real organization names, treat the sender as an \
individual with an unknown/no firm. Some fields may be empty; use whatever \
signal is present in subject/body.

Ground every field in the message text you are given. Do not invent account \
numbers, names, amounts, or history that is not present in the message; if the \
message does not say, do not assert it.

Return your result as a JSON object with exactly four fields:
  summary     — a single line, at most ~20 words (hard limit {MAX_SUMMARY_CHARS} \
characters), not just restating the subject.
  category    — one of: {", ".join(MODEL_CATEGORIES)}.
  priority    — one of: {", ".join(PRIORITIES)}.
  next_action — a short, concrete instruction (e.g. "Route to advisor on \
Dana Whitfield's account", "Send standard fee schedule + minimum", \
"No action — archive as newsletter").

If you are given a tool to call, call it exactly once with your result."""


_PROPERTIES: dict[str, dict] = {
    "summary": {
        "type": "string",
        "description": "One-line summary of the message, at most ~20 words.",
    },
    "category": {"type": "string", "enum": list(MODEL_CATEGORIES)},
    "priority": {"type": "string", "enum": list(PRIORITIES)},
    "next_action": {
        "type": "string",
        "description": "A short, concrete suggested next action.",
    },
}

_REQUIRED = ["summary", "category", "priority", "next_action"]

TRIAGE_TOOL: dict = {
    "name": "emit_triage",
    "description": "Emit the structured triage result for one inbound message.",
    "input_schema": {
        "type": "object",
        "properties": _PROPERTIES,
        "required": _REQUIRED,
    },
}

OPENAI_TRIAGE_SCHEMA: dict = {
    "name": "triage_result",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": _PROPERTIES,
        "required": _REQUIRED,
        "additionalProperties": False,
    },
}


def build_user_prompt(message: InboundMessage) -> str:
    """One message as plain key/value lines.

    Not the raw JSON record: it is cheaper, and it stops the model reading
    stray JSON syntax inside a garbled body as structure.
    """
    return (
        f"channel: {message.channel}\n"
        f"from_name: {message.from_name or '(empty)'}\n"
        f"from_org: {message.from_org or '(empty)'}\n"
        f"subject: {message.subject or '(empty)'}\n"
        f"body: {message.body or '(empty)'}"
    )
