"""OpenAI provider: strict JSON-schema structured output, same contract out.

Run against a fake client — see `conftest.no_network`.
"""

from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from triage_backend.classification.base import TriageError
from triage_backend.classification.prompt import OPENAI_TRIAGE_SCHEMA, SYSTEM_PROMPT
from triage_backend.classification.providers.openai_provider import OpenAIProvider
from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage

GOOD = {
    "summary": "Business seller wants help investing $8M of sale proceeds.",
    "category": "prospect",
    "priority": "medium",
    "next_action": "Send the intro pack and offer a call.",
}
BAD_ENUM = {**GOOD, "priority": "urgent"}


def completion(content: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=content))])


def json_completion(payload: dict) -> SimpleNamespace:
    return completion(json.dumps(payload))


class FakeCompletions:
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
        self.chat = SimpleNamespace(completions=FakeCompletions(script))


@pytest.fixture
def provider(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key-not-a-real-credential")
    get_settings.cache_clear()

    def build(script: list) -> OpenAIProvider:
        instance = OpenAIProvider()
        instance._client = FakeClient(script)
        return instance

    return build


def test_happy_path_returns_a_validated_result(provider, message: InboundMessage) -> None:
    outcome = provider([json_completion(GOOD)]).triage(message)
    assert outcome.result is not None
    assert outcome.result.priority == "medium"
    assert outcome.attempts == 1


def test_request_pins_the_strict_json_schema_and_system_prompt(
    provider, message: InboundMessage
) -> None:
    llm = provider([json_completion(GOOD)])
    llm.triage(message)

    sent = llm._client.chat.completions.calls[0]
    assert sent["response_format"] == {
        "type": "json_schema",
        "json_schema": OPENAI_TRIAGE_SCHEMA,
    }
    assert sent["messages"][0] == {"role": "system", "content": SYSTEM_PROMPT}
    assert sent["messages"][1]["role"] == "user"


@pytest.mark.parametrize(
    "first",
    [
        completion(None),
        completion(""),
        completion("here you go: {not json"),
        json_completion(BAD_ENUM),
        json_completion({"summary": "only this one"}),
    ],
)
def test_every_malformed_first_response_is_corrected_on_retry(
    provider, message: InboundMessage, first: SimpleNamespace
) -> None:
    llm = provider([first, json_completion(GOOD)])
    outcome = llm.triage(message)

    assert outcome.result is not None
    assert outcome.attempts == 2
    correction = llm._client.chat.completions.calls[1]["messages"]
    assert correction[-1]["role"] == "user"
    assert "invalid" in correction[-1]["content"]


def test_two_bad_responses_give_up(provider, message: InboundMessage) -> None:
    llm = provider([json_completion(BAD_ENUM), completion("still not json")])
    outcome = llm.triage(message)

    assert outcome.result is None
    assert len(outcome.validation_errors) == 2


def test_empty_choices_does_not_raise_index_error(provider, message: InboundMessage) -> None:
    llm = provider([SimpleNamespace(choices=[]), json_completion(GOOD)])
    assert llm.triage(message).result is not None


@pytest.mark.parametrize(
    "failure", [ConnectionError("reset"), RuntimeError("401 unauthorized"), TimeoutError("slow")]
)
def test_api_failures_become_triage_errors(
    provider, message: InboundMessage, failure: Exception
) -> None:
    with pytest.raises(TriageError):
        provider([failure]).triage(message)
