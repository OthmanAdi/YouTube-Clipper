"""Typed configuration loaded from config.toml with env-var interpolation."""
from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = REPO_ROOT / "config" / "config.toml"
ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class PathsSettings(BaseModel):
    output_dir: Path
    logs_dir: Path
    ffmpeg_bin: Path
    yt_dlp_bin: Path


class DaemonSettings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 7777


class WhisperSettings(BaseModel):
    model: str = "large-v3"
    device: Literal["cuda", "cpu", "auto"] = "cuda"
    compute_type: str = "float16"
    vad_filter: bool = True
    beam_size: int = 5
    language: str = "auto"


class AzureSummarizerSettings(BaseModel):
    enabled: bool = True
    endpoint: str
    model: str = "gpt-4o-mini"
    api_key: str


class OllamaSummarizerSettings(BaseModel):
    enabled: bool = True
    endpoint: str = "http://localhost:11434"
    model: str = "qwen2.5:14b"


class SummarizerSettings(BaseModel):
    azure: AzureSummarizerSettings
    ollama: OllamaSummarizerSettings


class RetrySettings(BaseModel):
    download_max_attempts: int = 4
    summarize_max_attempts: int = 3


class UxSettings(BaseModel):
    pause_video_on_drag: bool = False
    min_range_seconds: int = 2
    max_range_seconds: int = 1200


class AppSettings(BaseModel):
    paths: PathsSettings
    daemon: DaemonSettings
    whisper: WhisperSettings
    summarizer: SummarizerSettings
    retry: RetrySettings
    ux: UxSettings


def _interpolate(value: str) -> str:
    def repl(m: re.Match[str]) -> str:
        name = m.group(1)
        if name not in os.environ:
            raise RuntimeError(
                f"Config references env var ${{{name}}} which is not set. "
                f"Did you create config/.secrets.env and run start-daemon.ps1?"
            )
        return os.environ[name]

    return ENV_RE.sub(repl, value)


def _walk_and_interp(obj):
    if isinstance(obj, dict):
        return {k: _walk_and_interp(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk_and_interp(v) for v in obj]
    if isinstance(obj, str):
        return _interpolate(obj)
    return obj


def load_settings(path: Path | None = None) -> AppSettings:
    p = path or Path(os.environ.get("YTCLIPPER_CONFIG", str(DEFAULT_CONFIG_PATH)))
    if not p.exists():
        raise FileNotFoundError(f"config not found: {p}")
    raw = tomllib.loads(p.read_text(encoding="utf-8"))
    interpolated = _walk_and_interp(raw)
    return AppSettings.model_validate(interpolated)
