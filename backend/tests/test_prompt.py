"""The prompt and the two provider schemas are generated from one taxonomy.

These tests are the guard on `RATIONALE.md`'s claim that adding a category is
a one-line change: if the prompt, the Anthropic tool and the OpenAI schema can
drift from `TriageResult`, that claim is false.
"""

from __future__ import annotations

from pathlib import Path

from triage_backend.classification.prompt import (
    OPENAI_TRIAGE_SCHEMA,
    SYSTEM_PROMPT,
    TRIAGE_TOOL,
    build_user_prompt,
)
from triage_backend.schemas import MODEL_CATEGORIES, PRIORITIES, InboundMessage

FIELDS = {"summary", "category", "priority", "next_action"}


def test_anthropic_tool_enums_match_the_validated_taxonomy() -> None:
    properties = TRIAGE_TOOL["input_schema"]["properties"]
    assert properties["category"]["enum"] == list(MODEL_CATEGORIES)
    assert properties["priority"]["enum"] == list(PRIORITIES)
    assert set(TRIAGE_TOOL["input_schema"]["required"]) == FIELDS


def test_openai_schema_matches_the_validated_taxonomy() -> None:
    schema = OPENAI_TRIAGE_SCHEMA["schema"]
    assert schema["properties"]["category"]["enum"] == list(MODEL_CATEGORIES)
    assert schema["properties"]["priority"]["enum"] == list(PRIORITIES)
    assert set(schema["required"]) == FIELDS
    assert schema["additionalProperties"] is False
    assert OPENAI_TRIAGE_SCHEMA["strict"] is True


def test_both_providers_are_shown_the_same_fields() -> None:
    assert TRIAGE_TOOL["input_schema"]["properties"] == OPENAI_TRIAGE_SCHEMA["schema"]["properties"]


def test_system_prompt_lists_every_category_and_priority() -> None:
    for value in (*MODEL_CATEGORIES, *PRIORITIES):
        assert value in SYSTEM_PROMPT


def test_system_prompt_does_not_offer_the_fallback_category_to_the_model() -> None:
    assert "needs_review" not in SYSTEM_PROMPT


def test_system_prompt_grounds_the_model_against_invention() -> None:
    assert "Do not invent" in SYSTEM_PROMPT


def test_user_prompt_marks_empty_fields_rather_than_leaving_blanks(
    message: InboundMessage,
) -> None:
    blank = message.model_copy(update={"subject": "", "from_org": ""})
    rendered = build_user_prompt(blank)
    assert "subject: (empty)" in rendered
    assert "from_org: (empty)" in rendered
    assert f"body: {blank.body}" in rendered


def test_user_prompt_sends_key_values_not_raw_json(message: InboundMessage) -> None:
    rendered = build_user_prompt(message)
    assert rendered.startswith("channel: ")
    assert "{" not in rendered


def test_the_mirrored_prompt_doc_is_still_the_prompt() -> None:
    """`prompts/triage_prompt.md` reproduces SYSTEM_PROMPT for review. A doc
    that quietly drifts from the code is worse than no doc."""
    doc = (
        Path(__file__).resolve().parent.parent.parent / "prompts" / "triage_prompt.md"
    ).read_text(encoding="utf-8")
    assert SYSTEM_PROMPT in doc, "prompts/triage_prompt.md no longer matches SYSTEM_PROMPT"
