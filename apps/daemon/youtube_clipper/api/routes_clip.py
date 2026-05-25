"""POST /clip + GET /jobs/{id} — enqueue extractions, inspect job state."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from youtube_clipper.models import ClipInput
from youtube_clipper.pipeline.runner import build_new_job

router = APIRouter()


class ClipRequest(BaseModel):
    url: str
    start_s: float
    end_s: float
    summarizer: str = Field(pattern=r"^(azure|ollama|qwen)$")
    video_title: str | None = None
    channel_name: str | None = None
    # Optional override of the output directory. Must be an absolute path.
    output_dir: str | None = None
    # Summary intensity. quick = terse, deep = thorough.
    detail: str = Field(default="standard", pattern=r"^(quick|standard|deep)$")
    # Optional per-clip model override (e.g. "gpt-5-mini", "qwen-turbo"). None = use config default
    # for the chosen summarizer.
    model: str | None = None


@router.post("/clip")
async def create_clip(req: ClipRequest, request: Request):
    settings = request.app.state.settings
    length = req.end_s - req.start_s
    if length < settings.ux.min_range_seconds:
        raise HTTPException(400, f"range too short (min {settings.ux.min_range_seconds}s)")
    if length > settings.ux.max_range_seconds:
        raise HTTPException(400, f"range too long (max {settings.ux.max_range_seconds}s)")

    output_dir: Path | None = None
    if req.output_dir:
        candidate = Path(req.output_dir).expanduser()
        if not candidate.is_absolute():
            raise HTTPException(400, "output_dir must be an absolute path")
        output_dir = candidate

    input = ClipInput(
        url=req.url,
        start_s=req.start_s,
        end_s=req.end_s,
        summarizer=req.summarizer,
        video_title=req.video_title,
        channel_name=req.channel_name,
        output_dir=output_dir,
        detail=req.detail,
        model=req.model,
    )
    job = build_new_job(input, settings)
    await request.app.state.runner.enqueue(job)
    return {"job_id": job.job_id, "clip_id": job.clip_id, "job_dir": str(job.paths.job_dir)}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    job = request.app.state.runner.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.model_dump(mode="json")
