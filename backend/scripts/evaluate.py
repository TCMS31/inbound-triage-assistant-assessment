"""Score the triage pipeline against the hand-written reference labels.

    uv run python scripts/evaluate.py                  # whatever LLM_PROVIDER says
    LLM_PROVIDER=stub uv run python scripts/evaluate.py  # offline, free, deterministic
    uv run python scripts/evaluate.py --json report.json

Why this exists: "the model classifies inbound mail" is not a claim anyone
should accept without a number attached, and the number has to be reproducible
by whoever is reading the README. The offline `stub` provider is the baseline —
a model that cannot beat a page of regexes is not worth its latency or its bill.

Ambiguous items (see eval/golden.json) are reported separately rather than
folded into accuracy: scoring a defensible answer as wrong flatters nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from collections import Counter
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "src"))

from triage_backend.classification import TriageError  # noqa: E402
from triage_backend.config import get_settings  # noqa: E402
from triage_backend.ingestion import get_source  # noqa: E402
from triage_backend.routing import triage  # noqa: E402
from triage_backend.routing.cache import ResultCache  # noqa: E402

GOLDEN_PATH = BACKEND_ROOT / "eval" / "golden.json"


def load_golden() -> dict[str, dict]:
    raw = json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))
    return {item["id"]: item for item in raw["labels"]}


ACCEPTED_KEY = {"category": "accepted_categories", "priority": "accepted_priorities"}


def accepted(label: dict, field: str) -> set[str]:
    """Every label that would be a defensible answer for this message."""
    return {label[field], *label.get(ACCEPTED_KEY[field], [])}


def evaluate(scratch_cache: Path) -> dict:
    """Run every message through the real pipeline and score the results."""
    golden = load_golden()
    cache = ResultCache(scratch_cache)
    cache.clear()

    rows: list[dict] = []
    started = time.perf_counter()
    for message in get_source().list_messages():
        label = golden.get(message.id)
        if label is None:
            continue
        try:
            response = triage(message, cache=cache)
        except TriageError as exc:  # pragma: no cover - the pipeline catches these
            response = None
            error = str(exc)
        else:
            error = response.error_message if response.error else None

        result = response.result if response and response.result else None
        rows.append(
            {
                "id": message.id,
                "source": response.source if response else "n/a",
                "error": error,
                "expected_category": label["category"],
                "actual_category": result.category if result else None,
                "expected_priority": label["priority"],
                "actual_priority": result.priority if result else None,
                "ambiguous": bool(label.get("ambiguous")),
                "category_ok": bool(result) and result.category in accepted(label, "category"),
                "priority_ok": bool(result) and result.priority in accepted(label, "priority"),
                "note": label.get("note", ""),
            }
        )
    elapsed = time.perf_counter() - started

    scored = [row for row in rows if not row["ambiguous"]]
    sources = Counter(row["source"] for row in rows)
    return {
        "provider": get_settings().llm_provider or "auto",
        "messages": len(rows),
        "scored": len(scored),
        "ambiguous": len(rows) - len(scored),
        "errors": sum(1 for row in rows if row["error"]),
        "category_correct": sum(1 for row in scored if row["category_ok"]),
        "priority_correct": sum(1 for row in scored if row["priority_ok"]),
        "both_correct": sum(1 for row in scored if row["category_ok"] and row["priority_ok"]),
        "sources": dict(sources),
        "seconds": round(elapsed, 2),
        "rows": rows,
    }


def percent(part: int, whole: int) -> str:
    return f"{part}/{whole} ({part / whole * 100:.0f}%)" if whole else "n/a"


def render(report: dict) -> str:
    lines = [
        f"provider={report['provider']}  messages={report['messages']}  "
        f"scored={report['scored']}  ambiguous={report['ambiguous']}  "
        f"errors={report['errors']}  {report['seconds']}s",
        f"sources: {report['sources']}",
        "",
        f"category  {percent(report['category_correct'], report['scored'])}",
        f"priority  {percent(report['priority_correct'], report['scored'])}",
        f"both      {percent(report['both_correct'], report['scored'])}",
        "",
        f"{'id':<9} {'source':<10} {'category (actual/expected)':<34} "
        f"{'priority (actual/expected)':<26}",
        "-" * 80,
    ]
    for row in report["rows"]:
        category = f"{row['actual_category']} / {row['expected_category']}"
        priority = f"{row['actual_priority']} / {row['expected_priority']}"
        if row["ambiguous"]:
            verdict = "~ ambiguous"
        else:
            verdict = " ".join(
                [
                    "cat:ok" if row["category_ok"] else "cat:MISS",
                    "pri:ok" if row["priority_ok"] else "pri:MISS",
                ]
            )
        lines.append(f"{row['id']:<9} {row['source']:<10} {category:<34} {priority:<26} {verdict}")
        if row["error"]:
            lines.append(f"          error: {row['error']}")
    lines.append("")
    lines.append("~ = genuinely ambiguous message, excluded from the accuracy numbers")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", type=Path, help="also write the full report as JSON")
    args = parser.parse_args()

    scratch = BACKEND_ROOT / "data" / ".eval-cache.json"
    try:
        report = evaluate(scratch)
    finally:
        scratch.unlink(missing_ok=True)

    print(render(report))
    if args.json:
        args.json.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0 if report["errors"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
