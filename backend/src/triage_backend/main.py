"""FastAPI application wiring. Routers in, middleware on, nothing else."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from triage_backend.config import get_settings
from triage_backend.routes import inbound, triage


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Inbound Triage Assistant API",
        summary="Classify one inbound message at a time into summary / category / priority.",
        version="1.0.0",
    )

    # The Vite dev server proxies /api here, so the browser is same-origin and
    # CORS is not exercised in normal use. Kept narrow so hitting the API
    # directly (curl, a non-proxied port) still works without opening it up.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    app.include_router(inbound.router, prefix="/api")
    app.include_router(triage.router, prefix="/api")

    @app.get("/api/health", tags=["ops"])
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
