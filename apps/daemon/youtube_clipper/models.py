"""Core data model: Job, Stage, ClipInput, related types."""
from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path

from pydantic import BaseModel, Field


class Stage(StrEnum):
    RESOLVE = "resolve"
    DOWNLOAD = "download"
    NORMALIZE = "normalize"
    TRANSCRIBE = "transcribe"
    SUMMARIZE = "summarize"
    WRITE_NOTE = "write_note"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.RESOLVE,
    Stage.DOWNLOAD,
    Stage.NORMALIZE,
    Stage.TRANSCRIBE,
    Stage.SUMMARIZE,
    Stage.WRITE_NOTE,
)


class JobState(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ClipInput(BaseModel):
    url: str
    start_s: float
    end_s: float
    summarizer: str = Field(pattern=r"^(azure|ollama|qwen)$")
    video_title: str | None = None
    channel_name: str | None = None
    # Optional per-clip output dir override. None = use config.paths.output_dir (default).
    output_dir: Path | None = None
    # Summary intensity. "standard" = default; "quick" = terse; "deep" = thorough.
    detail: str = Field(default="standard", pattern=r"^(quick|standard|deep)$")
    # Optional per-clip model override (e.g. "gpt-5-mini", "qwen-turbo"). None = use config default
    # for the chosen summarizer. Lets the popup pick cheap/balanced/best per clip without changing
    # the global config.
    model: str | None = None


class ClipPaths(BaseModel):
    job_dir: Path
    audio_raw: Path | None = None
    audio: Path | None = None
    transcript_json: Path | None = None
    transcript_txt: Path | None = None
    note: Path | None = None
    raw_log: Path | None = None
    manifest: Path


class YouTubeMeta(BaseModel):
    video_id: str
    channel: str | None = None
    channel_id: str | None = None
    title: str | None = None
    duration_full_s: float | None = None
    is_live: bool = False


class SummaryArtifact(BaseModel):
    tldr: str
    bullets: list[str]
    notable_quotes: list[str] = Field(default_factory=list)
    tags: list[str]
    backend: str


class Job(BaseModel):
    job_id: str
    clip_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: JobState = JobState.PENDING
    current_stage: Stage | None = None
    stages_done: list[Stage] = Field(default_factory=list)
    failed_at_stage: Stage | None = None
    error_class: str | None = None
    error_message: str | None = None
    retry_count: dict[Stage, int] = Field(default_factory=dict)
    input: ClipInput
    paths: ClipPaths
    durations_ms: dict[Stage, int] = Field(default_factory=dict)
    summarizer_used: str | None = None
    youtube: YouTubeMeta | None = None
    summary: SummaryArtifact | None = None


def next_stage(done: list[Stage]) -> Stage | None:
    for s in STAGE_ORDER:
        if s not in done:
            return s
    return None
