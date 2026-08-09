"""HTTP surface for the inbound corpus. No logic lives here."""

from fastapi import APIRouter

from triage_backend.ingestion import get_source
from triage_backend.schemas import InboundMessage

router = APIRouter(tags=["inbound"])


@router.get("/inbound", response_model=list[InboundMessage])
def list_inbound() -> list[InboundMessage]:
    return get_source().list_messages()
