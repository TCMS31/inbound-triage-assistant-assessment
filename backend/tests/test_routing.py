"""The pipeline's decision table: cache, heuristic, model, fallback, error.

This is the policy layer. None of it needs a web server or a model to test,
which is the point of keeping it out of the route handler.
"""

from __future__ import annotations

import pytest

from triage_backend import routing
from triage_backend.classification.base import TriageError, TriageOutcome
from triage_backend.routing.cache import ResultCache
from triage_backend.schemas import InboundMessage, TriageResult

GOOD = TriageResult(
    summary="Business seller wants help investing sale proceeds.",
    category="prospect",
    priority="medium",
    next_action="Send the intro pack.",
)


@pytest.fixture
def fake_classify(monkeypatch: pytest.MonkeyPatch):
    def install(outcome_or_error: object) -> list[str]:
        seen: list[str] = []

        def classify(message: InboundMessage) -> TriageOutcome:
            seen.append(message.id)
            if isinstance(outcome_or_error, Exception):
                raise outcome_or_error
            return outcome_or_error

        monkeypatch.setattr(routing, "classify", classify)
        return seen

    return install


def test_a_good_classification_is_returned_and_cached(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    seen = fake_classify(TriageOutcome(result=GOOD, provider="anthropic"))

    first = routing.triage(message, cache=cache)
    assert first.source == "llm"
    assert first.error is False
    assert first.result is not None
    assert first.result.category == "prospect"
    assert "provider:anthropic" in first.flags

    second = routing.triage(message, cache=cache)
    assert second.source == "cache"
    assert "cached:llm" in second.flags
    assert seen == [message.id], "a cache hit must not call the model again"


def test_a_cache_hit_is_labelled_so_a_stale_result_is_visible(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    """Serving a cached row as `source: llm` makes a cached result and a fresh
    one indistinguishable in the UI."""
    fake_classify(TriageOutcome(result=GOOD, provider="anthropic"))
    routing.triage(message, cache=cache)
    assert routing.triage(message, cache=cache).source == "cache"


def test_a_malformed_message_never_reaches_the_model(
    cache: ResultCache, malformed_message: InboundMessage, fake_classify
) -> None:
    seen = fake_classify(TriageOutcome(result=GOOD, provider="anthropic"))

    response = routing.triage(malformed_message, cache=cache)

    assert seen == [], "malformed input must short-circuit before any spend"
    assert response.source == "heuristic"
    assert response.flags == ["empty_or_near_empty_body"]
    assert response.result is not None
    assert (response.result.category, response.result.priority) == ("noise_other", "low")


def test_a_heuristic_result_is_cached_too(
    cache: ResultCache, malformed_message: InboundMessage
) -> None:
    routing.triage(malformed_message, cache=cache)
    assert routing.triage(malformed_message, cache=cache).source == "cache"


def test_validation_failure_falls_back_to_needs_review(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    fake_classify(TriageOutcome(result=None, attempts=2, provider="openai"))

    response = routing.triage(message, cache=cache)

    assert response.source == "fallback"
    assert response.error is False
    assert response.result is not None
    assert response.result.category == "needs_review"
    assert "validation_failed_twice" in response.flags
    assert "attempts:2" in response.flags


def test_an_api_failure_is_a_failed_row_not_a_failed_request(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    fake_classify(TriageError("429 rate limit exceeded"))

    response = routing.triage(message, cache=cache)

    assert response.error is True
    assert response.result is None
    assert "429" in (response.error_message or "")


def test_a_failed_row_is_not_cached_so_retry_really_retries(
    cache: ResultCache, message: InboundMessage, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[str] = []

    def flaky(msg: InboundMessage) -> TriageOutcome:
        calls.append(msg.id)
        if len(calls) == 1:
            raise TriageError("transient")
        return TriageOutcome(result=GOOD, provider="anthropic")

    monkeypatch.setattr(routing, "classify", flaky)

    assert routing.triage(message, cache=cache).error is True
    retried = routing.triage(message, cache=cache)
    assert retried.error is False
    assert len(calls) == 2


def test_a_retry_after_success_costs_nothing(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    seen = fake_classify(TriageOutcome(result=GOOD, provider="anthropic"))
    for _ in range(5):
        routing.triage(message, cache=cache)
    assert len(seen) == 1


def test_an_offline_baseline_result_is_never_labelled_as_a_model_result(
    cache: ResultCache, message: InboundMessage, fake_classify
) -> None:
    """`source: llm` on a rule-engine result would be a lie the UI repeats."""
    fake_classify(TriageOutcome(result=GOOD, provider="stub", is_model=False))
    response = routing.triage(message, cache=cache)
    assert response.source == "baseline"
    assert "provider:stub" in response.flags
