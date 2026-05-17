"""POST /clip/{job_id}/website — render a self-contained index.html in the clip folder."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from youtube_clipper.website.builder import WebsiteNotReady, render_website

router = APIRouter()


@router.post("/clip/{job_id}/website")
async def make_website(job_id: str, request: Request):
    runner = request.app.state.runner
    settings = request.app.state.settings
    job = runner.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    if job.state.value != "done":
        raise HTTPException(409, f"job is not done (state={job.state.value})")
    try:
        path = render_website(job, whisper_model=settings.whisper.model)
    except WebsiteNotReady as ex:
        raise HTTPException(409, str(ex)) from ex
    return {"path": str(path)}
