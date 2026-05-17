import json

import pytest

from youtube_clipper.models import Stage, SummaryArtifact, YouTubeMeta
from youtube_clipper.website.builder import WebsiteNotReady, render_website


def _seed_done(job):
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(
        json.dumps(
            {
                "language": "en",
                "segments": [
                    {"start": 5.0, "end": 9.0, "text": " first segment", "words": []},
                    {"start": 9.0, "end": 18.0, "text": " second segment", "words": []},
                ],
            }
        ),
        encoding="utf-8",
    )
    job.paths.transcript_json = tj
    aud = job.paths.job_dir / "audio.mp3"
    aud.write_bytes(b"X" * 2048)
    job.paths.audio = aud
    job.summary = SummaryArtifact(
        tldr="Core idea.",
        bullets=["one", "two", "three"],
        notable_quotes=["a great line"],
        tags=["tag1", "tag2"],
        backend="ollama/hermes3:8b",
    )
    job.summarizer_used = "ollama/hermes3:8b"
    job.youtube = YouTubeMeta(
        video_id="abc",
        title="My Title",
        channel="My Channel",
        channel_id="UCabc",
        duration_full_s=300,
    )
    for s in (Stage.RESOLVE, Stage.DOWNLOAD, Stage.NORMALIZE, Stage.TRANSCRIBE, Stage.SUMMARIZE):
        job.durations_ms[s] = 100
    job.input.start_s = 5.0
    job.input.end_s = 18.0
    return job


def test_render_website_writes_index_html(make_job, fake_ctx):
    job = _seed_done(make_job())
    out = render_website(job, whisper_model="medium")
    assert out.exists()
    html = out.read_text(encoding="utf-8")
    assert "<title>My Title" in html
    assert "Core idea." in html
    assert "<li>one</li>" in html
    assert "a great line" in html
    assert "My Channel" in html
    assert "audio.mp3" in html
    assert "first segment" in html
    assert "second segment" in html
    # Click-to-jump data attributes:
    assert 'data-start="5"' in html
    assert 'data-start="9"' in html


def test_render_website_rejects_incomplete_job(make_job):
    job = make_job()
    # No summary, no transcript, no audio.
    with pytest.raises(WebsiteNotReady):
        render_website(job, whisper_model="medium")
