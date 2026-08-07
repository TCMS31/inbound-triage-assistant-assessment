"""Routing layer — decide what happens to a message and record it.

Stage 3 of 3 (ingestion -> classification -> routing). This is the only place
that knows the *policy*: what to serve from cache, when to skip the model
entirely, and what to return when the model cannot be trusted. Keeping it out
of the HTTP handler is what makes the whole decision table testable without a
web server and without a model.
"""

from __future__ import annotations

import logging

from triage_backend.classification import TriageError, classify, malformed_flags
from triage_backend.routing.cache import ResultCache, get_cache
from triage_backend.schemas import InboundMessage, StoredTriageResult, TriageResponse

logger = logging.getLogger(__name__)

__all__ = ["ResultCache", "get_cache", "triage"]

HEURISTIC_RESULT = StoredTriageResult(
    summary="Low-signal or unparseable message — skipped LLM classification.",
    category="noise_other",
    priority="low",
    next_action="Manual review — message body is empty, near-empty, or garbled.",
)

FALLBACK_RESULT = StoredTriageResult(
    summary="Model output failed validation twice — needs human review.",
    category="needs_review",
    priority="medium",
    next_action="Manual review — LLM did not return valid structured output.",
)

VALIDATION_FAILED_FLAG = "validation_failed_twice"


def triage(message: InboundMessage, *, cache: ResultCache | None = None) -> TriageResponse:
    """Run one message through the pipeline and return what the UI should show.

    Never raises for a model failure: a failed row is a failed row, not a
    failed request, so one bad message cannot take the rest of the list down.
    """
    store = cache or get_cache()

    cached = store.get(message)
    if cached is not None:
        # Serve it, but say so — an unmarked cache hit is indistinguishable
        # from a fresh classification, which makes a stale result invisible.
        return cached.model_copy(
            update={"source": "cache", "flags": [*cached.flags, f"cached:{cached.source}"]}
        )

    flags = malformed_flags(message)
    if flags:
        response = TriageResponse(
            id=message.id, source="heuristic", flags=flags, result=HEURISTIC_RESULT
        )
        store.put(message, response)
        return response

    try:
        outcome = classify(message)
    except TriageError as exc:
        logger.warning("triage failed for %s: %s", message.id, exc)
        # Deliberately not cached and deliberately HTTP 200 at the route: the
        # *row* failed, not the endpoint. The UI renders an inline error and a
        # Retry button, and the next attempt really does retry.
        return TriageResponse(id=message.id, source="llm", error=True, error_message=str(exc))

    provider_flags = [f"provider:{outcome.provider}"] if outcome.provider else []
    if outcome.attempts > 1:
        provider_flags.append(f"attempts:{outcome.attempts}")

    if outcome.result is None:
        response = TriageResponse(
            id=message.id,
            source="fallback",
            flags=[VALIDATION_FAILED_FLAG, *provider_flags],
            result=FALLBACK_RESULT,
        )
    else:
        response = TriageResponse(
            id=message.id,
            source="llm" if outcome.is_model else "baseline",
            flags=provider_flags,
            result=StoredTriageResult.model_validate(outcome.result.model_dump()),
        )

    store.put(message, response)
    return response
