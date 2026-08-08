"""Anthropic (Claude) provider — forced `tool_choice` for structured output."""

from __future__ import annotations

from typing import Any

import anthropic

from triage_backend.classification.base import StructuredOutputError, register_provider
from triage_backend.classification.prompt import SYSTEM_PROMPT, TRIAGE_TOOL
from triage_backend.classification.providers.structured import (
    CORRECTION_INSTRUCTION,
    StructuredOutputProvider,
)
from triage_backend.config import get_settings

#: Triage output is four short fields; 500 tokens is generous headroom and
#: caps the blast radius of a model that decides to narrate.
MAX_OUTPUT_TOKENS = 500


class AnthropicProvider(StructuredOutputProvider):
    """The model is given exactly one tool and required to call it, so there is
    no "parse a string that might be JSON" step at all."""

    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        self._model = settings.model_id
        self._client = anthropic.Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_transport_retries,
        )

    def _call_model(self, conversation: list[dict]) -> Any:
        return self._client.messages.create(
            model=self._model,
            max_tokens=MAX_OUTPUT_TOKENS,
            system=SYSTEM_PROMPT,
            tools=[TRIAGE_TOOL],
            tool_choice={"type": "tool", "name": TRIAGE_TOOL["name"]},
            messages=conversation,
        )

    def _extract(self, response: Any) -> Any:
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                return block.input
        raise StructuredOutputError("model response contained no tool_use block")

    def _assistant_turn(self, response: Any) -> Any:
        return response.content

    def _correction_turns(self, assistant_turn: Any, error: Exception) -> list[dict]:
        return [
            {"role": "assistant", "content": assistant_turn},
            {
                "role": "user",
                "content": (
                    f"That tool call was invalid: {error}. "
                    f"Call {TRIAGE_TOOL['name']} again. {CORRECTION_INSTRUCTION}"
                ),
            },
        ]


register_provider("anthropic", AnthropicProvider)
