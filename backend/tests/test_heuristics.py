"""The malformed-input pre-check. This runs before any model call, so its
behaviour is the difference between spending a token and not."""

from __future__ import annotations

import pytest

from triage_backend.classification.heuristics import (
    EMPTY_OR_NEAR_EMPTY_BODY,
    GARBLED_ENCODING,
    GARBLED_SENDER,
    is_malformed,
    malformed_flags,
    meaningful_length,
)
from triage_backend.schemas import InboundMessage


def make(**overrides: str) -> InboundMessage:
    base = {
        "id": "inb-x",
        "received_at": "2025-01-06T09:00:00Z",
        "channel": "email",
        "from_name": "Ada Lovelace",
        "from_org": "(individual)",
        "subject": "Hello",
        "body": "I would like to discuss investing the proceeds of a sale.",
    }
    base.update(overrides)
    return InboundMessage.model_validate(base)


def test_normal_message_is_not_flagged() -> None:
    assert malformed_flags(make()) == []
    assert is_malformed(make()) is False


@pytest.mark.parametrize("body", ["", " ", "\n\t ", ".", "...", " - ", "!!"])
def test_near_empty_bodies_are_flagged(body: str) -> None:
    assert EMPTY_OR_NEAR_EMPTY_BODY in malformed_flags(make(body=body))


@pytest.mark.parametrize("body", ["abc", "yes", "Call me back today please."])
def test_short_but_real_bodies_are_not_flagged(body: str) -> None:
    assert malformed_flags(make(body=body)) == []


def test_meaningful_length_ignores_punctuation_and_whitespace() -> None:
    assert meaningful_length("  ... ") == 0
    assert meaningful_length(" hi. ") == 2


@pytest.mark.parametrize("body", ["\x00\x00 lost bytes", "text with ��", "\x0bvtab"])
def test_control_characters_and_replacement_chars_are_flagged(body: str) -> None:
    assert GARBLED_ENCODING in malformed_flags(make(body=body))


def test_tabs_and_newlines_are_not_control_noise() -> None:
    assert malformed_flags(make(body="line one\n\tline two, a real message")) == []


@pytest.mark.parametrize(
    "from_name",
    ["=?utf-8?B?VGVzdA==?=", " =?iso-8859-1?Q?Jos=E9?=", "Jane =?utf-8?b?abc?="],
)
def test_mime_encoded_word_sender_is_flagged(from_name: str) -> None:
    """The original only matched an encoded word at position 0, so a sender
    with any leading text or whitespace slipped through unflagged."""
    assert GARBLED_SENDER in malformed_flags(make(from_name=from_name))


def test_plain_sender_is_not_flagged() -> None:
    assert GARBLED_SENDER not in malformed_flags(make(from_name="Robert Ellison"))


@pytest.mark.parametrize("org", ["(individual)", "(unknown)", ""])
def test_sentinel_orgs_are_expected_not_malformed(org: str) -> None:
    """The brief calls these out as expected values; treating them as garbage
    would silently drop real messages into noise_other."""
    assert malformed_flags(make(from_org=org)) == []


def test_flags_accumulate_and_keep_a_stable_order() -> None:
    flags = malformed_flags(make(body=".\x00", from_name="=?utf-8?B?x?="))
    assert flags == [EMPTY_OR_NEAR_EMPTY_BODY, GARBLED_ENCODING, GARBLED_SENDER]
