from unittest.mock import patch

import pytest

from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_02_download import download
from youtube_clipper.util.subprocess_async import CompletedProcess


@pytest.mark.asyncio
async def test_download_invokes_yt_dlp_with_range(make_job, fake_ctx):
    job = make_job(start_s=23.0, end_s=47.5)
    captured: dict = {}

    async def fake_run(args, *, timeout_s=None, **kw):
        captured["args"] = args
        captured["timeout_s"] = timeout_s
        # yt-dlp picks the container; pretend it landed as .m4a
        (job.paths.job_dir / "audio.raw.m4a").write_bytes(b"FAKE")
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with patch("youtube_clipper.pipeline.stage_02_download.run", new=fake_run):
        out = await download(job, fake_ctx)

    # Range passed correctly:
    assert "--download-sections" in captured["args"]
    idx = captured["args"].index("--download-sections")
    assert captured["args"][idx + 1] == "*23.00-47.50"
    # audio-only format requested:
    assert "-f" in captured["args"]
    assert captured["args"][captured["args"].index("-f") + 1] == "bestaudio"
    # NO force-keyframes and NO extract-audio — those were the stalling combo.
    assert "--force-keyframes-at-cuts" not in captured["args"]
    assert "--extract-audio" not in captured["args"]
    # Per-attempt timeout enforced:
    assert captured["timeout_s"] is not None and captured["timeout_s"] <= 120.0
    assert out.paths.audio_raw is not None
    assert out.paths.audio_raw.exists()
    assert out.paths.audio_raw.suffix == ".m4a"
    assert Stage.DOWNLOAD in out.durations_ms


@pytest.mark.asyncio
async def test_download_retries_then_fails(make_job, fake_ctx):
    fake_ctx.settings.retry.download_max_attempts = 2
    job = make_job()
    calls = {"n": 0}

    async def always_fail(args, *, timeout_s=None, **kw):
        calls["n"] += 1
        return CompletedProcess(args=args, returncode=1, stdout="", stderr="network error")

    with patch("youtube_clipper.pipeline.stage_02_download.run", new=always_fail):
        with pytest.raises(RuntimeError, match="yt-dlp download failed"):
            await download(job, fake_ctx)
    assert calls["n"] == 2  # one initial + one retry (max_attempts=2 means 2 total)
