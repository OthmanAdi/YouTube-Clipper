import json
from unittest.mock import patch

import pytest

from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_01_resolve import resolve
from youtube_clipper.util.subprocess_async import CompletedProcess


@pytest.mark.asyncio
async def test_resolve_success(make_job, fake_ctx):
    job = make_job()
    fake_info = {"id": "abc", "title": "Hello", "channel": "Ch", "duration": 100}
    fake_out = CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(fake_info), stderr=""
    )
    with patch("youtube_clipper.pipeline.stage_01_resolve.run", return_value=fake_out):
        out = await resolve(job, fake_ctx)
    assert out.youtube is not None
    assert out.youtube.video_id == "abc"
    assert out.youtube.title == "Hello"
    assert (job.paths.job_dir / "metadata.json").exists()
    assert Stage.RESOLVE in out.durations_ms


@pytest.mark.asyncio
async def test_resolve_rejects_live(make_job, fake_ctx):
    job = make_job()
    fake_info = {"id": "abc", "is_live": True}
    fake_out = CompletedProcess(
        args=[], returncode=0, stdout=json.dumps(fake_info), stderr=""
    )
    with patch("youtube_clipper.pipeline.stage_01_resolve.run", return_value=fake_out):
        with pytest.raises(RuntimeError, match="Live"):
            await resolve(job, fake_ctx)


@pytest.mark.asyncio
async def test_resolve_handles_yt_dlp_failure(make_job, fake_ctx):
    job = make_job()
    fake_out = CompletedProcess(
        args=[], returncode=1, stdout="", stderr="Video unavailable"
    )
    with patch("youtube_clipper.pipeline.stage_01_resolve.run", return_value=fake_out):
        with pytest.raises(RuntimeError, match="yt-dlp"):
            await resolve(job, fake_ctx)
