import json
from unittest.mock import patch

import pytest

from youtube_clipper.adapters.base import SummaryResult
from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_05_summarize import summarize


class StubAdapter:
    def __init__(self, name="stub/x"):
        self.name = name

    async def summarize(self, transcript, *, language, detail="standard"):
        return SummaryResult(
            tldr=f"An idea worth quoting (detail={detail}).",
            bullets=["one", "two"],
            tags=["tag"],
            backend=self.name,
            raw_response={"language": language, "detail": detail},
        )


@pytest.mark.asyncio
async def test_summarize_writes_summary(make_job, fake_ctx):
    job = make_job()
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [{"start": 0, "end": 1, "text": "hello", "words": []}],
            }
        ),
        encoding="utf-8",
    )
    job.paths.transcript_json = tj

    with patch(
        "youtube_clipper.pipeline.stage_05_summarize._pick_adapter",
        return_value=StubAdapter(),
    ):
        out = await summarize(job, fake_ctx)

    assert out.summary is not None
    assert "An idea worth quoting" in out.summary.tldr
    assert (job.paths.job_dir / "summary.json").exists()
    assert Stage.SUMMARIZE in out.durations_ms
    assert out.summarizer_used == "stub/x"


@pytest.mark.asyncio
async def test_summarize_retries_then_succeeds(make_job, fake_ctx):
    fake_ctx.settings.retry.summarize_max_attempts = 2
    job = make_job()
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(
        json.dumps({"language": "en", "segments": [{"start": 0, "end": 1, "text": "h", "words": []}]}),
        encoding="utf-8",
    )
    job.paths.transcript_json = tj

    class FlakyAdapter:
        name = "flaky/x"
        calls = 0

        async def summarize(self, transcript, *, language, detail="standard"):
            FlakyAdapter.calls += 1
            if FlakyAdapter.calls == 1:
                raise RuntimeError("temporary 429")
            return SummaryResult(
                tldr="ok",
                bullets=["b"],
                tags=[],
                backend=self.name,
                raw_response={},
            )

    with patch(
        "youtube_clipper.pipeline.stage_05_summarize._pick_adapter",
        return_value=FlakyAdapter(),
    ):
        with patch("youtube_clipper.pipeline.stage_05_summarize.asyncio.sleep", new=__noop_sleep):
            out = await summarize(job, fake_ctx)
    assert out.summary is not None
    assert FlakyAdapter.calls == 2


async def __noop_sleep(_):
    return None
