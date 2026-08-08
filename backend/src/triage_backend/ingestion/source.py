"""Inbound message sources.

`InboundSource` is the seam: swapping the local JSON corpus for Airtable,
IMAP or a queue consumer means writing one class with two methods and
registering it here — no other layer changes.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Protocol, runtime_checkable

from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage


@runtime_checkable
class InboundSource(Protocol):
    """Everything the rest of the app needs from a message source."""

    def list_messages(self) -> list[InboundMessage]: ...

    def get_message(self, message_id: str) -> InboundMessage | None: ...


class JsonFileSource:
    """Reads a JSON array of messages from disk.

    The file is parsed once and memoised against its (mtime_ns, size); a lookup
    is then a dict hit rather than a whole-file read + parse + validate of every
    record. That matters because the triage endpoint is called once per row, so
    the naive version re-parsed the entire corpus N times to render one page.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._stamp: tuple[int, int] | None = None
        self._messages: list[InboundMessage] = []
        self._index: dict[str, InboundMessage] = {}

    @property
    def path(self) -> Path:
        return self._path

    def _refresh(self) -> None:
        stat = self._path.stat()
        stamp = (stat.st_mtime_ns, stat.st_size)
        with self._lock:
            if stamp == self._stamp:
                return
            raw = json.loads(self._path.read_text(encoding="utf-8"))
            messages = [InboundMessage.model_validate(item) for item in raw]
            self._messages = messages
            self._index = {message.id: message for message in messages}
            self._stamp = stamp

    def list_messages(self) -> list[InboundMessage]:
        self._refresh()
        return list(self._messages)

    def get_message(self, message_id: str) -> InboundMessage | None:
        self._refresh()
        return self._index.get(message_id)


_source: InboundSource | None = None
_source_lock = threading.Lock()


def get_source() -> InboundSource:
    """Process-wide inbound source, built from settings on first use."""
    global _source
    if _source is None:
        with _source_lock:
            if _source is None:
                _source = JsonFileSource(get_settings().inbound_path)
    return _source


def set_source(source: InboundSource | None) -> None:
    """Swap the process-wide source. Used by tests and by any future
    deployment that reads from somewhere other than a local file."""
    global _source
    _source = source
