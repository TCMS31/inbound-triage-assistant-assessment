"""Anthropic provider: forced tool call in, validated TriageResult out.

Every test here runs against a fake client. `conftest.no_network` makes a real
call impossible, so this file can never cost money.
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from triage_backend.classification.base import TriageError
from triage_backend.classification.prompt import SYSTEM_PROMPT, TRIAGE_TOOL
from triage_backend.classification.providers.anthropic_provider import AnthropicProvider
from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage

GOOD = {
    "summary": "Business seller wants help investing $8M of sale proceeds.",
    "category": "prospect",
    "priority": "medium",
    "next_action": "Send the intro pack and offer a call.",
}
BAD_ENUM = {**GOOD, "category": "definitely_a_prospect"}


def tool_response(payload: dict) -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="tool_use", input=payload)])


def text_response(text: str = "sure thing") -> SimpleNamespace:
    return SimpleNamespace(content=[SimpleNamespace(type="text", text=text)])


class FakeMessages:
    def __init__(self, script: list) -> None:
        self._script = list(script)
        self.calls: list[dict] = []

    def create(self, **kwargs: object) -> object:
        self.calls.append(kwargs)
        if not self._script:
            raise AssertionError("provider made more calls than the test scripted")
        step = self._script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step


class FakeClient:
    def __init__(self, script: list) -> None:
        self.messages = FakeMessages(script)


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-a-real-credential")
    get_settings.cache_clear()

    def build(script: list) -> AnthropicProvider:
        instance = AnthropicProvider()
        instance._client = FakeClient(script)
        return instance

    return build


def test_happy_path_returns_a_validated_result(provider, message: InboundMessage) -> None:
    llm = provider([tool_response(GOOD)])
    outcome = llm.triage(message)

    assert outcome.result is not None
    assert outcome.result.category == "prospect"
    assert outcome.attempts == 1
    assert outcome.validation_errors == []


def test_request_forces_the_single_triage_tool(provider, message: InboundMessage) -> None:
    llm = provider([tool_response(GOOD)])
    llm.triage(message)

    sent = llm._client.messages.calls[0]
    assert sent["tool_choice"] == {"type": "tool", "name": "emit_triage"}
    assert [tool["name"] for tool in sent["tools"]] == [TRIAGE_TOOL["name"]]
    assert sent["system"] == SYSTEM_PROMPT
    assert sent["messages"][0]["role"] == "user"
    assert message.body in sent["messages"][0]["content"]


def test_invalid_enum_triggers_one_corrective_retry_then_succeeds(
    provider, message: InboundMessage
) -> None:
    llm = provider([tool_response(BAD_ENUM), tool_response(GOOD)])
    outcome = llm.triage(message)

    assert outcome.result is not None
    assert outcome.attempts == 2
    assert len(outcome.validation_errors) == 1

    correction = llm._client.messages.calls[1]["messages"]
    assert correction[1]["role"] == "assistant"
    assert correction[2]["role"] == "user"
    assert "invalid" in correction[2]["content"]


def test_two_invalid_outputs_give_up_rather_than_loop(provider, message: InboundMessage) -> None:
    llm = provider([tool_response(BAD_ENUM), tool_response(BAD_ENUM)])
    outcome = llm.triage(message)

    assert outcome.result is None
    assert outcome.validation_failed is True
    assert outcome.attempts == 2
    assert len(llm._client.messages.calls) == 2


def test_missing_tool_use_block_is_a_recoverable_structure_failure(
    provider, message: InboundMessage
) -> None:
    """A text-only reply is not an API failure — it is the model ignoring the
    tool, which the corrective turn exists to fix."""
    llm = provider([text_response(), tool_response(GOOD)])
    outcome = llm.triage(message)

    assert outcome.result is not None
    assert "no tool_use block" in outcome.validation_errors[0]


@pytest.mark.parametrize(
    "failure",
    [
        ConnectionError("connection reset"),
        TypeError("Could not resolve authentication method"),
        RuntimeError("429 rate limit exceeded"),
    ],
)
def test_any_api_failure_becomes_a_triage_error(
    provider, message: InboundMessage, failure: Exception
) -> None:
    """The catch is deliberately broad: a missing key makes the SDK raise a
    plain TypeError during header validation, before any request goes out, and
    that must still degrade to a per-row error rather than a 500."""
    llm = provider([failure])
    with pytest.raises(TriageError) as excinfo:
        llm.triage(message)
    assert type(failure).__name__ in str(excinfo.value)


def test_api_failure_on_the_retry_also_surfaces_cleanly(provider, message: InboundMessage) -> None:
    llm = provider([tool_response(BAD_ENUM), ConnectionError("dropped")])
    with pytest.raises(TriageError):
        llm.triage(message)
