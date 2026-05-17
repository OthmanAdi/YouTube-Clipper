"""Stage 2: download just the audio range via `yt-dlp --download-sections`.

Design notes:
- We request `-f bestaudio` (no video tracks). Smaller download, no transcoding pressure.
- We deliberately do NOT pass `--force-keyframes-at-cuts`: on some YouTube HLS sources it makes
  yt-dlp spawn ffmpeg in a re-encode pipeline that can stall for minutes. The boundary noise it
  removes is irrelevant to Whisper accuracy, and stage 3 normalizes the audio anyway.
- We deliberately do NOT pass `--extract-audio --audio-format mp3`: that runs another ffmpeg
  encode inside yt-dlp. Stage 3 does mp3 conversion under our own timeout control.
- Per-attempt timeout is 90s. The first attempt with a sane network finishes in <10s for most
  ranges. If it stalls, we want to fail fast and retry rather than burn 5 minutes.
"""
from __future__ import annotations

import time

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage
from youtube_clipper.util.subprocess_async import run

from .context import PipelineContext

log = get_logger(__name__)

PER_ATTEMPT_TIMEOUT_S = 90.0


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
        "-f", "bestaudio",
        "--download-sections", section,
        "--no-part",
        "-o", out_template,
        job.input.url,
    ]
    log.info("download.start", section=section, url=job.input.url)

    last_err: str | None = None
    last_returncode: int | None = None
    for attempt in range(1, ctx.settings.retry.download_max_attempts + 1):
        await ctx.progress(Stage.DOWNLOAD, 0.0, f"yt-dlp attempt {attempt}/{ctx.settings.retry.download_max_attempts}")
        try:
            res = await run(args, timeout_s=PER_ATTEMPT_TIMEOUT_S)
        except TimeoutError:
            last_err = f"yt-dlp timeout after {PER_ATTEMPT_TIMEOUT_S}s"
            log.warning("download.timeout", attempt=attempt, timeout_s=PER_ATTEMPT_TIMEOUT_S)
            continue
        if res.ok:
            last_err = None
            last_returncode = 0
            break
        last_err = res.stderr.strip()[:500] or res.stdout.strip()[:500] or f"returncode {res.returncode}"
        last_returncode = res.returncode
        log.warning("download.retry", attempt=attempt, returncode=res.returncode, stderr=last_err)
    if last_err is not None:
        raise RuntimeError(f"yt-dlp download failed (rc={last_returncode}): {last_err}")

    # yt-dlp picks the extension automatically (e.g. .m4a, .webm, .opus). Find it.
    candidates = sorted(job.paths.job_dir.glob("audio.raw.*"))
    if not candidates:
        raise RuntimeError("download succeeded but no audio.raw.* file landed on disk")
    raw = candidates[0]
    job.paths.audio_raw = raw

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.DOWNLOAD] = duration_ms
    log.info(
        "download.done",
        bytes=raw.stat().st_size,
        ext=raw.suffix,
        duration_ms=duration_ms,
        path=str(raw),
    )
    return job
