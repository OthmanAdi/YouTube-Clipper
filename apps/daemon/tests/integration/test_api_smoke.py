"""End-to-end smoke tests for the FastAPI app (no real yt-dlp/Whisper/LLM)."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_fake_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    cfg.write_text(
        f"""
[paths]
output_dir = "{out_dir.as_posix()}"
logs_dir = "{logs_dir.as_posix()}"
ffmpeg_bin = "ffmpeg"
yt_dlp_bin = "yt-dlp"

[daemon]
host = "127.0.0.1"
port = 7777

[whisper]
model = "tiny"
device = "cpu"
compute_type = "int8"

[summarizer.azure]
enabled = false
endpoint = "https://x.test"
api_key = "x"

[summarizer.ollama]
enabled = false
endpoint = "http://localhost:11434"
model = "qwen2.5:14b"

[retry]
download_max_attempts = 1
summarize_max_attempts = 1

[ux]
pause_video_on_drag = false
min_range_seconds = 1
max_range_seconds = 60
""",
        encoding="utf-8",
    )
    monkeypatch.setenv("YTCLIPPER_CONFIG", str(cfg))
    # reset structlog so the daemon's configure_logging can rebind cleanly per test
    import logging

    import structlog

    import youtube_clipper.logging as logmod

    monkeypatch.setattr(logmod, "_CONFIGURED", False)
    structlog.reset_defaults()
    for h in list(logging.getLogger().handlers):
        logging.getLogger().removeHandler(h)
        h.close()

    from youtube_clipper.api.app import create_app

    return create_app()


def test_health_endpoint(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.get("/health")
        assert r.status_code == 200
        body = r.json()
        assert body["status"] == "ok"
        assert "summarizers" in body
        assert body["whisper_model"] == "tiny"


def test_clip_range_too_short_rejected(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.post(
            "/clip",
            json={
                "url": "https://www.youtube.com/watch?v=x",
                "start_s": 10.0,
                "end_s": 10.5,
                "summarizer": "azure",
            },
        )
        assert r.status_code == 400


def test_clip_range_too_long_rejected(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.post(
            "/clip",
            json={
                "url": "https://www.youtube.com/watch?v=x",
                "start_s": 0.0,
                "end_s": 999.0,  # > max_range_seconds (60)
                "summarizer": "ollama",
            },
        )
        assert r.status_code == 400


def test_job_not_found_returns_404(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.get("/jobs/j_missing")
        assert r.status_code == 404
