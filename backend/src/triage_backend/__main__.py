"""`python -m triage_backend` — production-shaped entrypoint.

Honours `PORT` from the environment (this is what the container CMD uses).
`fastapi dev --port N` takes its port from the CLI flag instead.
"""

from __future__ import annotations

import uvicorn

from triage_backend.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run("triage_backend.main:app", host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
