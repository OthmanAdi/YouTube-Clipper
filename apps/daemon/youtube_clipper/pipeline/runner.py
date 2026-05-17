"""Pipeline orchestrator: builds jobs, runs the 6-stage chain on a worker, publishes events."""
from __future__ import annotations

import asyncio
import os
from contextlib import suppress
from datetime import date
from pathlib import Path

from youtube_clipper.config import AppSettings
from youtube_clipper.logging import bind_job, clear_log_context, get_logger
from youtube_clipper.models import (
    STAGE_ORDER,
    ClipInput,
    ClipPaths,
    Job,
    JobState,
    Stage,
)
from youtube_clipper.pipeline.context import PipelineContext
from youtube_clipper.pipeline.stage_01_resolve import resolve
from youtube_clipper.pipeline.stage_02_download import download
from youtube_clipper.pipeline.stage_03_normalize import normalize
from youtube_clipper.pipeline.stage_04_transcribe import transcribe
from youtube_clipper.pipeline.stage_05_summarize import summarize
from youtube_clipper.pipeline.stage_06_write_note import write_note
from youtube_clipper.slug import build_clip_id, build_job_dir_name, next_clip_suffix
from youtube_clipper.util.raw_log import build_raw_log

log = get_logger(__name__)

STAGE_FNS = {
    Stage.RESOLVE: resolve,
    Stage.DOWNLOAD: download,
    Stage.NORMALIZE: normalize,
    Stage.TRANSCRIBE: transcribe,
    Stage.SUMMARIZE: summarize,
    Stage.WRITE_NOTE: write_note,
}


class JobBus:
    """In-memory hub of per-job asyncio.Queue subscribers — WS events fan out from here."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue(maxsize=256)
            self._subs.setdefault(job_id, []).append(q)
            return q

    async def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            if job_id in self._subs and q in self._subs[job_id]:
                self._subs[job_id].remove(q)

    async def publish(self, job_id: str, message: dict) -> None:
        async with self._lock:
            subs = list(self._subs.get(job_id, []))
        for q in subs:
            with suppress(asyncio.QueueFull):
                q.put_nowait(message)


def _atomic_write_manifest(path: Path, job: Job) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def build_new_job(input: ClipInput, settings: AppSettings) -> Job:
    today = date.today()
    # Per-clip override beats the default output_dir.
    base_output_dir = input.output_dir if input.output_dir is not None else settings.paths.output_dir
    base_output_dir.mkdir(parents=True, exist_ok=True)
    suffix = next_clip_suffix(base_output_dir, today)
    clip_id = build_clip_id(today, suffix)
    job_id = f"j_{clip_id.replace('-', '_')}"
    channel = input.channel_name or "unknown"
    title = input.video_title or "untitled"
    dir_name = build_job_dir_name(today, suffix, channel, title)
    job_dir = base_output_dir / dir_name
    job_dir.mkdir(parents=True, exist_ok=True)
    return Job(
        job_id=job_id,
        clip_id=clip_id,
        input=input,
        paths=ClipPaths(job_dir=job_dir, manifest=job_dir / "manifest.json"),
    )


class PipelineRunner:
    def __init__(self, settings: AppSettings, bus: JobBus) -> None:
        self.settings = settings
        self.bus = bus
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(
                self._worker_loop(), name="pipeline-worker"
            )

    async def stop(self) -> None:
        if self._task is not None:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def enqueue(self, job: Job) -> None:
        self._jobs[job.job_id] = job
        job.state = JobState.QUEUED
        _atomic_write_manifest(job.paths.manifest, job)
        await self._queue.put(job)
        await self.bus.publish(job.job_id, {"type": "enqueued", "job_id": job.job_id})

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._run(job)
            except Exception as ex:
                log.error("pipeline.unhandled", error=str(ex))

    async def _run(self, job: Job) -> None:
        bind_job(job.job_id, job.clip_id)
        job.state = JobState.RUNNING
        await self.bus.publish(
            job.job_id, {"type": "running", "job_id": job.job_id}
        )

        async def progress(stage: Stage, pct: float, msg: str) -> None:
            await self.bus.publish(
                job.job_id,
                {
                    "type": "progress",
                    "job_id": job.job_id,
                    "stage": stage.value,
                    "percent": pct,
                    "message": msg,
                },
            )

        ctx = PipelineContext(settings=self.settings, progress=progress)

        for stage in STAGE_ORDER:
            if stage in job.stages_done:
                continue
            job.current_stage = stage
            _atomic_write_manifest(job.paths.manifest, job)
            await self.bus.publish(
                job.job_id,
                {"type": "stage_start", "job_id": job.job_id, "stage": stage.value},
            )
            try:
                fn = STAGE_FNS[stage]
                await fn(job, ctx)
                job.stages_done.append(stage)
                _atomic_write_manifest(job.paths.manifest, job)
                await self.bus.publish(
                    job.job_id,
                    {
                        "type": "stage_done",
                        "job_id": job.job_id,
                        "stage": stage.value,
                        "duration_ms": job.durations_ms.get(stage, 0),
                    },
                )
            except Exception as ex:
                job.state = JobState.FAILED
                job.failed_at_stage = stage
                job.error_class = type(ex).__name__
                job.error_message = str(ex)
                _atomic_write_manifest(job.paths.manifest, job)
                log.error("pipeline.failed", stage=stage.value, error=str(ex))
                await self.bus.publish(
                    job.job_id,
                    {
                        "type": "failed",
                        "job_id": job.job_id,
                        "stage": stage.value,
                        "error_class": job.error_class,
                        "error_message": job.error_message,
                    },
                )
                clear_log_context()
                raw_log_path = job.paths.job_dir / "raw.log"
                build_raw_log(self.settings.paths.logs_dir, job.job_id, raw_log_path)
                job.paths.raw_log = raw_log_path
                _atomic_write_manifest(job.paths.manifest, job)
                return

        job.state = JobState.DONE
        job.current_stage = None
        _atomic_write_manifest(job.paths.manifest, job)
        clear_log_context()

        raw_log_path = job.paths.job_dir / "raw.log"
        build_raw_log(self.settings.paths.logs_dir, job.job_id, raw_log_path)
        job.paths.raw_log = raw_log_path
        _atomic_write_manifest(job.paths.manifest, job)

        await self.bus.publish(
            job.job_id,
            {"type": "done", "job_id": job.job_id, "note": str(job.paths.note or "")},
        )
