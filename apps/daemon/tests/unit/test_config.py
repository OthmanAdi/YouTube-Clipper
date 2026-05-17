from pathlib import Path

import pytest

from youtube_clipper.config import AppSettings, load_settings


_BASE_TOML = """
[paths]
output_dir = "out"
logs_dir = "logs"
ffmpeg_bin = "ffmpeg"
yt_dlp_bin = "yt-dlp"

[daemon]
host = "127.0.0.1"
port = 7777

[whisper]
model = "large-v3"
device = "cpu"
compute_type = "int8"

[summarizer.azure]
enabled = true
endpoint = "{ep}"
api_key = "{ak}"

[summarizer.ollama]
enabled = true
endpoint = "http://localhost:11434"
model = "qwen2.5:14b"

[retry]
download_max_attempts = 4
summarize_max_attempts = 3

[ux]
pause_video_on_drag = false
min_range_seconds = 2
max_range_seconds = 1200
"""


def _write(tmp_path: Path, ep: str, ak: str) -> Path:
    cfg = tmp_path / "config.toml"
    cfg.write_text(_BASE_TOML.format(ep=ep, ak=ak), encoding="utf-8")
    return cfg


def test_load_settings_with_env_interpolation(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_AZ_EP", "https://example.test")
    monkeypatch.setenv("TEST_AZ_KEY", "abc123")
    cfg = _write(tmp_path, "${TEST_AZ_EP}", "${TEST_AZ_KEY}")
    s = load_settings(cfg)
    assert isinstance(s, AppSettings)
    assert s.summarizer.azure.endpoint == "https://example.test"
    assert s.summarizer.azure.api_key == "abc123"
    assert s.daemon.port == 7777
    assert s.whisper.device == "cpu"


def test_load_settings_literal_strings(tmp_path):
    cfg = _write(tmp_path, "https://no-interp.test", "literal-key")
    s = load_settings(cfg)
    assert s.summarizer.azure.endpoint == "https://no-interp.test"
    assert s.summarizer.azure.api_key == "literal-key"


def test_missing_env_var_raises_clear_error(tmp_path, monkeypatch):
    monkeypatch.delenv("MISSING_VAR", raising=False)
    cfg = _write(tmp_path, "${MISSING_VAR}", "x")
    with pytest.raises(RuntimeError, match="MISSING_VAR"):
        load_settings(cfg)


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_settings(tmp_path / "nope.toml")
