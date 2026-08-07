"""Shared fixtures.

Two invariants this file enforces for the whole suite:

1. **No test may open a socket.** Every provider is exercised against a fake
   client, so a test that reaches the network is a bug, not a slow test. The
   `no_network` fixture makes that failure loud instead of expensive.
2. **No test may read the developer's real configuration.** Settings are
   rebuilt from a scrubbed environment for every test, and the inbound source
   and result cache point at a tmp directory.
"""

from __future__ import annotations

import json
import socket
from collections.abc import Iterator
from pathlib import Path

import pytest

from triage_backend import ingestion
from triage_backend.config import Settings, get_settings
from triage_backend.routing.cache import ResultCache, set_cache
from triage_backend.schemas import InboundMessage

LLM_ENV_VARS = (
    "ANTHROPIC_API_KEY",
    "OPENAI_API_KEY",
    "LLM_PROVIDER",
    "MODEL_ID",
    "OPENAI_MODEL_ID",
    "TRIAGE_FORCE_ERROR_ID",
)


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Hard guarantee that the suite never calls a paid API."""

    def blocked(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "a test tried to open a network connection — every provider must be faked"
        )

    monkeypatch.setattr(socket.socket, "connect", blocked)
    monkeypatch.setattr(socket.socket, "connect_ex", blocked)
    monkeypatch.setattr(socket, "create_connection", blocked)


@pytest.fixture
def sample_messages() -> list[dict]:
    return [
        {
            "id": "inb-001",
            "received_at": "2025-01-06T09:12:00Z",
            "channel": "email",
            "from_name": "Gregory Palmer",
            "from_org": "(individual)",
            "subject": "Wealth planning after a liquidity event",
            "body": "I recently sold my business and have around $8M in proceeds to invest.",
        },
        {
            "id": "inb-002",
            "received_at": "2025-01-06T10:02:00Z",
            "channel": "web-form",
            "from_name": "Dana Whitfield",
            "from_org": "(unknown)",
            "subject": "Need updated statement by Friday",
            "body": "I'm an existing client and my lender needs an updated statement by Friday.",
        },
        {
            "id": "inb-010",
            "received_at": "2025-01-06T11:00:00Z",
            "channel": "web-form",
            "from_name": "",
            "from_org": "",
            "subject": "",
            "body": ".",
        },
    ]


@pytest.fixture(autouse=True)
def isolated_settings(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, sample_messages: list[dict]
) -> Iterator[Settings]:
    """Rebuild settings from a scrubbed environment, pointed at tmp_path.

    Environment variables beat `.env`, so setting each LLM var to "" here means
    a developer's real key can never leak into a test run.
    """
    for name in LLM_ENV_VARS:
        monkeypatch.setenv(name, "")

    inbound_path = tmp_path / "inbound.json"
    inbound_path.write_text(json.dumps(sample_messages), encoding="utf-8")
    monkeypatch.setenv("INBOUND_PATH", str(inbound_path))
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path / "results.json"))

    get_settings.cache_clear()
    ingestion.set_source(None)
    set_cache(None)

    yield get_settings()

    get_settings.cache_clear()
    ingestion.set_source(None)
    set_cache(None)


@pytest.fixture
def cache(isolated_settings: Settings) -> ResultCache:
    return ResultCache(isolated_settings.results_path)


@pytest.fixture
def message(sample_messages: list[dict]) -> InboundMessage:
    return InboundMessage.model_validate(sample_messages[0])


@pytest.fixture
def malformed_message(sample_messages: list[dict]) -> InboundMessage:
    return InboundMessage.model_validate(sample_messages[2])
