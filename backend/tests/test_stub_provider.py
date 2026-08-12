"""The offline rule baseline.

It exists so the app, the suite and the screenshots run with no API key, and
so `scripts/evaluate.py` has something to measure the model against. It is not
a model and is never selected implicitly — see test_provider_resolution.
"""

from __future__ import annotations

import pytest

from triage_backend.classification.providers.stub_provider import StubProvider
from triage_backend.schemas import InboundMessage, TriageResult


def make(subject: str, body: str, name: str = "Sam Cho") -> InboundMessage:
    return InboundMessage.model_validate(
        {
            "id": "inb-x",
            "received_at": "2025-01-06T09:00:00Z",
            "channel": "email",
            "from_name": name,
            "from_org": "(individual)",
            "subject": subject,
            "body": body,
        }
    )


@pytest.mark.parametrize(
    ("subject", "body", "expected"),
    [
        ("Need updated statement by Friday", "I'm an existing client.", "existing_client"),
        ("Portfolio analytics - quick demo?", "We sell portfolio software.", "vendor_partner"),
        ("Exciting opportunity", "You'd be a great fit for this role.", "noise_other"),
        ("Your Monday market digest", "MARKETS ... unsubscribe", "noise_other"),
        ("Wealth planning", "I sold my business and have proceeds to invest.", "prospect"),
    ],
)
def test_categories(subject: str, body: str, expected: str) -> None:
    result = StubProvider().triage(make(subject, body)).result
    assert result is not None
    assert result.category == expected


@pytest.mark.parametrize(
    ("subject", "body", "expected"),
    [
        ("Statement by Friday", "I'm an existing client and need it by Friday.", "high"),
        ("Quarterly review", "Existing client here, my account needs a review.", "medium"),
        ("Just exploring options", "No rush at all - I'm early in thinking about it.", "low"),
        ("Newsletter", "unsubscribe", "low"),
    ],
)
def test_priorities(subject: str, body: str, expected: str) -> None:
    result = StubProvider().triage(make(subject, body)).result
    assert result is not None
    assert result.priority == expected


def test_output_always_satisfies_the_same_contract_as_a_model() -> None:
    result = StubProvider().triage(make("", "")).result
    assert isinstance(result, TriageResult)


def test_it_is_deterministic() -> None:
    message = make("Following up", "Just following up on our conversation.")
    first = StubProvider().triage(message).result
    second = StubProvider().triage(message).result
    assert first == second


def test_it_reports_zero_model_calls() -> None:
    assert StubProvider().triage(make("Hi", "Hello there, a real body.")).attempts == 0
