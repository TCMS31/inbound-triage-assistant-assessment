"""Which provider answers, and what happens when none can."""

from __future__ import annotations

import pytest

from triage_backend.classification import (
    TriageError,
    available_providers,
    classify,
    resolve_provider,
)
from triage_backend.classification.base import build_provider, register_provider
from triage_backend.classification.providers.anthropic_provider import AnthropicProvider
from triage_backend.classification.providers.openai_provider import OpenAIProvider
from triage_backend.classification.providers.stub_provider import StubProvider
from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage

REAL_LOOKING_KEY = "test-key-not-a-real-credential"


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch):
    def apply(**values: str) -> None:
        for name, value in values.items():
            monkeypatch.setenv(name.upper(), value)
        get_settings.cache_clear()

    return apply


def test_builtin_providers_are_registered() -> None:
    assert available_providers() == ("anthropic", "openai", "stub")


def test_auto_prefers_anthropic_when_both_keys_are_present(env) -> None:
    env(ANTHROPIC_API_KEY=REAL_LOOKING_KEY, OPENAI_API_KEY=REAL_LOOKING_KEY, LLM_PROVIDER="auto")
    assert isinstance(resolve_provider(), AnthropicProvider)


def test_auto_falls_through_to_openai(env) -> None:
    env(ANTHROPIC_API_KEY="", OPENAI_API_KEY=REAL_LOOKING_KEY, LLM_PROVIDER="auto")
    assert isinstance(resolve_provider(), OpenAIProvider)


def test_auto_never_silently_selects_the_offline_stub(env) -> None:
    """An offline baseline masquerading as a model call is the worst possible
    failure mode for a triage tool, so `auto` must fail loudly instead."""
    env(ANTHROPIC_API_KEY="", OPENAI_API_KEY="", LLM_PROVIDER="auto")
    with pytest.raises(TriageError) as excinfo:
        resolve_provider()
    assert "No LLM API key configured" in str(excinfo.value)


def test_stub_must_be_asked_for_by_name(env) -> None:
    env(LLM_PROVIDER="stub")
    assert isinstance(resolve_provider(), StubProvider)


@pytest.mark.parametrize(
    ("provider", "key_var"),
    [("anthropic", "ANTHROPIC_API_KEY"), ("openai", "OPENAI_API_KEY")],
)
def test_explicit_provider_without_its_key_fails_with_a_readable_message(
    env, provider: str, key_var: str
) -> None:
    env(LLM_PROVIDER=provider, ANTHROPIC_API_KEY="", OPENAI_API_KEY="")
    with pytest.raises(TriageError) as excinfo:
        resolve_provider()
    assert key_var in str(excinfo.value)


@pytest.mark.parametrize("value", ["  ANTHROPIC  ", "OpenAI", "Stub"])
def test_provider_names_are_case_and_whitespace_insensitive(env, value: str) -> None:
    env(LLM_PROVIDER=value, ANTHROPIC_API_KEY=REAL_LOOKING_KEY, OPENAI_API_KEY=REAL_LOOKING_KEY)
    assert resolve_provider().name == value.strip().lower()


def test_unknown_provider_is_a_triage_error_not_a_crash(env) -> None:
    env(LLM_PROVIDER="llama-on-a-toaster")
    with pytest.raises(TriageError) as excinfo:
        resolve_provider()
    assert "unknown LLM provider" in str(excinfo.value)


def test_a_provider_that_fails_to_construct_is_a_triage_error() -> None:
    """A missing optional SDK must not escape the classification layer as a
    bare ImportError — the route has no handler for that."""

    def broken() -> object:
        raise ImportError("No module named 'openai'")

    register_provider("broken-for-test", broken)
    try:
        with pytest.raises(TriageError) as excinfo:
            build_provider("broken-for-test")
        assert "could not initialise provider" in str(excinfo.value)
    finally:
        from triage_backend.classification import base

        base._REGISTRY.pop("broken-for-test", None)


def test_a_third_party_provider_can_be_registered_without_touching_the_package(
    env, message: InboundMessage
) -> None:
    """The extensibility seam, exercised the way a future developer would."""
    from triage_backend.classification.base import TriageOutcome
    from triage_backend.schemas import TriageResult

    class RegexProvider:
        name = "regex-only"

        def triage(self, _: InboundMessage) -> TriageOutcome:
            return TriageOutcome(
                result=TriageResult(
                    summary="Handled by a bespoke provider.",
                    category="noise_other",
                    priority="low",
                    next_action="Archive.",
                )
            )

    register_provider("regex-only", RegexProvider)
    try:
        env(LLM_PROVIDER="regex-only")
        outcome = classify(message)
        assert outcome.provider == "regex-only"
        assert outcome.result is not None
    finally:
        from triage_backend.classification import base

        base._REGISTRY.pop("regex-only", None)


def test_force_error_id_short_circuits_before_any_provider_is_built(env) -> None:
    """The demo aid must fire without a key configured, or it cannot be used
    to demo the error path offline."""
    env(TRIAGE_FORCE_ERROR_ID="inb-001", LLM_PROVIDER="stub")
    from triage_backend.ingestion import get_source

    with pytest.raises(TriageError) as excinfo:
        classify(get_source().get_message("inb-001"))
    assert "simulated failure" in str(excinfo.value)


def test_force_error_id_leaves_other_messages_alone(env) -> None:
    env(TRIAGE_FORCE_ERROR_ID="inb-001", LLM_PROVIDER="stub")
    from triage_backend.ingestion import get_source

    assert classify(get_source().get_message("inb-002")).result is not None


def test_classify_records_the_provider_that_answered(env, message: InboundMessage) -> None:
    env(LLM_PROVIDER="stub")
    assert classify(message).provider == "stub"
