"""FastAPI entrypoint: uvicorn app.main:app"""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api import artifacts, download, health, sources, split
from app.auth import ApiKeyMiddleware
from app.config import Settings, get_settings
from app.errors import install_error_handlers
from app.logging_setup import setup_logging
from app.services import retention
from app.services.binaries import detect_versions

log = logging.getLogger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings: Settings = app.state.settings
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    app.state.binaries = detect_versions(settings.ytdlp_bin, settings.ffmpeg_bin)
    log.info(
        "media-service started",
        extra={
            "data_dir": str(settings.data_dir),
            "audio_format": settings.audio_format,
            "auth_enabled": settings.auth_enabled,
        },
    )
    sweeper = asyncio.create_task(_retention_loop(settings))
    try:
        yield
    finally:
        sweeper.cancel()
        log.info("media-service stopped")


async def _retention_loop(settings: Settings) -> None:
    if settings.retention_sweep_minutes == 0:
        return
    while True:
        try:
            await asyncio.to_thread(retention.sweep, settings)
        except Exception:  # keep the loop alive; the next tick retries
            log.exception("retention sweep failed")
        await asyncio.sleep(settings.retention_sweep_minutes * 60)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    setup_logging(settings.log_level)

    app = FastAPI(
        title="Video Digest Media Service",
        version="0.1.0",
        lifespan=_lifespan,
        responses={
            401: {"description": "Missing or invalid API key"},
            422: {"description": "Validation error"},
        },
    )
    app.state.settings = settings
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(ApiKeyMiddleware, api_key=settings.api_key)
    install_error_handlers(app)
    app.include_router(health.router)
    app.include_router(sources.router)
    app.include_router(download.router)
    app.include_router(split.router)
    app.include_router(artifacts.router)
    return app


app = create_app()
