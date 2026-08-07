"""HTTP contract. The route layer is thin, so these tests check wiring and
status codes rather than re-testing the pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from triage_backend import routing
from triage_backend.classification.base import TriageError, TriageOutcome
from triage_backend.config import Settings
from triage_backend.main import create_app
from triage_backend.schemas import InboundMessage, TriageResult

GOOD = TriageResult(
    summary="Business seller wants help investing sale proceeds.",
    category="prospect",
    priority="medium",
    next_action="Send the intro pack.",
)


@pytest.fixture
def client(isolated_settings: Settings) -> Iterator[TestClient]:
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health(client: TestClient) -> None:
    assert client.get("/api/health").json() == {"status": "ok"}


def test_inbound_returns_every_message_in_order(
    client: TestClient, sample_messages: list[dict]
) -> None:
    response = client.get("/api/inbound")
    assert response.status_code == 200
    assert [item["id"] for item in response.json()] == [m["id"] for m in sample_messages]


def test_triage_with_no_api_key_is_a_200_with_an_error_body(client: TestClient) -> None:
    """The app must start and serve with no key configured. A missing key is a
    per-row error the UI can render and retry, not a 500."""
    response = client.post("/api/triage/inb-001")
    assert response.status_code == 200
    body = response.json()
    assert body["error"] is True
    assert body["result"] is None
    assert "No LLM API key configured" in body["error_message"]


def test_triage_of_a_malformed_message_works_with_no_api_key(client: TestClient) -> None:
    body = client.post("/api/triage/inb-010").json()
    assert body["source"] == "heuristic"
    assert body["result"]["category"] == "noise_other"


def test_unknown_message_is_404(client: TestClient) -> None:
    response = client.post("/api/triage/inb-does-not-exist")
    assert response.status_code == 404
    assert "inb-does-not-exist" in response.json()["detail"]


@pytest.mark.parametrize("message_id", ["../../etc/passwd", "..%2F..%2Fetc", "*", "%00"])
def test_hostile_ids_are_404_not_a_file_read(client: TestClient, message_id: str) -> None:
    assert client.post(f"/api/triage/{message_id}").status_code in (404, 405)


def test_refresh_busts_the_cache(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def classify(message: InboundMessage) -> TriageOutcome:
        calls.append(message.id)
        return TriageOutcome(result=GOOD, provider="anthropic")

    monkeypatch.setattr(routing, "classify", classify)

    assert client.post("/api/triage/inb-001").json()["source"] == "llm"
    assert client.post("/api/triage/inb-001").json()["source"] == "cache"
    assert client.post("/api/triage/inb-001?refresh=true").json()["source"] == "llm"
    assert len(calls) == 2


def test_one_failing_row_does_not_take_the_list_down(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    def classify(message: InboundMessage) -> TriageOutcome:
        if message.id == "inb-001":
            raise TriageError("simulated upstream failure")
        return TriageOutcome(result=GOOD, provider="anthropic")

    monkeypatch.setattr(routing, "classify", classify)

    statuses = {
        item["id"]: client.post(f"/api/triage/{item['id']}").json()
        for item in client.get("/api/inbound").json()
    }
    assert statuses["inb-001"]["error"] is True
    assert statuses["inb-002"]["error"] is False


def test_response_body_matches_the_published_schema(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        routing, "classify", lambda message: TriageOutcome(result=GOOD, provider="anthropic")
    )
    body = client.post("/api/triage/inb-001").json()
    assert set(body) == {"id", "result", "source", "flags", "error", "error_message"}
    assert set(body["result"]) == {"summary", "category", "priority", "next_action"}


def test_openapi_document_is_generated(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()
    assert "/api/triage/{message_id}" in schema["paths"]
    assert "/api/inbound" in schema["paths"]


def test_an_edited_corpus_is_picked_up_without_a_restart(
    client: TestClient, isolated_settings: Settings, sample_messages: list[dict]
) -> None:
    extra = {**sample_messages[0], "id": "inb-999", "subject": "Added later"}
    isolated_settings.inbound_path.write_text(
        json.dumps([*sample_messages, extra]), encoding="utf-8"
    )
    ids = [item["id"] for item in client.get("/api/inbound").json()]
    assert "inb-999" in ids
