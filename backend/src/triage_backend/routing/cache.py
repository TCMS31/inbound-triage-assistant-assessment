"""Triage result cache.

Keyed on message id *and* a fingerprint of the message content, so editing a
message's body invalidates its cached triage instead of serving a result that
was computed from different text.

Two fixes over a naive `json.dump` cache, both of which matter the moment more
than one row is triaged at once (the UI fans out three at a time):

* **Atomic writes.** The file is written to a sibling temp file and
  `os.replace`d in, so a reader never sees a half-written file.
* **Memoised reads.** The file is parsed once per change, not once per
  request, and looked up by key.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from pathlib import Path

from triage_backend.config import get_settings
from triage_backend.schemas import InboundMessage, TriageResponse

logger = logging.getLogger(__name__)

CACHE_VERSION = 2
"""Bumped when the on-disk shape changes. Entries written by an older version
are ignored rather than mis-parsed."""


class ResultCache:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.RLock()
        self._stamp: tuple[int, int] | None = None
        self._entries: dict[str, dict] = {}

    @property
    def path(self) -> Path:
        return self._path

    # --- disk -------------------------------------------------------------

    def _load(self) -> dict[str, dict]:
        with self._lock:
            if not self._path.exists():
                self._entries = {}
                self._stamp = None
                return self._entries
            stat = self._path.stat()
            stamp = (stat.st_mtime_ns, stat.st_size)
            if stamp == self._stamp:
                return self._entries
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                # A corrupt cache is a performance problem, not a correctness
                # one: drop it and recompute rather than failing the request.
                logger.warning("triage cache at %s is unreadable (%s) — ignoring", self._path, exc)
                raw = {}
            if not isinstance(raw, dict) or raw.get("version") != CACHE_VERSION:
                raw = {}
            entries = raw.get("entries", {})
            self._entries = entries if isinstance(entries, dict) else {}
            self._stamp = stamp
            return self._entries

    def _write(self, entries: dict[str, dict]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps({"version": CACHE_VERSION, "entries": entries}, indent=2)
        handle, tmp_name = tempfile.mkstemp(
            dir=self._path.parent, prefix=".results-", suffix=".tmp"
        )
        try:
            with os.fdopen(handle, "w", encoding="utf-8") as tmp:
                tmp.write(payload)
            os.replace(tmp_name, self._path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
        self._entries = entries
        stat = self._path.stat()
        self._stamp = (stat.st_mtime_ns, stat.st_size)

    # --- api --------------------------------------------------------------

    def get(self, message: InboundMessage) -> TriageResponse | None:
        entry = self._load().get(message.id)
        if entry is None:
            return None
        if entry.get("fingerprint") != message.fingerprint():
            logger.info("cache entry for %s is stale (message changed) — retriaging", message.id)
            return None
        try:
            return TriageResponse.model_validate(entry["response"])
        except (KeyError, ValueError) as exc:
            logger.warning("discarding unreadable cache entry for %s: %s", message.id, exc)
            return None

    def put(self, message: InboundMessage, response: TriageResponse) -> None:
        # Never cache an error: a transient API failure must not stick forever.
        if response.error:
            return
        with self._lock:
            entries = dict(self._load())
            entries[message.id] = {
                "fingerprint": message.fingerprint(),
                "response": response.model_dump(),
            }
            self._write(entries)

    def forget(self, message_id: str) -> None:
        """Drop one entry so the next request re-runs the pipeline."""
        with self._lock:
            entries = dict(self._load())
            if entries.pop(message_id, None) is not None:
                self._write(entries)

    def clear(self) -> None:
        with self._lock:
            self._write({})


_cache: ResultCache | None = None
_cache_lock = threading.Lock()


def get_cache() -> ResultCache:
    global _cache
    if _cache is None:
        with _cache_lock:
            if _cache is None:
                _cache = ResultCache(get_settings().results_path)
    return _cache


def set_cache(cache: ResultCache | None) -> None:
    """Swap the process-wide cache (tests, alternative backends)."""
    global _cache
    _cache = cache
