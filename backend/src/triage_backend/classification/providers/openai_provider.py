"""OpenAI (GPT) provider — `response_format` structured outputs."""

from __future__ import annotations

import json
from typing import Any

from triage_backend.classification.base import (
    StructuredOutputError,
    TriageError,
    register_provider,
)
from triage_backend.classification.prompt import OPENAI_TRIAGE_SCHEMA, SYSTEM_PROMPT
from triage_backend.classification.providers.structured import (
    CORRECTION_INSTRUCTION,
    StructuredOutputProvider,
)
from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage


class OpenAIProvider(StructuredOutputProvider):
    """Structured outputs via a strict JSON schema — OpenAI's equivalent of
    Anthropic's forced tool call. The same Pydantic model re-validates the
    parsed JSON, so the contract downstream is byte-identical either way."""

    name = "openai"

    def __init__(self) -> None:
        try:
            import openai
        except ImportError as exc:  # optional extra — see pyproject.toml
            raise TriageError(
                "the openai package is not installed — run `uv sync --extra openai`"
            ) from exc

        settings = get_settings()
        self._model = settings.openai_model_id
        self._client = openai.OpenAI(
            api_key=settings.openai_api_key,
            timeout=settings.llm_timeout_seconds,
            max_retries=settings.llm_transport_retries,
        )

    def _initial_conversation(self, message: InboundMessage) -> list[dict]:
        # OpenAI carries the system prompt as the first message rather than as
        # a separate request field.
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            *super()._initial_conversation(message),
        ]

    def _call_model(self, conversation: list[dict]) -> Any:
        return self._client.chat.completions.create(
            model=self._model,
            messages=conversation,
            response_format={"type": "json_schema", "json_schema": OPENAI_TRIAGE_SCHEMA},
        )

    @staticmethod
    def _content(response: Any) -> str | None:
        choices = getattr(response, "choices", None) or []
        if not choices:
            return None
        return choices[0].message.content

    def _extract(self, response: Any) -> Any:
        content = self._content(response)
        if not content:
            raise StructuredOutputError("OpenAI returned empty content")
        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise StructuredOutputError(f"response was not valid JSON: {exc}") from exc

    def _assistant_turn(self, response: Any) -> Any:
        return self._content(response) or ""

    def _correction_turns(self, assistant_turn: Any, error: Exception) -> list[dict]:
        return [
            {"role": "assistant", "content": assistant_turn},
            {
                "role": "user",
                "content": f"Your response was invalid: {error}. {CORRECTION_INSTRUCTION}",
            },
        ]


register_provider("openai", OpenAIProvider)
