"""Measure the cost of one message lookup, before and after the uplift.

    uv run python scripts/bench_lookup.py [--sizes 13 10000]

The pre-uplift `data_store.get_inbound_by_id` read the JSON file, parsed it,
validated every record into a Pydantic model and then linear-scanned for one
id — per call. The triage endpoint calls it once per row, so rendering a page
of N messages re-parsed the whole corpus N times.

`NaiveSource` below reproduces that implementation exactly so the comparison
is runnable rather than asserted. Every number in the README's design notes
comes from this script.
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
import tempfile
import time
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from triage_backend.ingestion import JsonFileSource  # noqa: E402
from triage_backend.schemas import InboundMessage  # noqa: E402


class NaiveSource:
    """The pre-uplift implementation, reproduced verbatim for comparison."""

    def __init__(self, path: Path) -> None:
        self._path = path

    def list_messages(self) -> list[InboundMessage]:
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        return [InboundMessage.model_validate(item) for item in raw]

    def get_message(self, message_id: str) -> InboundMessage | None:
        for message in self.list_messages():
            if message.id == message_id:
                return message
        return None


def corpus(size: int, target: Path) -> list[str]:
    base = json.loads((BACKEND_ROOT / "data" / "inbound.json").read_text(encoding="utf-8"))
    rows = []
    for index in range(size):
        row = copy.deepcopy(base[index % len(base)])
        row["id"] = f"inb-{index:06d}"
        rows.append(row)
    target.write_text(json.dumps(rows), encoding="utf-8")
    return [row["id"] for row in rows]


def time_lookups(source: object, ids: list[str], iterations: int) -> float:
    source.get_message(ids[0])  # warm whatever caching exists
    started = time.perf_counter()
    for index in range(iterations):
        source.get_message(ids[(index * 997) % len(ids)])
    return (time.perf_counter() - started) / iterations


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sizes", type=int, nargs="+", default=[13, 1000, 10000])
    parser.add_argument("--iterations", type=int, default=200)
    args = parser.parse_args()

    print(f"{'corpus':>8}  {'naive (pre-uplift)':>20}  {'indexed (current)':>20}  {'speedup':>9}")
    print("-" * 66)
    with tempfile.TemporaryDirectory() as tmp:
        for size in args.sizes:
            path = Path(tmp) / f"inbound-{size}.json"
            ids = corpus(size, path)
            naive = time_lookups(NaiveSource(path), ids, args.iterations) * 1e6
            indexed = time_lookups(JsonFileSource(path), ids, args.iterations) * 1e6
            speedup = naive / indexed if indexed else float("inf")
            print(f"{size:>8}  {naive:>17.1f} us  {indexed:>17.2f} us  {speedup:>8.0f}x")
    print()
    print(
        f"{args.iterations} lookups per cell, mean per lookup. Python "
        f"{sys.version.split()[0]} on {sys.platform}."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
