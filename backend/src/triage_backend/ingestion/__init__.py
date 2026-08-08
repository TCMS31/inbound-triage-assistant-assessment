"""Ingestion layer — where inbound messages come from.

Stage 1 of 3 (ingestion -> classification -> routing). Nothing in here knows
that an LLM exists; it only produces `InboundMessage` objects.
"""

from triage_backend.ingestion.source import (
    InboundSource,
    JsonFileSource,
    get_source,
    set_source,
)

__all__ = ["InboundSource", "JsonFileSource", "get_source", "set_source"]
