"""HTTP surface for triage. Thin by design — the decision table lives in
`triage_backend.routing`, so it can be tested without a web server."""

from fastapi import APIRouter, HTTPException, Query

from triage_backend import routing
from triage_backend.ingestion import get_source
from triage_backend.schemas import TriageResponse

router = APIRouter(tags=["triage"])


@router.post("/triage/{message_id}", response_model=TriageResponse)
def triage_one(
    message_id: str,
    refresh: bool = Query(
        default=False,
        description="Ignore any cached result and re-run the pipeline for this message.",
    ),
) -> TriageResponse:
    message = get_source().get_message(message_id)
    if message is None:
        raise HTTPException(status_code=404, detail=f"no inbound message with id {message_id!r}")

    cache = routing.get_cache()
    if refresh:
        cache.forget(message_id)
    return routing.triage(message, cache=cache)
