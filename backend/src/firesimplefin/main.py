"""Application entry and route wiring."""

import logging
import os
import urllib.parse
from pathlib import Path

import uvicorn
from fastapi import FastAPI
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse
from starlette.staticfiles import StaticFiles

from firesimplefin.api import firefly, health, simplefin
from firesimplefin.background import get_running_count
from firesimplefin.config import settings

logger = logging.getLogger("firesimplefin")

app = FastAPI(
    title="Fire SimpleFIN API",
    version="0.1.0",
    description="Connect bank via SimpleFIN, upload transactions to Firefly III",
)


class RunningJobsHeaderMiddleware(BaseHTTPMiddleware):
    """Add X-Running-Background-Jobs to every response."""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers["X-Running-Background-Jobs"] = str(get_running_count())
        return response


app.add_middleware(RunningJobsHeaderMiddleware)
app.include_router(health.router, prefix="/api", tags=["health"])
app.include_router(simplefin.router, prefix="/api", tags=["simplefin"])
app.include_router(firefly.router, prefix="/api", tags=["firefly"])

if settings.frontend_dist:
    dist = Path(settings.frontend_dist)
    if dist.is_dir():
        app.mount("/", StaticFiles(directory=str(dist), html=True), name="frontend")

        @app.exception_handler(StarletteHTTPException)
        async def spa_fallback(request: Request, exc: StarletteHTTPException):
            if exc.status_code == 404 and not request.url.path.startswith("/api"):
                index = dist / "index.html"
                if index.is_file():
                    return FileResponse(str(index))
            raise exc


def serve() -> None:
    """Run the web server."""
    logging.basicConfig(level=logging.INFO)
    listen_url = os.getenv("LISTEN_URL", "0.0.0.0:8080")
    parsed = urllib.parse.urlparse("//" + listen_url)
    host = parsed.hostname or "0.0.0.0"
    port = int(parsed.port or 8080)
    uvicorn.run(app, host=host, port=port, log_level="info")
