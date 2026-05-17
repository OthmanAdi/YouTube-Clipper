"""Stage 1: resolve YouTube metadata via `yt-dlp -J`."""
from __future__ import annotations

import json
import time

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage, YouTubeMeta
from youtube_clipper.util.subprocess_async import run

from .context import PipelineContext

log = get_logger(__name__)


async def resolve(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.RESOLVE.value)
    t0 = time.perf_counter()
    log.info("resolve.start", url=job.input.url)

    yt_dlp = str(ctx.settings.paths.yt_dlp_bin)
    res = await run([yt_dlp, "-J", "--no-warnings", job.input.url], timeout_s=30)
    if not res.ok:
        log.error("resolve.failed", stderr=res.stderr[:500])
        raise RuntimeError(f"yt-dlp -J failed: {res.stderr.strip()[:200]}")

    info = json.loads(res.stdout)
    meta = YouTubeMeta(
        video_id=info.get("id", "unknown"),
        channel=info.get("channel") or info.get("uploader"),
        channel_id=info.get("channel_id"),
        title=info.get("title"),
        duration_full_s=info.get("duration"),
        is_live=bool(info.get("is_live")),
    )
    job.youtube = meta

    metadata_path = job.paths.job_dir / "metadata.json"
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    if meta.is_live:
        raise RuntimeError("Live streams not supported")

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.RESOLVE] = duration_ms
    log.info(
        "resolve.done",
        video_id=meta.video_id,
        title=meta.title,
        duration_ms=duration_ms,
    )
    return job
