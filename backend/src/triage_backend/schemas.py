"""Pydantic models — these double as the LLM structured-output contract."""

from __future__ import annotations

import hashlib
import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ModelCategory = Literal["prospect", "existing_client", "vendor_partner", "noise_other"]
"""The only categories the LLM is allowed to emit. The prompt, the Anthropic
tool schema and the OpenAI JSON schema are all generated from this tuple, so
prompt and validator cannot drift apart."""

MODEL_CATEGORIES: tuple[str, ...] = ("prospect", "existing_client", "vendor_partner", "noise_other")

Category = Literal["prospect", "existing_client", "vendor_partner", "noise_other", "needs_review"]
"""What may appear in a stored/served result. `needs_review` is deliberately
NOT in `ModelCategory`: it is only ever written by the deterministic fallback
in the routing layer when structured output fails validation twice, so a
model cannot label its own guess "needs review" and have it pass."""

Priority = Literal["high", "medium", "low"]

PRIORITIES: tuple[str, ...] = ("high", "medium", "low")

# Hard ceiling on free-text fields coming back from a model. The prompt asks
# for "<= 20 words"; that is a preference, not a guarantee, and an unbounded
# string from a model is an unbounded string in the UI and in the cache file.
MAX_SUMMARY_CHARS = 400
MAX_NEXT_ACTION_CHARS = 400

_WHITESPACE = re.compile(r"\s+")


def _clean_text(value: str, *, field: str, limit: int) -> str:
    collapsed = _WHITESPACE.sub(" ", value).strip()
    if not collapsed:
        raise ValueError(f"{field} must not be empty")
    if len(collapsed) > limit:
        raise ValueError(f"{field} must be at most {limit} characters, got {len(collapsed)}")
    return collapsed


class InboundMessage(BaseModel):
    id: str
    received_at: str
    channel: str
    from_name: str
    from_org: str
    subject: str
    body: str

    def fingerprint(self) -> str:
        """Stable hash of the fields that affect triage.

        The result cache is keyed on id *and* this fingerprint, so editing a
        message's body invalidates its cached triage instead of silently
        serving a result computed from different text.
        """
        payload = "␟".join([self.channel, self.from_name, self.from_org, self.subject, self.body])
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


class TriageResult(BaseModel):
    """The exact shape the model is forced to emit, and what its output is
    validated against server-side. One object, both jobs — no drift."""

    summary: str = Field(description="One-line summary of the message, <= 20 words")
    category: ModelCategory
    priority: Priority
    next_action: str = Field(description="A short, concrete suggested next action")

    @field_validator("summary")
    @classmethod
    def _check_summary(cls, value: str) -> str:
        return _clean_text(value, field="summary", limit=MAX_SUMMARY_CHARS)

    @field_validator("next_action")
    @classmethod
    def _check_next_action(cls, value: str) -> str:
        return _clean_text(value, field="next_action", limit=MAX_NEXT_ACTION_CHARS)


class StoredTriageResult(TriageResult):
    """A result as served/stored. Widens `category` to include `needs_review`,
    which only the deterministic fallback may set."""

    category: Category  # type: ignore[assignment]


TriageSource = Literal["cache", "llm", "baseline", "heuristic", "fallback"]
"""Where a served result came from. `baseline` is the offline rule provider —
never a model, and deliberately impossible to confuse with one."""


class TriageResponse(BaseModel):
    """What the API returns — a superset of the result that also carries the
    source/error/flag metadata the UI needs to render cached, malformed,
    fallback and error states distinctly."""

    id: str
    result: StoredTriageResult | None = None
    source: TriageSource = "llm"
    flags: list[str] = Field(default_factory=list)
    error: bool = False
    error_message: str | None = None
