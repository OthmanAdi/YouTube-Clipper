"""Shared test fixtures for unit + integration tests."""
from __future__ import annotations

from pathlib import Path

import pytest

from youtube_clipper.config import (
    AppSettings,
    AzureSummarizerSettings,
    DaemonSettings,
    OllamaSummarizerSettings,
    PathsSettings,
    RetrySettings,
    SummarizerSettings,
    UxSettings,
    WhisperSettings,
)
from youtube_clipper.models import ClipInput, ClipPaths, Job
from youtube_clipper.pipeline.context import PipelineContext


@pytest.fixture
def fake_settings(tmp_path: Path) -> AppSettings:
    return AppSettings(
        paths=PathsSettings(
            output_dir=tmp_path,
            logs_dir=tmp_path,
            ffmpeg_bin=Path("ffmpeg"),
            yt_dlp_bin=Path("yt-dlp"),
        ),
        daemon=DaemonSettings(),
        whisper=WhisperSettings(device="cpu", compute_type="int8", model="tiny"),
        summarizer=SummarizerSettings(
            azure=AzureSummarizerSettings(
                endpoint="https://x.test", api_key="k", model="gpt-4o-mini"
            ),
            ollama=OllamaSummarizerSettings(),
        ),
        retry=RetrySettings(download_max_attempts=1, summarize_max_attempts=1),
        ux=UxSettings(),
    )


@pytest.fixture
def fake_ctx(fake_settings) -> PipelineContext:
    async def noop_progress(stage, pct, msg):
        return None

    return PipelineContext(settings=fake_settings, progress=noop_progress)


@pytest.fixture
def make_job(tmp_path: Path):
    def _factory(*, start_s: float = 0.0, end_s: float = 10.0, summarizer: str = "azure") -> Job:
        job_dir = tmp_path / "clip"
        job_dir.mkdir(parents=True, exist_ok=True)
        return Job(
            job_id="j1",
            clip_id="2026-05-17-001",
            input=ClipInput(
                url="https://www.youtube.com/watch?v=abc",
                start_s=start_s,
                end_s=end_s,
                summarizer=summarizer,
            ),
            paths=ClipPaths(job_dir=job_dir, manifest=job_dir / "manifest.json"),
        )

    return _factory
