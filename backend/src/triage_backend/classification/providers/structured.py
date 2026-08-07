"""Shared retry/validation loop for providers that emit structured output.

Anthropic and OpenAI differ only in how the request is shaped and how the
payload is dug out of the response. Everything after that — validate, quote
the error back to the model, retry once, give up — is identical, so it lives
here once instead of twice.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import ValidationError

from triage_backend.classification.base import (
    StructuredOutputError,
    TriageError,
    TriageOutcome,
)
from triage_backend.classification.prompt import build_user_prompt
from triage_backend.schemas import InboundMessage, TriageResult

logger = logging.getLogger(__name__)

#: First attempt plus one corrective retry. Beyond two, a model that cannot
#: satisfy a four-field schema is not going to on the third try, and the caller
#: has a deterministic fallback that is cheaper and more predictable.
MAX_ATTEMPTS = 2


class StructuredOutputProvider:
    """Template for a provider. Subclasses implement the two abstract hooks."""

    name: str = "structured"
    is_model: bool = True
    max_attempts: int = MAX_ATTEMPTS

    # --- hooks ------------------------------------------------------------

    def _initial_conversation(self, message: InboundMessage) -> list[dict]:
        return [{"role": "user", "content": build_user_prompt(message)}]

    def _call_model(self, conversation: list[dict]) -> Any:
        """Make the request. Any exception becomes a `TriageError`."""
        raise NotImplementedError

    def _extract(self, response: Any) -> Any:
        """Return the payload to validate.

        Raise `StructuredOutputError` if the response is not shaped as asked.
        """
        raise NotImplementedError

    def _assistant_turn(self, response: Any) -> Any:
        """The assistant content to replay when asking for a correction."""
        raise NotImplementedError

    def _correction_turns(self, assistant_turn: Any, error: Exception) -> list[dict]:
        raise NotImplementedError

    # --- template ---------------------------------------------------------

    def triage(self, message: InboundMessage) -> TriageOutcome:
        conversation = self._initial_conversation(message)
        errors: list[str] = []

        for attempt in range(1, self.max_attempts + 1):
            try:
                response = self._call_model(conversation)
            except TriageError:
                raise
            except Exception as exc:
                # Broad on purpose, and only here: this is the boundary between
                # "the API call failed for any reason" (network, auth, rate
                # limit, or an SDK-level TypeError raised during header
                # validation before the request even goes out) and the rest of
                # the app. Every failure here must degrade to a per-row error,
                # never a 500 that takes the whole list down.
                raise TriageError(f"{type(exc).__name__}: {exc}") from exc

            try:
                result = TriageResult.model_validate(self._extract(response))
            except (ValidationError, StructuredOutputError, ValueError) as exc:
                errors.append(str(exc))
                logger.warning(
                    "%s: invalid structured output on attempt %d/%d: %s",
                    self.name,
                    attempt,
                    self.max_attempts,
                    exc,
                )
                if attempt < self.max_attempts:
                    conversation.extend(self._correction_turns(self._assistant_turn(response), exc))
                    continue
                break

            return TriageOutcome(result=result, attempts=attempt, validation_errors=errors)

        return TriageOutcome(result=None, attempts=self.max_attempts, validation_errors=errors)


CORRECTION_INSTRUCTION = (
    "Return exactly the four fields summary, category, priority, next_action, "
    "using only the allowed enum values."
)
