"""Offline rule-based provider — `LLM_PROVIDER=stub`.

This is NOT a model. It is a transparent keyword baseline that lets the app,
the test suite and UI screenshots run end to end with no API key and no spend,
and it doubles as the comparison baseline in `scripts/evaluate.py`: a model
that cannot beat a page of regexes is not earning its cost.

It is never selected by `auto` — you have to ask for it by name — and every
result it produces is tagged `provider:stub` in the response flags, so a
stub-classified row is never mistaken for a model-classified one.
"""

from __future__ import annotations

import re

from triage_backend.classification.base import TriageOutcome, register_provider
from triage_backend.schemas import InboundMessage, TriageResult


def _rx(*words: str) -> re.Pattern[str]:
    return re.compile("|".join(words), re.IGNORECASE)


EXISTING_CLIENT = _rx(
    r"\bexisting client\b",
    r"\bi'?m a client\b",
    r"\bclient here\b",
    r"\bmy account\b",
    r"\bmy portfolio\b",
    r"\bour quarterly\b",
    r"\bmy statement\b",
    r"\bupdated statement\b",
)
VENDOR_PARTNER = _rx(
    r"\bwe sell\b",
    r"\bquick demo\b",
    r"\bour (?:software|platform|product)\b",
    r"\bpartnership\b",
    r"\breferral\b",
    r"\bwhite[- ]?label\b",
    r"\bi run a small ria\b",
)
NOISE = _rx(
    r"\bunsubscribe\b",
    r"\bnewsletter\b",
    r"\bmarket digest\b",
    r"\bautomated\b",
    r"\bexciting opportunity\b",
    r"\brecruit",
    r"\bgreat fit for (?:a|this) role\b",
)
URGENT = _rx(
    r"\bby (?:friday|monday|tomorrow|end of (?:day|week))\b",
    r"\bdeadline\b",
    r"\burgent\b",
    r"\basap\b",
    r"\bnot happy\b",
    r"\bcomplaint\b",
    r"\bfrustrat",
    r"\bright away\b",
)
UNHURRIED = _rx(r"\bno rush\b", r"\bjust exploring\b", r"\bearly in thinking\b", r"\bsome ?day\b")


class StubProvider:
    """Deterministic keyword classifier. Satisfies `LLMProvider`, no network."""

    name = "stub"
    is_model = False

    def triage(self, message: InboundMessage) -> TriageOutcome:
        haystack = f"{message.subject}\n{message.body}"
        category = self._category(haystack)
        return TriageOutcome(
            result=TriageResult(
                summary=self._summary(message),
                category=category,
                priority=self._priority(category, haystack),
                next_action=self._next_action(category),
            ),
            attempts=0,
        )

    @staticmethod
    def _category(haystack: str) -> str:
        if NOISE.search(haystack):
            return "noise_other"
        if EXISTING_CLIENT.search(haystack):
            return "existing_client"
        if VENDOR_PARTNER.search(haystack):
            return "vendor_partner"
        return "prospect"

    @staticmethod
    def _priority(category: str, haystack: str) -> str:
        if category == "noise_other":
            return "low"
        if category == "existing_client" and URGENT.search(haystack):
            return "high"
        if UNHURRIED.search(haystack):
            return "low"
        return "medium"

    @staticmethod
    def _summary(message: InboundMessage) -> str:
        """First sentence of the body, or the subject if there isn't one.

        A rule engine cannot abstract, so it quotes instead of pretending to
        summarise — which is also the honest way to show what the baseline is.
        """
        body = " ".join((message.body or "").split())
        sentence = re.split(r"(?<=[.!?])\s", body)[0] if body else ""
        if len(sentence) > 140:
            sentence = sentence[:137].rstrip() + "..."
        fallback = message.subject.strip() or "No subject and no body."
        return sentence or fallback

    @staticmethod
    def _next_action(category: str) -> str:
        return {
            "existing_client": "Route to the advisor who owns the relationship.",
            "prospect": "Send the standard intro pack and offer an intro call.",
            "vendor_partner": "Forward to operations for a vendor/partner decision.",
            "noise_other": "No action — archive.",
        }[category]


register_provider("stub", StubProvider)
