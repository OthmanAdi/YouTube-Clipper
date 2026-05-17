from pathlib import Path

from youtube_clipper.models import (
    STAGE_ORDER,
    ClipInput,
    ClipPaths,
    Job,
    JobState,
    Stage,
    next_stage,
)


def test_stage_order():
    assert STAGE_ORDER[0] == Stage.RESOLVE
    assert STAGE_ORDER[-1] == Stage.WRITE_NOTE
    assert len(STAGE_ORDER) == 6


def test_next_stage_empty():
    assert next_stage([]) == Stage.RESOLVE


def test_next_stage_mid():
    assert next_stage([Stage.RESOLVE, Stage.DOWNLOAD]) == Stage.NORMALIZE


def test_next_stage_done():
    assert next_stage(list(STAGE_ORDER)) is None


def test_job_roundtrip(tmp_path: Path):
    job = Job(
        job_id="j_001",
        clip_id="2026-05-17-001",
        input=ClipInput(
            url="https://www.youtube.com/watch?v=abc",
            start_s=10.0,
            end_s=20.0,
            summarizer="azure",
        ),
        paths=ClipPaths(
            job_dir=tmp_path / "c",
            manifest=tmp_path / "c" / "manifest.json",
        ),
    )
    js = job.model_dump_json()
    back = Job.model_validate_json(js)
    assert back.job_id == "j_001"
    assert back.input.summarizer == "azure"
    assert back.state == JobState.PENDING
    assert back.stages_done == []


def test_clip_input_rejects_unknown_summarizer():
    import pytest
    from pydantic import ValidationError

    with pytest.raises(ValidationError):
        ClipInput(
            url="https://www.youtube.com/watch?v=abc",
            start_s=0.0,
            end_s=10.0,
            summarizer="z.ai",  # not allowed
        )
