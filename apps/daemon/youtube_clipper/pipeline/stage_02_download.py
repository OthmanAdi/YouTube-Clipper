"""Stage 2: download the audio chunk via `yt-dlp --download-sections`."""
from __future__ import annotations

import time

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage
from youtube_clipper.util.subprocess_async import run

from .context import PipelineContext

log = get_logger(__name__)


def _fmt_time(seconds: float) -> str:
    return f"{seconds:.2f}"


async def download(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.DOWNLOAD.value)
    t0 = time.perf_counter()
    s = job.input.start_s
    e = job.input.end_s
    section = f"*{_fmt_time(s)}-{_fmt_time(e)}"
    out_template = str(job.paths.job_dir / "audio.raw.%(ext)s")

    args = [
        str(ctx.settings.paths.yt_dlp_bin),
        "--no-warnings",
        "--no-playlist",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_template,
        job.input.url,
    ]
    log.info("download.start", section=section, url=job.input.url)

    last_err: str | None = None
    for attempt in range(1, ctx.settings.retry.download_max_attempts + 1):
        res = await run(args, timeout_s=300)
        if res.ok:
            last_err = None
            break
        last_err = res.stderr.strip()[:500]
        log.warning("download.retry", attempt=attempt, stderr=last_err)
    if last_err is not None:
        raise RuntimeError(f"yt-dlp download failed: {last_err}")

    raw = job.paths.job_dir / "audio.raw.mp3"
    if not raw.exists():
        candidates = sorted(job.paths.job_dir.glob("audio.raw.*"))
        if not candidates:
            raise RuntimeError("download produced no file")
        raw = candidates[0]
    job.paths.audio_raw = raw

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.DOWNLOAD] = duration_ms
    log.info(
        "download.done",
        bytes=raw.stat().st_size,
        duration_ms=duration_ms,
        path=str(raw),
    )
    return job
