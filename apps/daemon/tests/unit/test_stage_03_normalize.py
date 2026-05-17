from unittest.mock import patch

import pytest

from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_03_normalize import normalize
from youtube_clipper.util.subprocess_async import CompletedProcess


@pytest.mark.asyncio
async def test_normalize_creates_mp3(make_job, fake_ctx):
    job = make_job()
    raw = job.paths.job_dir / "audio.raw.mp3"
    raw.write_bytes(b"FAKE_RAW")
    job.paths.audio_raw = raw

    async def fake_run(args, **kw):
        (job.paths.job_dir / "audio.mp3").write_bytes(b"NORMALIZED")
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with patch("youtube_clipper.pipeline.stage_03_normalize.run", new=fake_run):
        out = await normalize(job, fake_ctx)
    assert out.paths.audio is not None
    assert out.paths.audio.exists()
    assert Stage.NORMALIZE in out.durations_ms


@pytest.mark.asyncio
async def test_normalize_requires_audio_raw(make_job, fake_ctx):
    job = make_job()
    job.paths.audio_raw = None
    with pytest.raises(RuntimeError, match="audio_raw"):
        await normalize(job, fake_ctx)


@pytest.mark.asyncio
async def test_normalize_propagates_ffmpeg_failure(make_job, fake_ctx):
    job = make_job()
    raw = job.paths.job_dir / "audio.raw.mp3"
    raw.write_bytes(b"FAKE_RAW")
    job.paths.audio_raw = raw

    async def fake_run(args, **kw):
        return CompletedProcess(args=args, returncode=1, stdout="", stderr="bad codec")

    with patch("youtube_clipper.pipeline.stage_03_normalize.run", new=fake_run):
        with pytest.raises(RuntimeError, match="ffmpeg"):
            await normalize(job, fake_ctx)
