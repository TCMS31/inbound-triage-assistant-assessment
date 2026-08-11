"""The evaluation harness itself.

`scripts/evaluate.py` is what turns "it classifies inbound mail" into a number
somebody else can reproduce, so it needs to be right about what it is counting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

BACKEND_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_ROOT / "scripts"))

import evaluate  # noqa: E402

from triage_backend.schemas import MODEL_CATEGORIES, PRIORITIES  # noqa: E402


def test_golden_set_covers_every_message_in_the_shipped_corpus() -> None:
    corpus = json.loads((BACKEND_ROOT / "data" / "inbound.json").read_text(encoding="utf-8"))
    labels = evaluate.load_golden()
    assert {item["id"] for item in corpus} == set(labels)


def test_every_golden_label_uses_a_real_taxonomy_value() -> None:
    for label in evaluate.load_golden().values():
        assert label["category"] in MODEL_CATEGORIES
        assert label["priority"] in PRIORITIES
        for value in label.get("accepted_categories", []):
            assert value in MODEL_CATEGORIES
        for value in label.get("accepted_priorities", []):
            assert value in PRIORITIES


def test_every_golden_label_carries_its_reasoning() -> None:
    """A label with no note is an assertion nobody can argue with."""
    assert all(label.get("note") for label in evaluate.load_golden().values())


def test_accepted_always_includes_the_primary_label() -> None:
    label = {"category": "prospect", "accepted_categories": ["existing_client"]}
    assert evaluate.accepted(label, "category") == {"prospect", "existing_client"}
    assert evaluate.accepted({"priority": "high"}, "priority") == {"high"}


def test_percent_handles_an_empty_denominator() -> None:
    assert evaluate.percent(0, 0) == "n/a"
    assert evaluate.percent(3, 4) == "3/4 (75%)"


@pytest.mark.parametrize("provider", ["stub"])
def test_the_harness_runs_end_to_end_offline(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, provider: str
) -> None:
    """Uses the shipped corpus and the shipped labels, with no key and no
    network — the run quoted in the README is this run."""
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv("INBOUND_PATH", str(BACKEND_ROOT / "data" / "inbound.json"))
    monkeypatch.setenv("RESULTS_PATH", str(tmp_path / "results.json"))
    from triage_backend.config import get_settings
    from triage_backend.ingestion import set_source

    get_settings.cache_clear()
    set_source(None)

    report = evaluate.evaluate(tmp_path / "eval-cache.json")

    assert report["messages"] == 13
    assert report["errors"] == 0
    assert report["ambiguous"] == 1
    assert report["sources"]["heuristic"] == 2, "the two malformed items must skip the provider"
    assert report["sources"]["baseline"] == 11, "a rule run must never be reported as an llm run"
    assert report["category_correct"] == report["scored"]
    assert "cat:ok" in evaluate.render(report)
