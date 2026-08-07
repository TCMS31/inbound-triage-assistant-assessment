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
        correction = (
            f"That tool call was invalid: {error}. "
            f"Call {TRIAGE_TOOL['name']} again. {CORRECTION_INSTRUCTION}"
        )
        # The Messages API rejects a turn that follows a tool_use block unless
        # it answers that block with a tool_result, so a plain-text correction
        # would turn every corrective retry into a 400. Only a reply with no
        # tool call at all gets the plain-text form.
        tool_use_ids = [
            block.id for block in assistant_turn if getattr(block, "type", None) == "tool_use"
        ]
        if not tool_use_ids:
            return [
                {"role": "assistant", "content": assistant_turn},
                {"role": "user", "content": correction},
            ]
        return [
            {"role": "assistant", "content": assistant_turn},
            {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "is_error": True,
                        "content": correction,
                    }
                    for tool_use_id in tool_use_ids
                ],
            },
        ]


register_provider("anthropic", AnthropicProvider)
