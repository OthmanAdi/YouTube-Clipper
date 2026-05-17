"""GET /health — daemon liveness + summarizer availability snapshot."""
from __future__ import annotations

from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    s = request.app.state.settings
    return {
        "status": "ok",
        "version": "0.1.0",
        "summarizers": {
            "azure": s.summarizer.azure.enabled,
            "ollama": s.summarizer.ollama.enabled,
        },
        "whisper_model": s.whisper.model,
    }
