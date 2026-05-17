import json
from unittest.mock import patch

import pytest

from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_04_transcribe import transcribe


class FakeWord:
    def __init__(self, s, e, w):
        self.start, self.end, self.word = s, e, w


class FakeSeg:
    def __init__(self, s, e, t, words):
        self.start, self.end, self.text, self.words = s, e, t, words


class FakeInfo:
    language = "en"
    language_probability = 0.99
    duration = 84.5


class FakeModel:
    def transcribe(self, *a, **kw):
        seg = FakeSeg(
            0.0,
            2.0,
            " hello world",
            [FakeWord(0.0, 1.0, "hello"), FakeWord(1.0, 2.0, "world")],
        )
        return iter([seg]), FakeInfo()


@pytest.mark.asyncio
async def test_transcribe_writes_outputs(make_job, fake_ctx):
    job = make_job()
    audio = job.paths.job_dir / "audio.mp3"
    audio.write_bytes(b"FAKE")
    job.paths.audio = audio

    with patch(
        "youtube_clipper.pipeline.stage_04_transcribe._load_model",
        return_value=FakeModel(),
    ):
        out = await transcribe(job, fake_ctx)

    assert out.paths.transcript_json is not None
    assert out.paths.transcript_json.exists()
    data = json.loads(out.paths.transcript_json.read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["segments"][0]["text"].strip() == "hello world"
    assert (out.paths.job_dir / "transcript.txt").read_text(encoding="utf-8").startswith(
        "[00:00]"
    )
    assert Stage.TRANSCRIBE in out.durations_ms


@pytest.mark.asyncio
async def test_transcribe_falls_back(make_job, fake_ctx):
    job = make_job()
    audio = job.paths.job_dir / "audio.mp3"
    audio.write_bytes(b"FAKE")
    job.paths.audio = audio

    # First device tried fails, second succeeds.
    fake_ctx.settings.whisper.device = "cuda"
    calls = {"n": 0}

    def fake_loader(model, device, compute_type):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("CUDA OOM")
        return FakeModel()

    with patch(
        "youtube_clipper.pipeline.stage_04_transcribe._load_model",
        side_effect=fake_loader,
    ):
        await transcribe(job, fake_ctx)
    assert calls["n"] >= 2
