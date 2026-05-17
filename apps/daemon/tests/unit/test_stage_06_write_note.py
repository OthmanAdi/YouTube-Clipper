import json

import pytest

from youtube_clipper.models import Stage, SummaryArtifact, YouTubeMeta
from youtube_clipper.pipeline.stage_06_write_note import write_note


def _seed(job):
    job.input.start_s = 23.0
    job.input.end_s = 107.5
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {"start": 23.0, "end": 30.0, "text": " hello there", "words": []},
                    {"start": 30.0, "end": 60.0, "text": " second part of the clip", "words": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    job.paths.transcript_json = tj

    aud = job.paths.job_dir / "audio.mp3"
    aud.write_bytes(b"X" * 1024)
    job.paths.audio = aud

    job.summary = SummaryArtifact(
        tldr="Idea.", bullets=["b1", "b2"], notable_quotes=["one verbatim quote"],
        tags=["ai"],
        backend="azure-foundry/gpt-4o-mini",
    )
    job.summarizer_used = "azure-foundry/gpt-4o-mini"
    job.youtube = YouTubeMeta(
        video_id="abc",
        title="A Title",
        channel="A Channel",
        channel_id="UCabc",
        duration_full_s=600,
    )
    for s in (Stage.RESOLVE, Stage.DOWNLOAD, Stage.NORMALIZE, Stage.TRANSCRIBE, Stage.SUMMARIZE):
        job.durations_ms[s] = 100
    return job


@pytest.mark.asyncio
async def test_write_note_fresh(make_job, fake_ctx):
    job = _seed(make_job())
    await write_note(job, fake_ctx)
    out = (job.paths.job_dir / "note.md").read_text(encoding="utf-8")
    assert "# A Title" in out
    assert "**00:23 → 01:47**" in out
    assert "## TL;DR" in out
    assert "- b1" in out
    assert "## Notable Quotes" in out
    assert "one verbatim quote" in out
    assert "[A Channel](https://www.youtube.com/channel/UCabc)" in out
    assert "<audio controls" in out
    assert "## My Notes" in out
    assert "Summarized by: azure-foundry/gpt-4o-mini" in out


@pytest.mark.asyncio
async def test_write_note_preserves_my_notes(make_job, fake_ctx):
    job = _seed(make_job())
    pre = job.paths.job_dir / "note.md"
    pre.write_text(
        "old\n\n## My Notes\nMY PRECIOUS NOTES\n\n### subheading\nmore\n",
        encoding="utf-8",
    )
    await write_note(job, fake_ctx)
    out = pre.read_text(encoding="utf-8")
    assert "MY PRECIOUS NOTES" in out
    assert "### subheading" in out
    assert "# A Title" in out
    assert "**00:23 → 01:47**" in out


@pytest.mark.asyncio
async def test_write_note_creates_empty_my_notes_when_none(make_job, fake_ctx):
    job = _seed(make_job())
    note_path = job.paths.job_dir / "note.md"
    assert not note_path.exists()
    await write_note(job, fake_ctx)
    out = note_path.read_text(encoding="utf-8")
    assert "## My Notes" in out
    assert "Sacrosanct" in out  # placeholder comment present
