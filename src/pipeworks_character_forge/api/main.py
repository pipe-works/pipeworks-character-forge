"""FastAPI application for the PipeWorks Character Forge.

PR 1 surface only: ``/`` serves a placeholder page, ``/api/health`` is a
liveness probe, and ``/api/slots`` returns the canonical 25-slot
catalog. Generation endpoints are added in PR 3.
"""

from __future__ import annotations

import logging

import uvicorn
from fastapi import FastAPI
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

from pipeworks_character_forge import __version__
from pipeworks_character_forge.api.services import slot_catalog
from pipeworks_character_forge.core.config import config

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    app = FastAPI(
        title="PipeWorks Character Forge",
        version=__version__,
        docs_url="/api/docs",
        redoc_url=None,
    )

    app.mount(
        "/static",
        StaticFiles(directory=str(config.static_dir)),
        name="static",
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "version": __version__}

    @app.get("/api/slots")
    def slots() -> dict[str, object]:
        catalog = slot_catalog.load_catalog()
        return {
            "schema_version": catalog.schema_version,
            "source_prompt": catalog.source_prompt,
            "intermediate": catalog.intermediate.model_dump(),
            "slots": [s.model_dump() for s in slot_catalog.list_slots()],
        }

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        index_html = (config.templates_dir / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(index_html)

    return app


app = create_app()


def main() -> None:
    """Console-script entry point used by the systemd unit."""
    logging.basicConfig(level=getattr(logging, config.log_level.upper(), logging.INFO))
    uvicorn.run(
        "pipeworks_character_forge.api.main:app",
        host=config.server_host,
        port=config.server_port,
        log_level=config.log_level.lower(),
    )


if __name__ == "__main__":
    main()
