"""The inbound source: the seam a real deployment would replace."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from triage_backend.ingestion import InboundSource, JsonFileSource, get_source, set_source
from triage_backend.schemas import InboundMessage


def test_loads_and_validates_every_message(isolated_settings, sample_messages: list[dict]) -> None:
    source = JsonFileSource(isolated_settings.inbound_path)
    messages = source.list_messages()
    assert len(messages) == len(sample_messages)
    assert all(isinstance(item, InboundMessage) for item in messages)


def test_lookup_by_id(isolated_settings) -> None:
    source = JsonFileSource(isolated_settings.inbound_path)
    assert source.get_message("inb-002").subject == "Need updated statement by Friday"
    assert source.get_message("nope") is None


def test_the_file_is_parsed_once_not_once_per_lookup(
    isolated_settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The original re-read, re-parsed and re-validated the whole corpus for
    every single lookup, and the UI does one lookup per row."""
    source = JsonFileSource(isolated_settings.inbound_path)
    source.list_messages()

    parses = 0
    original = json.loads

    def counting_loads(*args: object, **kwargs: object) -> object:
        nonlocal parses
        parses += 1
        return original(*args, **kwargs)

    monkeypatch.setattr(json, "loads", counting_loads)
    for _ in range(100):
        source.get_message("inb-001")
    assert parses == 0


def test_an_edited_file_is_reloaded(isolated_settings, sample_messages: list[dict]) -> None:
    source = JsonFileSource(isolated_settings.inbound_path)
    assert source.get_message("inb-777") is None

    added = {**sample_messages[0], "id": "inb-777"}
    isolated_settings.inbound_path.write_text(
        json.dumps([*sample_messages, added]), encoding="utf-8"
    )
    assert source.get_message("inb-777") is not None


def test_a_malformed_corpus_file_raises_rather_than_serving_nothing(tmp_path: Path) -> None:
    path = tmp_path / "broken.json"
    path.write_text("[{", encoding="utf-8")
    with pytest.raises(json.JSONDecodeError):
        JsonFileSource(path).list_messages()


def test_the_process_source_can_be_swapped(isolated_settings) -> None:
    """The Airtable/IMAP seam: one class, two methods, no other layer changes."""

    class SingleMessageSource:
        def list_messages(self) -> list[InboundMessage]:
            return [self.get_message("only")]

        def get_message(self, message_id: str) -> InboundMessage | None:
            if message_id != "only":
                return None
            return InboundMessage(
                id="only",
                received_at="2025-01-06T09:00:00Z",
                channel="airtable",
                from_name="Someone",
                from_org="(unknown)",
                subject="From another store",
                body="Proof that ingestion is pluggable.",
            )

    assert isinstance(SingleMessageSource(), InboundSource)
    set_source(SingleMessageSource())
    try:
        assert [m.id for m in get_source().list_messages()] == ["only"]
    finally:
        set_source(None)
