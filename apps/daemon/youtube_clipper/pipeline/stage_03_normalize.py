"""Stage 3: ffmpeg normalize → mono 16 kHz mp3 ready for Whisper."""
from __future__ import annotations

import time

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage
from youtube_clipper.util.subprocess_async import run

from .context import PipelineContext

log = get_logger(__name__)


async def normalize(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.NORMALIZE.value)
    t0 = time.perf_counter()
    raw = job.paths.audio_raw
    if raw is None or not raw.exists():
        raise RuntimeError("normalize requires audio_raw from stage 2")

    out = job.paths.job_dir / "audio.mp3"
    args = [
        str(ctx.settings.paths.ffmpeg_bin),
        "-y",
        "-i", str(raw),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "libmp3lame",
        "-b:a", "64k",
        str(out),
    ]
    log.info("normalize.start", input=str(raw), output=str(out))
    res = await run(args, timeout_s=120)
    if not res.ok:
        raise RuntimeError(f"ffmpeg failed: {res.stderr.strip()[:200]}")
    if not out.exists():
        raise RuntimeError(f"ffmpeg reported success but produced no output: {out}")

    job.paths.audio = out
    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.NORMALIZE] = duration_ms
    log.info("normalize.done", bytes=out.stat().st_size, duration_ms=duration_ms)
    return job
