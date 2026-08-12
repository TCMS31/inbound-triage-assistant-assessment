"""The output contract. These models are simultaneously the schema the model
is forced to emit and the schema we trust, so their edges matter."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from triage_backend.schemas import (
    MAX_SUMMARY_CHARS,
    MODEL_CATEGORIES,
    InboundMessage,
    StoredTriageResult,
    TriageResponse,
    TriageResult,
)


def valid(**overrides: object) -> dict:
    payload = {
        "summary": "Seller of a business wants help investing $8M in proceeds.",
        "category": "prospect",
        "priority": "medium",
        "next_action": "Send the intro pack and offer a call.",
    }
    payload.update(overrides)
    return payload


def test_valid_payload_round_trips() -> None:
    assert TriageResult.model_validate(valid()).category == "prospect"


@pytest.mark.parametrize("field", ["summary", "category", "priority", "next_action"])
def test_every_field_is_required(field: str) -> None:
    payload = valid()
    payload.pop(field)
    with pytest.raises(ValidationError):
        TriageResult.model_validate(payload)


@pytest.mark.parametrize("category", ["Prospect", "urgent", "", "needs_review"])
def test_category_rejects_values_outside_the_model_taxonomy(category: str) -> None:
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(category=category))


def test_needs_review_is_not_a_category_a_model_may_emit() -> None:
    """It is the deterministic fallback's value. If a model could emit it, a
    guess would be indistinguishable from an admission of failure."""
    assert "needs_review" not in MODEL_CATEGORIES
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(category="needs_review"))
    assert StoredTriageResult.model_validate(valid(category="needs_review")).category == (
        "needs_review"
    )


@pytest.mark.parametrize("priority", ["HIGH", "urgent", "none"])
def test_priority_rejects_unknown_values(priority: str) -> None:
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(priority=priority))


@pytest.mark.parametrize("blank", ["", "   ", "\n\t"])
def test_blank_free_text_is_rejected(blank: str) -> None:
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(summary=blank))
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(next_action=blank))


def test_runaway_summary_is_rejected_not_stored() -> None:
    """An unbounded string from a model is an unbounded string in the UI and
    in the cache file; the prompt's '<= 20 words' is a preference, not a
    guarantee, so the ceiling is enforced here."""
    with pytest.raises(ValidationError):
        TriageResult.model_validate(valid(summary="x " * MAX_SUMMARY_CHARS))


def test_whitespace_is_collapsed() -> None:
    result = TriageResult.model_validate(valid(summary="  too   many\n\nspaces  "))
    assert result.summary == "too many spaces"


def test_response_defaults_are_a_successful_llm_row() -> None:
    response = TriageResponse(id="inb-001")
    assert (response.source, response.error, response.flags) == ("llm", False, [])


def message(**overrides: str) -> InboundMessage:
    base = {
        "id": "inb-001",
        "received_at": "2025-01-06T09:00:00Z",
        "channel": "email",
        "from_name": "Ada",
        "from_org": "(individual)",
        "subject": "Hi",
        "body": "Body text",
    }
    base.update(overrides)
    return InboundMessage.model_validate(base)


def test_fingerprint_is_stable_for_identical_content() -> None:
    assert message().fingerprint() == message().fingerprint()


@pytest.mark.parametrize(
    "overrides",
    [{"body": "Different"}, {"subject": "Other"}, {"from_name": "Bob"}, {"channel": "linkedin"}],
)
def test_fingerprint_changes_when_triage_relevant_content_changes(overrides: dict) -> None:
    assert message().fingerprint() != message(**overrides).fingerprint()


def test_fingerprint_ignores_fields_that_do_not_affect_triage() -> None:
    assert message().fingerprint() == message(received_at="1999-01-01T00:00:00Z").fingerprint()
