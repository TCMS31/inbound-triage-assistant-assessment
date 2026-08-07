"""Classification layer — turn one inbound message into a triage result.

Stage 2 of 3 (ingestion -> classification -> routing). It owns the prompt, the
provider abstraction and the malformed-input heuristic. It knows nothing about
HTTP, caching or how a result is stored.
"""

from __future__ import annotations

import logging

from triage_backend.classification import providers as _providers  # noqa: F401 - registers
from triage_backend.classification.base import (
    LLMProvider,
    StructuredOutputError,
    TriageError,
    TriageOutcome,
    available_providers,
    build_provider,
    register_provider,
)
from triage_backend.classification.heuristics import is_malformed, malformed_flags
from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage

logger = logging.getLogger(__name__)

#: Order tried when `LLM_PROVIDER=auto`. The stub is deliberately absent — an
#: offline baseline must never be selected by accident.
AUTO_ORDER: tuple[tuple[str, str], ...] = (
    ("anthropic", "anthropic_api_key"),
    ("openai", "openai_api_key"),
)

__all__ = [
    "LLMProvider",
    "StructuredOutputError",
    "TriageError",
    "TriageOutcome",
    "available_providers",
    "classify",
    "is_malformed",
    "malformed_flags",
    "register_provider",
    "resolve_provider",
]


def resolve_provider() -> LLMProvider:
    """Pick a provider from `LLM_PROVIDER` and the keys that are actually set.

    Raises `TriageError` — never a bare exception — so a misconfiguration
    surfaces as a per-row error with a readable message rather than a 500.
    """
    settings = get_settings()
    requested = settings.llm_provider.lower().strip()

    if requested and requested != "auto":
        key_attr = dict(AUTO_ORDER).get(requested)
        if key_attr and not getattr(settings, key_attr):
            raise TriageError(f"LLM_PROVIDER={requested} but {key_attr.upper()} is not set")
        return build_provider(requested)

    for name, key_attr in AUTO_ORDER:
        if getattr(settings, key_attr):
            return build_provider(name)

    raise TriageError(
        "No LLM API key configured — set ANTHROPIC_API_KEY or OPENAI_API_KEY in "
        "backend/.env, or set LLM_PROVIDER=stub to run offline with the rule-based "
        "baseline."
    )


def classify(message: InboundMessage) -> TriageOutcome:
    """Classify one message with the configured provider.

    Raises `TriageError` on any API/config failure; the routing layer turns
    that into a per-row error response.
    """
    settings = get_settings()
    if settings.triage_force_error_id and message.id == settings.triage_force_error_id:
        raise TriageError(
            f"simulated failure (TRIAGE_FORCE_ERROR_ID={settings.triage_force_error_id})"
        )

    provider = resolve_provider()
    logger.info("classifying %s with provider=%s", message.id, provider.name)
    outcome = provider.triage(message)
    outcome.provider = provider.name
    outcome.is_model = getattr(provider, "is_model", True)
    return outcome
