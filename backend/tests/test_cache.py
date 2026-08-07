"""The result cache — correctness under edits, corruption and concurrency."""

from __future__ import annotations

import json
import threading
from pathlib import Path

import pytest

from triage_backend.routing.cache import CACHE_VERSION, ResultCache
from triage_backend.schemas import InboundMessage, StoredTriageResult, TriageResponse

RESULT = StoredTriageResult(
    summary="Business seller wants help investing sale proceeds.",
    category="prospect",
    priority="medium",
    next_action="Send the intro pack.",
)


def response(message_id: str = "inb-001", **overrides: object) -> TriageResponse:
    return TriageResponse(id=message_id, result=RESULT, source="llm", **overrides)


def test_miss_then_hit(cache: ResultCache, message: InboundMessage) -> None:
    assert cache.get(message) is None
    cache.put(message, response())
    assert cache.get(message) == response()


def test_editing_a_message_invalidates_its_cached_result(
    cache: ResultCache, message: InboundMessage
) -> None:
    """Keying on id alone would serve a triage computed from text that is no
    longer in the message."""
    cache.put(message, response())
    edited = message.model_copy(update={"body": "Actually, I am an existing client."})
    assert cache.get(edited) is None


def test_errors_are_never_cached(cache: ResultCache, message: InboundMessage) -> None:
    """A transient API failure must not stick forever — the Retry button has
    to be able to actually retry."""
    cache.put(message, TriageResponse(id=message.id, error=True, error_message="429"))
    assert cache.get(message) is None


def test_forget_drops_one_entry(cache: ResultCache, message: InboundMessage) -> None:
    cache.put(message, response())
    cache.forget(message.id)
    assert cache.get(message) is None


def test_forget_is_a_no_op_for_an_unknown_id(cache: ResultCache) -> None:
    cache.forget("nope")  # must not raise or create a file
    assert not cache.path.exists()


def test_clear_empties_the_store(cache: ResultCache, message: InboundMessage) -> None:
    cache.put(message, response())
    cache.clear()
    assert cache.get(message) is None


def test_a_corrupt_cache_file_is_ignored_not_fatal(
    cache: ResultCache, message: InboundMessage
) -> None:
    cache.path.write_text("{not json at all", encoding="utf-8")
    assert cache.get(message) is None
    cache.put(message, response())
    assert cache.get(message) is not None


def test_an_older_cache_format_is_discarded(cache: ResultCache, message: InboundMessage) -> None:
    """The pre-uplift format was a bare {id: response} map with no fingerprint;
    reading it as if it were the current one would serve unkeyed results."""
    cache.path.write_text(json.dumps({message.id: response().model_dump()}), encoding="utf-8")
    assert cache.get(message) is None


def test_written_file_is_versioned_and_fingerprinted(
    cache: ResultCache, message: InboundMessage
) -> None:
    cache.put(message, response())
    raw = json.loads(cache.path.read_text(encoding="utf-8"))
    assert raw["version"] == CACHE_VERSION
    assert raw["entries"][message.id]["fingerprint"] == message.fingerprint()


def test_a_reader_never_sees_a_partially_written_file(
    tmp_path: Path, sample_messages: list[dict]
) -> None:
    """Writes go through a temp file and os.replace. Without that, the UI's
    three-at-a-time fan-out can read a truncated JSON document."""
    path = tmp_path / "results.json"
    writer = ResultCache(path)
    messages = [
        InboundMessage.model_validate(sample_messages[0]).model_copy(
            update={"id": f"inb-{index:03d}", "body": f"Distinct body number {index}."}
        )
        for index in range(40)
    ]
    for item in messages:
        writer.put(item, response(item.id))

    errors: list[Exception] = []
    stop = threading.Event()

    def reader() -> None:
        while not stop.is_set():
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                errors.append(exc)

    thread = threading.Thread(target=reader, daemon=True)
    thread.start()
    try:
        for _ in range(20):
            for item in messages:
                writer.put(item, response(item.id))
    finally:
        stop.set()
        thread.join(timeout=5)

    assert errors == []


def test_concurrent_writers_do_not_lose_entries(
    cache: ResultCache, sample_messages: list[dict]
) -> None:
    messages = [
        InboundMessage.model_validate(sample_messages[0]).model_copy(
            update={"id": f"inb-{index:03d}", "body": f"Distinct body number {index}."}
        )
        for index in range(30)
    ]

    def write(item: InboundMessage) -> None:
        cache.put(item, response(item.id))

    threads = [threading.Thread(target=write, args=(item,)) for item in messages]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()

    assert all(cache.get(item) is not None for item in messages)


def test_repeated_reads_do_not_reparse_the_file(
    cache: ResultCache, message: InboundMessage, monkeypatch: pytest.MonkeyPatch
) -> None:
    cache.put(message, response())
    cache.get(message)

    reads = 0
    original = Path.read_text

    def counting_read_text(self: Path, *args: object, **kwargs: object) -> str:
        nonlocal reads
        if self == cache.path:
            reads += 1
        return original(self, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", counting_read_text)
    for _ in range(50):
        cache.get(message)
    assert reads == 0
