"""The provider seam.

Adding a model vendor means writing one class with a `triage()` method and
calling `register_provider("name", Factory)`. Nothing outside this package —
not the routes, not the cache, not the UI — learns which vendor answered.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from triage_backend.schemas import InboundMessage, TriageResult


class StructuredOutputError(ValueError):
    """The call succeeded but the payload was not the structure we asked for.

    Distinct from `TriageError`: this is recoverable with a corrective retry,
    an API failure is not.
    """


class TriageError(Exception):
    """The LLM call itself failed — network, auth, rate limit, bad config.

    Always surfaced to the caller as a per-row error, never a 500.
    """


@dataclass
class TriageOutcome:
    """Result of one classification attempt."""

    result: TriageResult | None
    """`None` only when structured output failed validation on every attempt —
    the routing layer applies the deterministic fallback in that case."""

    attempts: int = 1
    """How many model calls it took. Surfaced so retry cost is observable."""

    is_model: bool = True
    """Whether a real model produced this. See `LLMProvider.is_model`."""

    provider: str = ""
    """Name of the provider that produced this, recorded in the response flags
    so a stub- or fallback-sourced row is never mistaken for a model call."""

    validation_errors: list[str] = field(default_factory=list)
    """Validation messages from rejected attempts, in order."""

    @property
    def validation_failed(self) -> bool:
        return self.result is None


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal contract — each provider just needs to triage one message."""

    name: str

    is_model: bool
    """False for deterministic offline providers. The routing layer uses this
    to label the result `baseline` instead of `llm`, so an offline run can
    never be read as a model run."""

    def triage(self, message: InboundMessage) -> TriageOutcome: ...


ProviderFactory = Callable[[], LLMProvider]

_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory) -> None:
    """Register a provider factory under a `LLM_PROVIDER` value."""
    _REGISTRY[name.lower().strip()] = factory


def available_providers() -> tuple[str, ...]:
    return tuple(sorted(_REGISTRY))


def build_provider(name: str) -> LLMProvider:
    """Instantiate a registered provider, or raise `TriageError`."""
    key = name.lower().strip()
    factory = _REGISTRY.get(key)
    if factory is None:
        raise TriageError(
            f"unknown LLM provider {name!r} — available: {', '.join(available_providers())}"
        )
    try:
        return factory()
    except TriageError:
        raise
    except Exception as exc:  # missing optional SDK, bad credentials object, ...
        raise TriageError(f"could not initialise provider {key!r}: {exc}") from exc
