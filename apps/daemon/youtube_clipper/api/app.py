"""FastAPI app factory + lifespan that owns the pipeline runner + job bus."""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from youtube_clipper.config import load_settings
from youtube_clipper.logging import configure_logging
from youtube_clipper.pipeline.runner import JobBus, PipelineRunner


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings.paths.logs_dir)
    bus = JobBus()
    runner = PipelineRunner(settings, bus)
    runner.start()
    app.state.settings = settings
    app.state.runner = runner
    app.state.bus = bus
    try:
        yield
    finally:
        await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Clipper Daemon", lifespan=lifespan)
    # CORS: the Chrome extension calls from a chrome-extension:// origin.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from .routes_clip import router as clip_router
    from .routes_health import router as health_router
    from .ws_events import router as ws_router

    app.include_router(clip_router)
    app.include_router(health_router)
    app.include_router(ws_router)
    return app


app = create_app()
