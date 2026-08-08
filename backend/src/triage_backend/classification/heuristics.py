"""Cheap, deterministic pre-check that runs before any LLM call.

Two goals: (1) don't spend an API call classifying something that isn't
meaningfully classifiable, and (2) guarantee the malformed/edge-case items in
the corpus (inb-010, inb-011) always resolve to a sane, low-priority result
instead of depending on the model to notice they are garbage.

Flag strings are part of the persisted cache format — rename one and old
cached rows stop matching. Add new flags rather than renaming existing ones.
"""

from __future__ import annotations

import re
import string

from triage_backend.schemas import InboundMessage

EMPTY_OR_NEAR_EMPTY_BODY = "empty_or_near_empty_body"
GARBLED_ENCODING = "garbled_encoding"
GARBLED_SENDER = "garbled_sender"

#: Below this many "meaningful" characters a body carries no classifiable signal.
MIN_MEANINGFUL_BODY_CHARS = 3

_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")
_REPLACEMENT_CHAR = "�"
# A raw, un-decoded RFC 2047 encoded-word, e.g. "=?utf-8?B?...". Searched
# rather than anchored: real headers arrive with leading whitespace or a
# display-name fragment in front of the encoded part.
_MIME_ENCODED_WORD = re.compile(r"=\?[\w-]+\?[bBqQ]\?")

# Sentinel org values the brief calls out as expected, not as corruption.
SENTINEL_ORGS = frozenset({"(individual)", "(unknown)", ""})


def meaningful_length(body: str) -> int:
    """Length of the body once whitespace and pure punctuation are removed.

    A lone "." (the inb-010 sample) has length 1 but carries no signal.
    """
    return len(body.strip().strip(string.punctuation + string.whitespace))


def malformed_flags(message: InboundMessage) -> list[str]:
    """Reasons this message is malformed/low-signal, or `[]` if it looks like
    normal parseable text. Order is stable so the UI's "first flag" label is."""
    flags: list[str] = []
    body = message.body or ""

    if meaningful_length(body) < MIN_MEANINGFUL_BODY_CHARS:
        flags.append(EMPTY_OR_NEAR_EMPTY_BODY)

    if _CONTROL_CHARS.search(body) or _REPLACEMENT_CHAR in body:
        flags.append(GARBLED_ENCODING)

    sender = message.from_name or ""
    if _MIME_ENCODED_WORD.search(sender) or _CONTROL_CHARS.search(sender):
        flags.append(GARBLED_SENDER)

    return flags


def is_malformed(message: InboundMessage) -> bool:
    return bool(malformed_flags(message))
