"""Runtime configuration, loaded from environment / .env.

`get_settings()` is cached rather than a module-level singleton so tests (and
anything that needs to flip an env var at runtime) can call
`get_settings.cache_clear()` and get a freshly-read `Settings`.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BACKEND_ROOT / "data"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=BACKEND_ROOT / ".env", extra="ignore")

    anthropic_api_key: str = ""
    openai_api_key: str = ""
    model_id: str = "claude-haiku-4-5-20251001"
    openai_model_id: str = "gpt-4o-mini"

    # "anthropic" | "openai" | "stub" | "auto".
    llm_provider: str = "auto"

    # Per-request timeout for an LLM call, and how many times the vendor SDK
    # may retry at the transport layer before we treat it as a failed row.
    llm_timeout_seconds: float = 30.0
    llm_transport_retries: int = 1

    # Comma-separated browser origins allowed to call the API directly. The
    # Vite dev proxy makes the app same-origin, so this only matters for
    # direct/cross-origin callers.
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    # Port used by `python -m triage_backend` (and the container CMD).
    # `fastapi dev --port N` takes its port from the CLI flag instead.
    port: int = 8787

    # Where the inbound corpus and the triage cache live. Overridable so tests
    # and alternative deployments don't write into the checked-out data dir.
    inbound_path: Path = DATA_DIR / "inbound.json"
    results_path: Path = DATA_DIR / "results.json"

    # Demo aid: forcing this inbound id to fail lets the API-error path be
    # triggered on demand (e.g. while recording a walkthrough) instead of
    # hoping a real transient failure happens live.
    triage_force_error_id: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
