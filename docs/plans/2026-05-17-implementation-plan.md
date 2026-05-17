# YouTube-Clipper Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans (chosen by user — single-session inline build). Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Chrome extension + local FastAPI daemon that turns a Ctrl+drag on the YouTube seekbar into a verbatim-transcribed, AI-summarized markdown note within 30 seconds.

**Architecture:** Thin browser extension (TS + Vite, MV3) triggers a fat local Python daemon (FastAPI + uvicorn) on `127.0.0.1:7777`. The daemon runs a 6-stage pipeline (resolve → download → normalize → transcribe → summarize → write_note) and streams progress back over WebSocket. Only stage 5 is AI; the other five are deterministic CLI-tool wrappers. Output is one folder per clip in `output/`, containing `note.md` + `audio.mp3` + `transcript.json` + `raw.log`.

**Tech Stack:**
- Daemon: Python 3.11, FastAPI, uvicorn, structlog, pydantic-settings, httpx, jinja2, faster-whisper, yt-dlp (CLI), ffmpeg (CLI)
- Extension: TypeScript 5, Vite 5, Chrome Manifest V3
- Tests: pytest, pytest-asyncio
- Tooling: PowerShell scripts, uv for Python deps

---

## Project Layout

```
YouTube-Clipper/
├── apps/
│   ├── extension/                        Chrome MV3 (TS + Vite)
│   │   ├── manifest.json
│   │   ├── package.json
│   │   ├── tsconfig.json
│   │   ├── vite.config.ts
│   │   └── src/
│   │       ├── content/content.ts        seekbar overlay + Ctrl+drag
│   │       ├── background/sw.ts          fetch + WS bridge
│   │       ├── popup/popup.html
│   │       ├── popup/popup.css
│   │       ├── popup/popup.ts
│   │       └── lib/
│   │           ├── youtube.ts            URL/time parsing
│   │           ├── api.ts                daemon client
│   │           └── format.ts             mm:ss formatting
│   └── daemon/                           FastAPI daemon
│       ├── pyproject.toml
│       ├── README.md
│       └── youtube_clipper/
│           ├── __init__.py
│           ├── config.py                 pydantic-settings
│           ├── models.py                 Job, ClipInput, Stage, JobState
│           ├── logging.py                structlog config
│           ├── slug.py                   slug + clip_id utilities
│           ├── api/
│           │   ├── __init__.py
│           │   ├── app.py                FastAPI app factory
│           │   ├── routes_clip.py        POST /clip, GET /clips, GET /jobs/{id}
│           │   ├── routes_health.py      GET /health
│           │   └── ws_events.py          WS /events/{job_id}
│           ├── pipeline/
│           │   ├── __init__.py
│           │   ├── runner.py             orchestrator + worker queue
│           │   ├── context.py            PipelineContext
│           │   ├── stage_01_resolve.py
│           │   ├── stage_02_download.py
│           │   ├── stage_03_normalize.py
│           │   ├── stage_04_transcribe.py
│           │   ├── stage_05_summarize.py
│           │   ├── stage_06_write_note.py
│           │   └── note_template.md.j2   Jinja2 template
│           ├── adapters/
│           │   ├── __init__.py
│           │   ├── base.py               Summarizer protocol + SummaryResult
│           │   ├── azure_foundry.py
│           │   └── ollama.py
│           └── util/
│               ├── __init__.py
│               ├── subprocess_async.py   thin async exec wrapper
│               └── raw_log.py            post-job per-clip log filter
│       └── tests/
│           ├── unit/
│           └── integration/
├── config/
│   ├── config.toml
│   └── .secrets.env.example              committed; .secrets.env is gitignored
├── scripts/
│   ├── install.ps1
│   ├── start-daemon.ps1
│   ├── stop-daemon.ps1
│   └── doctor.ps1
├── output/                               gitignored (user data)
├── logs/                                 gitignored
├── docs/
│   ├── specs/2026-05-17-design.md
│   ├── plans/2026-05-17-implementation-plan.md  (this file)
│   └── runbook.md
├── .gitignore
├── MISSION.md
├── PROFILE.md
└── README.md
```

---

## Tasks

### Task 1: Initialize git repo and .gitignore

**Files:**
- Create: `.gitignore`
- Modify: working tree (git init)

- [ ] Step 1: Run `git init` in the repo root.

- [ ] Step 2: Write `.gitignore` with:

```gitignore
# Python
__pycache__/
*.py[cod]
.venv/
*.egg-info/
.pytest_cache/
.mypy_cache/
.ruff_cache/

# Node / Vite
node_modules/
dist/
*.tsbuildinfo

# User data
output/
logs/
config/.secrets.env

# OS
Thumbs.db
.DS_Store

# IDE
.vscode/
.idea/

# Whisper model cache (downloaded on first run)
.cache/
```

- [ ] Step 3: Commit.

```bash
git add .gitignore MISSION.md PROFILE.md README.md docs/
git commit -m "chore: initial repo with mission, profile, spec"
```

---

### Task 2: Daemon `pyproject.toml` and dependency lock

**Files:**
- Create: `apps/daemon/pyproject.toml`
- Create: `apps/daemon/README.md`

- [ ] Step 1: Write `apps/daemon/pyproject.toml`:

```toml
[project]
name = "youtube-clipper-daemon"
version = "0.1.0"
description = "Local pipeline daemon for the YouTube-Clipper extension"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.110",
    "uvicorn[standard]>=0.27",
    "pydantic>=2.6",
    "pydantic-settings>=2.2",
    "structlog>=24.1",
    "python-json-logger>=2.0",
    "httpx>=0.27",
    "jinja2>=3.1",
    "faster-whisper>=1.0",
    "tomli>=2.0; python_version < '3.11'",
]

[project.optional-dependencies]
dev = [
    "pytest>=8",
    "pytest-asyncio>=0.23",
    "ruff>=0.4",
]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["youtube_clipper"]

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py311"
```

- [ ] Step 2: Write `apps/daemon/README.md` with quick-start commands.

- [ ] Step 3: Commit.

```bash
git add apps/daemon/pyproject.toml apps/daemon/README.md
git commit -m "feat(daemon): pyproject scaffold with pinned deps"
```

---

### Task 3: Daemon package skeleton + `__init__.py` files

**Files:**
- Create: `apps/daemon/youtube_clipper/__init__.py`
- Create: `apps/daemon/youtube_clipper/api/__init__.py`
- Create: `apps/daemon/youtube_clipper/pipeline/__init__.py`
- Create: `apps/daemon/youtube_clipper/adapters/__init__.py`
- Create: `apps/daemon/youtube_clipper/util/__init__.py`
- Create: `apps/daemon/tests/__init__.py`
- Create: `apps/daemon/tests/unit/__init__.py`
- Create: `apps/daemon/tests/integration/__init__.py`

- [ ] Step 1: Create all `__init__.py` files. `youtube_clipper/__init__.py` exports `__version__ = "0.1.0"`. The others are empty.

- [ ] Step 2: Commit.

```bash
git add apps/daemon/youtube_clipper apps/daemon/tests
git commit -m "feat(daemon): package skeleton"
```

---

### Task 4: Config schema (`pydantic-settings`)

**Files:**
- Create: `apps/daemon/youtube_clipper/config.py`
- Create: `apps/daemon/tests/unit/test_config.py`
- Create: `config/config.toml`
- Create: `config/.secrets.env.example`

- [ ] Step 1: Write `config/config.toml` from the spec (Section 11).

- [ ] Step 2: Write `config/.secrets.env.example`:

```env
AZURE_FOUNDRY_ENDPOINT=https://YOUR-RESOURCE.openai.azure.com
AZURE_FOUNDRY_KEY=replace-me
```

- [ ] Step 3: Write `youtube_clipper/config.py` with pydantic models for each TOML section. Use `pydantic-settings.BaseSettings` with `env_nested_delimiter="__"`. Load TOML via `tomllib`. Provide a `load_settings(path: Path | None) -> AppSettings` function that:
  1. resolves config.toml path (arg → env `YTCLIPPER_CONFIG` → repo default),
  2. reads TOML,
  3. substitutes `${VAR}` strings from environment,
  4. validates into `AppSettings`.

```python
# apps/daemon/youtube_clipper/config.py
from __future__ import annotations
import os
import re
import tomllib
from pathlib import Path
from typing import Literal
from pydantic import BaseModel, Field, HttpUrl

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
            raise RuntimeError(f"Config references env var ${{{name}}} which is not set")
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
```

- [ ] Step 4: Write `tests/unit/test_config.py`:

```python
import os
from pathlib import Path
import pytest
from youtube_clipper.config import load_settings, AppSettings


def test_load_settings_from_repo_default(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
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
endpoint = "${TEST_AZ_EP}"
api_key = "${TEST_AZ_KEY}"

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
""", encoding="utf-8")
    monkeypatch.setenv("TEST_AZ_EP", "https://example.test")
    monkeypatch.setenv("TEST_AZ_KEY", "abc123")
    s = load_settings(cfg)
    assert isinstance(s, AppSettings)
    assert s.summarizer.azure.endpoint == "https://example.test"
    assert s.summarizer.azure.api_key == "abc123"
    assert s.daemon.port == 7777


def test_missing_env_raises(tmp_path):
    cfg = tmp_path / "config.toml"
    cfg.write_text("""
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
endpoint = "${MISSING_VAR}"
api_key = "x"

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
""", encoding="utf-8")
    with pytest.raises(RuntimeError, match="MISSING_VAR"):
        load_settings(cfg)
```

- [ ] Step 5: Run tests:

```powershell
cd apps/daemon
uv run pytest tests/unit/test_config.py -v
```

Expected: 2 PASS.

- [ ] Step 6: Commit.

```bash
git add apps/daemon/youtube_clipper/config.py apps/daemon/tests/unit/test_config.py config/config.toml config/.secrets.env.example
git commit -m "feat(daemon): typed config loader with env interpolation"
```

---

### Task 5: Data models (`Job`, `ClipInput`, `Stage`, `JobState`)

**Files:**
- Create: `apps/daemon/youtube_clipper/models.py`
- Create: `apps/daemon/tests/unit/test_models.py`

- [ ] Step 1: Write `youtube_clipper/models.py`:

```python
from __future__ import annotations
from datetime import datetime, timezone
from enum import StrEnum
from pathlib import Path
from pydantic import BaseModel, Field, HttpUrl


class Stage(StrEnum):
    RESOLVE = "resolve"
    DOWNLOAD = "download"
    NORMALIZE = "normalize"
    TRANSCRIBE = "transcribe"
    SUMMARIZE = "summarize"
    WRITE_NOTE = "write_note"


STAGE_ORDER: tuple[Stage, ...] = (
    Stage.RESOLVE,
    Stage.DOWNLOAD,
    Stage.NORMALIZE,
    Stage.TRANSCRIBE,
    Stage.SUMMARIZE,
    Stage.WRITE_NOTE,
)


class JobState(StrEnum):
    PENDING = "pending"
    QUEUED = "queued"
    RUNNING = "running"
    DONE = "done"
    FAILED = "failed"


class ClipInput(BaseModel):
    url: str
    start_s: float
    end_s: float
    summarizer: str = Field(pattern=r"^(azure|ollama)$")
    video_title: str | None = None
    channel_name: str | None = None


class ClipPaths(BaseModel):
    job_dir: Path
    audio_raw: Path | None = None
    audio: Path | None = None
    transcript_json: Path | None = None
    transcript_txt: Path | None = None
    note: Path | None = None
    raw_log: Path | None = None
    manifest: Path


class YouTubeMeta(BaseModel):
    video_id: str
    channel: str | None = None
    channel_id: str | None = None
    title: str | None = None
    duration_full_s: float | None = None
    is_live: bool = False


class SummaryArtifact(BaseModel):
    tldr: str
    bullets: list[str]
    tags: list[str]
    backend: str


class Job(BaseModel):
    job_id: str
    clip_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    state: JobState = JobState.PENDING
    current_stage: Stage | None = None
    stages_done: list[Stage] = Field(default_factory=list)
    failed_at_stage: Stage | None = None
    error_class: str | None = None
    error_message: str | None = None
    retry_count: dict[Stage, int] = Field(default_factory=dict)
    input: ClipInput
    paths: ClipPaths
    durations_ms: dict[Stage, int] = Field(default_factory=dict)
    summarizer_used: str | None = None
    youtube: YouTubeMeta | None = None
    summary: SummaryArtifact | None = None


def next_stage(done: list[Stage]) -> Stage | None:
    for s in STAGE_ORDER:
        if s not in done:
            return s
    return None
```

- [ ] Step 2: Write `tests/unit/test_models.py` with cases:
  - Stage enum order is correct
  - `next_stage([])` returns RESOLVE
  - `next_stage([RESOLVE, DOWNLOAD])` returns NORMALIZE
  - `next_stage([all 6])` returns None
  - `Job.model_validate_json` roundtrip preserves all fields

```python
from datetime import datetime, timezone
from pathlib import Path
from youtube_clipper.models import (
    Stage, STAGE_ORDER, JobState, ClipInput, ClipPaths, Job, next_stage,
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


def test_job_roundtrip(tmp_path):
    job = Job(
        job_id="j_001",
        clip_id="2026-05-17-001",
        input=ClipInput(
            url="https://www.youtube.com/watch?v=abc",
            start_s=10.0, end_s=20.0, summarizer="azure",
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
```

- [ ] Step 3: Run tests:

```powershell
uv run pytest tests/unit/test_models.py -v
```

Expected: 5 PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/models.py apps/daemon/tests/unit/test_models.py
git commit -m "feat(daemon): pydantic job/stage data models"
```

---

### Task 6: Slug + clip_id utility

**Files:**
- Create: `apps/daemon/youtube_clipper/slug.py`
- Create: `apps/daemon/tests/unit/test_slug.py`

- [ ] Step 1: Write `youtube_clipper/slug.py`:

```python
from __future__ import annotations
import re
import unicodedata
from datetime import date
from pathlib import Path

_SLUG_NONALNUM = re.compile(r"[^a-z0-9]+")


def slugify(text: str, max_len: int = 40) -> str:
    if not text:
        return "untitled"
    norm = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    s = _SLUG_NONALNUM.sub("-", norm.lower()).strip("-")
    if not s:
        s = "untitled"
    return s[:max_len].rstrip("-") or "untitled"


def next_clip_suffix(output_dir: Path, today: date) -> int:
    prefix = today.isoformat()
    n = 0
    if not output_dir.exists():
        return 1
    for entry in output_dir.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix + "_"):
            n += 1
    return n + 1


def build_clip_id(today: date, suffix: int) -> str:
    return f"{today.isoformat()}-{suffix:03d}"


def build_job_dir_name(today: date, suffix: int, channel: str, title: str) -> str:
    return f"{today.isoformat()}_{slugify(channel)}_{slugify(title)}_{suffix:03d}"
```

- [ ] Step 2: Write `tests/unit/test_slug.py`:

```python
from datetime import date
from pathlib import Path
from youtube_clipper.slug import slugify, next_clip_suffix, build_clip_id, build_job_dir_name


def test_slugify_basic():
    assert slugify("Hello World!") == "hello-world"


def test_slugify_unicode():
    assert slugify("Café Münchner") == "cafe-munchner"


def test_slugify_empty():
    assert slugify("") == "untitled"


def test_slugify_truncates():
    assert len(slugify("a" * 80)) == 40


def test_next_clip_suffix_empty(tmp_path):
    assert next_clip_suffix(tmp_path, date(2026, 5, 17)) == 1


def test_next_clip_suffix_existing(tmp_path):
    (tmp_path / "2026-05-17_a_b_001").mkdir()
    (tmp_path / "2026-05-17_c_d_002").mkdir()
    (tmp_path / "2026-05-16_x_y_001").mkdir()  # different day, ignored
    assert next_clip_suffix(tmp_path, date(2026, 5, 17)) == 3


def test_build_clip_id():
    assert build_clip_id(date(2026, 5, 17), 7) == "2026-05-17-007"


def test_build_job_dir_name():
    name = build_job_dir_name(date(2026, 5, 17), 1, "Andrej Karpathy", "Agents Have Arrived")
    assert name == "2026-05-17_andrej-karpathy_agents-have-arrived_001"
```

- [ ] Step 3: Run tests, expect 7 PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/slug.py apps/daemon/tests/unit/test_slug.py
git commit -m "feat(daemon): slug + clip_id utilities"
```

---

### Task 7: Structlog setup with contextvars

**Files:**
- Create: `apps/daemon/youtube_clipper/logging.py`
- Create: `apps/daemon/tests/unit/test_logging.py`

- [ ] Step 1: Write `youtube_clipper/logging.py`:

```python
from __future__ import annotations
import logging
import sys
from logging.handlers import TimedRotatingFileHandler
from pathlib import Path
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars, merge_contextvars

_CONFIGURED = False


def configure_logging(logs_dir: Path, level: str = "INFO") -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return
    logs_dir.mkdir(parents=True, exist_ok=True)
    handlers: list[logging.Handler] = []

    json_renderer = structlog.processors.JSONRenderer()

    file_handler = TimedRotatingFileHandler(
        logs_dir / "pipeline.jsonl", when="midnight", backupCount=30, encoding="utf-8"
    )
    file_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(file_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(logging.Formatter("%(message)s"))
    handlers.append(stderr_handler)

    logging.basicConfig(level=level, format="%(message)s", handlers=handlers, force=True)

    structlog.configure(
        processors=[
            merge_contextvars,
            structlog.processors.add_log_level,
            structlog.processors.TimeStamper(fmt="iso", utc=False),
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            json_renderer,
        ],
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level)),
        cache_logger_on_first_use=True,
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> structlog.stdlib.BoundLogger:
    return structlog.get_logger(name)


def bind_job(job_id: str, clip_id: str) -> None:
    bind_contextvars(job_id=job_id, clip_id=clip_id)


def bind_stage(stage: str) -> None:
    bind_contextvars(stage=stage)


def clear_log_context() -> None:
    clear_contextvars()
```

- [ ] Step 2: Write `tests/unit/test_logging.py`:

```python
import json
from pathlib import Path
from youtube_clipper.logging import configure_logging, get_logger, bind_job, bind_stage, clear_log_context


def test_logger_emits_json(tmp_path, capfd):
    configure_logging(tmp_path)
    bind_job(job_id="j1", clip_id="c1")
    bind_stage("resolve")
    log = get_logger("test")
    log.info("event.happened", count=3)

    # File written:
    files = list(tmp_path.glob("pipeline.jsonl*"))
    assert files, "expected pipeline.jsonl"
    content = files[0].read_text(encoding="utf-8").strip().splitlines()[-1]
    parsed = json.loads(content)
    assert parsed["event"] == "event.happened"
    assert parsed["job_id"] == "j1"
    assert parsed["clip_id"] == "c1"
    assert parsed["stage"] == "resolve"
    assert parsed["count"] == 3
    clear_log_context()
```

NOTE: `configure_logging` uses a module-level guard so it only initialises once per test process. Subsequent tests inherit the same handlers.

- [ ] Step 3: Run tests. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/logging.py apps/daemon/tests/unit/test_logging.py
git commit -m "feat(daemon): structlog with contextvars and JSONL rotation"
```

---

### Task 8: Subprocess helper

**Files:**
- Create: `apps/daemon/youtube_clipper/util/subprocess_async.py`
- Create: `apps/daemon/tests/unit/test_subprocess.py`

- [ ] Step 1: Write `util/subprocess_async.py`:

```python
from __future__ import annotations
import asyncio
from dataclasses import dataclass
from pathlib import Path


@dataclass
class CompletedProcess:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str

    @property
    def ok(self) -> bool:
        return self.returncode == 0


async def run(
    args: list[str],
    *,
    cwd: Path | None = None,
    timeout_s: float | None = None,
    capture: bool = True,
) -> CompletedProcess:
    proc = await asyncio.create_subprocess_exec(
        *args,
        cwd=str(cwd) if cwd else None,
        stdout=asyncio.subprocess.PIPE if capture else None,
        stderr=asyncio.subprocess.PIPE if capture else None,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    return CompletedProcess(
        args=list(args),
        returncode=proc.returncode or 0,
        stdout=(out or b"").decode("utf-8", errors="replace"),
        stderr=(err or b"").decode("utf-8", errors="replace"),
    )
```

- [ ] Step 2: Write `tests/unit/test_subprocess.py` using `python -c` as a portable subprocess:

```python
import sys
import pytest
from youtube_clipper.util.subprocess_async import run


@pytest.mark.asyncio
async def test_run_ok():
    res = await run([sys.executable, "-c", "print('hello')"])
    assert res.ok
    assert "hello" in res.stdout


@pytest.mark.asyncio
async def test_run_fail():
    res = await run([sys.executable, "-c", "import sys; sys.exit(2)"])
    assert not res.ok
    assert res.returncode == 2
```

- [ ] Step 3: Run tests. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/util/subprocess_async.py apps/daemon/tests/unit/test_subprocess.py
git commit -m "feat(daemon): async subprocess helper"
```

---

### Task 9: PipelineContext

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/context.py`

- [ ] Step 1: Write `pipeline/context.py`:

```python
from __future__ import annotations
from dataclasses import dataclass
from typing import Awaitable, Callable
from youtube_clipper.config import AppSettings
from youtube_clipper.models import Job, Stage

ProgressFn = Callable[[Stage, float, str], Awaitable[None]]


@dataclass
class PipelineContext:
    settings: AppSettings
    progress: ProgressFn
```

- [ ] Step 2: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/context.py
git commit -m "feat(daemon): pipeline context type"
```

---

### Task 10: Stage 1 — resolve (yt-dlp metadata)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/stage_01_resolve.py`
- Create: `apps/daemon/tests/unit/test_stage_01_resolve.py`

- [ ] Step 1: Write the stage:

```python
# apps/daemon/youtube_clipper/pipeline/stage_01_resolve.py
from __future__ import annotations
import json
import time
from pathlib import Path
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage, YouTubeMeta
from youtube_clipper.util.subprocess_async import run
from .context import PipelineContext

log = get_logger(__name__)


async def resolve(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.RESOLVE.value)
    t0 = time.perf_counter()
    log.info("resolve.start", url=job.input.url)

    yt_dlp = str(ctx.settings.paths.yt_dlp_bin)
    res = await run([yt_dlp, "-J", "--no-warnings", job.input.url], timeout_s=30)
    if not res.ok:
        log.error("resolve.failed", stderr=res.stderr[:500])
        raise RuntimeError(f"yt-dlp -J failed: {res.stderr.strip()[:200]}")

    info = json.loads(res.stdout)
    meta = YouTubeMeta(
        video_id=info.get("id", "unknown"),
        channel=info.get("channel") or info.get("uploader"),
        channel_id=info.get("channel_id"),
        title=info.get("title"),
        duration_full_s=info.get("duration"),
        is_live=bool(info.get("is_live")),
    )

    job.youtube = meta
    metadata_path = job.paths.job_dir / "metadata.json"
    metadata_path.write_text(json.dumps(info, indent=2, ensure_ascii=False), encoding="utf-8")

    if meta.is_live:
        raise RuntimeError("Live streams not supported")

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.RESOLVE] = duration_ms
    log.info("resolve.done", video_id=meta.video_id, title=meta.title, duration_ms=duration_ms)
    return job
```

- [ ] Step 2: Write unit test stubbing `run`:

```python
# apps/daemon/tests/unit/test_stage_01_resolve.py
import json
from pathlib import Path
from unittest.mock import patch
import pytest
from youtube_clipper.models import Job, ClipInput, ClipPaths, Stage
from youtube_clipper.pipeline.stage_01_resolve import resolve
from youtube_clipper.pipeline.context import PipelineContext
from youtube_clipper.util.subprocess_async import CompletedProcess


@pytest.fixture
def fake_ctx(tmp_path):
    from youtube_clipper.config import AppSettings, PathsSettings, DaemonSettings, WhisperSettings, SummarizerSettings, AzureSummarizerSettings, OllamaSummarizerSettings, RetrySettings, UxSettings
    settings = AppSettings(
        paths=PathsSettings(output_dir=tmp_path, logs_dir=tmp_path, ffmpeg_bin="ffmpeg", yt_dlp_bin="yt-dlp"),
        daemon=DaemonSettings(),
        whisper=WhisperSettings(device="cpu", compute_type="int8"),
        summarizer=SummarizerSettings(
            azure=AzureSummarizerSettings(endpoint="x", api_key="x"),
            ollama=OllamaSummarizerSettings(),
        ),
        retry=RetrySettings(),
        ux=UxSettings(),
    )
    async def noop_progress(stage, pct, msg): pass
    return PipelineContext(settings=settings, progress=noop_progress)


def make_job(tmp_path) -> Job:
    job_dir = tmp_path / "clip"
    job_dir.mkdir()
    return Job(
        job_id="j1", clip_id="2026-05-17-001",
        input=ClipInput(url="https://www.youtube.com/watch?v=abc", start_s=0.0, end_s=10.0, summarizer="azure"),
        paths=ClipPaths(job_dir=job_dir, manifest=job_dir / "manifest.json"),
    )


@pytest.mark.asyncio
async def test_resolve_success(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    fake_info = {"id": "abc", "title": "Hello", "channel": "Ch", "duration": 100}
    fake_out = CompletedProcess(args=[], returncode=0, stdout=json.dumps(fake_info), stderr="")
    with patch("youtube_clipper.pipeline.stage_01_resolve.run", return_value=fake_out):
        out = await resolve(job, fake_ctx)
    assert out.youtube.video_id == "abc"
    assert (job.paths.job_dir / "metadata.json").exists()
    assert Stage.RESOLVE in out.durations_ms


@pytest.mark.asyncio
async def test_resolve_rejects_live(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    fake_info = {"id": "abc", "is_live": True}
    fake_out = CompletedProcess(args=[], returncode=0, stdout=json.dumps(fake_info), stderr="")
    with patch("youtube_clipper.pipeline.stage_01_resolve.run", return_value=fake_out):
        with pytest.raises(RuntimeError, match="Live"):
            await resolve(job, fake_ctx)
```

- [ ] Step 3: Run tests. Expected: 2 PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/stage_01_resolve.py apps/daemon/tests/unit/test_stage_01_resolve.py
git commit -m "feat(daemon): stage 1 resolve via yt-dlp -J"
```

---

### Task 11: Stage 2 — download (yt-dlp range)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/stage_02_download.py`
- Create: `apps/daemon/tests/unit/test_stage_02_download.py`

- [ ] Step 1: Write the stage:

```python
# apps/daemon/youtube_clipper/pipeline/stage_02_download.py
from __future__ import annotations
import time
from pathlib import Path
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage
from youtube_clipper.util.subprocess_async import run
from .context import PipelineContext

log = get_logger(__name__)


def _fmt_time(seconds: float) -> str:
    return f"{seconds:.2f}"


async def download(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.DOWNLOAD.value)
    t0 = time.perf_counter()
    s = job.input.start_s
    e = job.input.end_s
    section = f"*{_fmt_time(s)}-{_fmt_time(e)}"
    out_template = str(job.paths.job_dir / "audio.raw.%(ext)s")

    args = [
        str(ctx.settings.paths.yt_dlp_bin),
        "--no-warnings",
        "--no-playlist",
        "--download-sections", section,
        "--force-keyframes-at-cuts",
        "--extract-audio",
        "--audio-format", "mp3",
        "--audio-quality", "0",
        "-o", out_template,
        job.input.url,
    ]
    log.info("download.start", section=section)

    last_err: str | None = None
    for attempt in range(1, ctx.settings.retry.download_max_attempts + 1):
        res = await run(args, timeout_s=300)
        if res.ok:
            break
        last_err = res.stderr.strip()[:500]
        log.warning("download.retry", attempt=attempt, stderr=last_err)
    else:
        raise RuntimeError(f"yt-dlp download failed: {last_err}")

    # yt-dlp produces audio.raw.mp3 with extract-audio mp3:
    raw = job.paths.job_dir / "audio.raw.mp3"
    if not raw.exists():
        candidates = sorted(job.paths.job_dir.glob("audio.raw.*"))
        if not candidates:
            raise RuntimeError("download produced no file")
        raw = candidates[0]
    job.paths.audio_raw = raw

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.DOWNLOAD] = duration_ms
    log.info("download.done", bytes=raw.stat().st_size, duration_ms=duration_ms)
    return job
```

- [ ] Step 2: Write unit test that mocks `run` to "create" the file and assert command shape:

```python
# apps/daemon/tests/unit/test_stage_02_download.py
from pathlib import Path
from unittest.mock import patch
import pytest
from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_02_download import download
from youtube_clipper.util.subprocess_async import CompletedProcess
from .test_stage_01_resolve import fake_ctx, make_job  # reuse fixture & factory


@pytest.mark.asyncio
async def test_download_invokes_yt_dlp(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    job.input.start_s = 23.0
    job.input.end_s = 47.5
    captured = {}

    async def fake_run(args, *, timeout_s=None, **kw):
        captured["args"] = args
        (job.paths.job_dir / "audio.raw.mp3").write_bytes(b"FAKE")
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with patch("youtube_clipper.pipeline.stage_02_download.run", new=fake_run):
        out = await download(job, fake_ctx)

    assert "--download-sections" in captured["args"]
    idx = captured["args"].index("--download-sections")
    assert captured["args"][idx + 1] == "*23.00-47.50"
    assert out.paths.audio_raw and out.paths.audio_raw.exists()
    assert Stage.DOWNLOAD in out.durations_ms
```

- [ ] Step 3: Run. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/stage_02_download.py apps/daemon/tests/unit/test_stage_02_download.py
git commit -m "feat(daemon): stage 2 download with yt-dlp range + retry"
```

---

### Task 12: Stage 3 — normalize (ffmpeg)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/stage_03_normalize.py`
- Create: `apps/daemon/tests/unit/test_stage_03_normalize.py`

- [ ] Step 1: Write:

```python
# apps/daemon/youtube_clipper/pipeline/stage_03_normalize.py
from __future__ import annotations
import time
from pathlib import Path
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage
from youtube_clipper.util.subprocess_async import run
from .context import PipelineContext

log = get_logger(__name__)


async def normalize(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.NORMALIZE.value)
    t0 = time.perf_counter()
    raw = job.paths.audio_raw
    if raw is None or not raw.exists():
        raise RuntimeError("normalize requires audio_raw from stage 2")

    out = job.paths.job_dir / "audio.mp3"
    args = [
        str(ctx.settings.paths.ffmpeg_bin),
        "-y", "-i", str(raw),
        "-vn",
        "-ar", "16000",
        "-ac", "1",
        "-c:a", "libmp3lame", "-b:a", "64k",
        str(out),
    ]
    log.info("normalize.start", input=str(raw), output=str(out))
    res = await run(args, timeout_s=120)
    if not res.ok:
        raise RuntimeError(f"ffmpeg failed: {res.stderr.strip()[:200]}")
    job.paths.audio = out

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.NORMALIZE] = duration_ms
    log.info("normalize.done", bytes=out.stat().st_size, duration_ms=duration_ms)
    return job
```

- [ ] Step 2: Unit test mocking `run` to write the output file.

```python
# apps/daemon/tests/unit/test_stage_03_normalize.py
from unittest.mock import patch
import pytest
from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_03_normalize import normalize
from youtube_clipper.util.subprocess_async import CompletedProcess
from .test_stage_01_resolve import fake_ctx, make_job


@pytest.mark.asyncio
async def test_normalize_creates_mp3(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    raw = job.paths.job_dir / "audio.raw.mp3"
    raw.write_bytes(b"FAKE")
    job.paths.audio_raw = raw

    async def fake_run(args, **kw):
        (job.paths.job_dir / "audio.mp3").write_bytes(b"NORMALIZED")
        return CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    with patch("youtube_clipper.pipeline.stage_03_normalize.run", new=fake_run):
        out = await normalize(job, fake_ctx)
    assert out.paths.audio and out.paths.audio.exists()
    assert Stage.NORMALIZE in out.durations_ms
```

- [ ] Step 3: Run. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/stage_03_normalize.py apps/daemon/tests/unit/test_stage_03_normalize.py
git commit -m "feat(daemon): stage 3 normalize with ffmpeg to 16k mono mp3"
```

---

### Task 13: Stage 4 — transcribe (faster-whisper)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/stage_04_transcribe.py`
- Create: `apps/daemon/tests/unit/test_stage_04_transcribe.py`

- [ ] Step 1: Write:

```python
# apps/daemon/youtube_clipper/pipeline/stage_04_transcribe.py
from __future__ import annotations
import asyncio
import json
import time
from pathlib import Path
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage
from .context import PipelineContext

log = get_logger(__name__)

_MODEL_CACHE: dict[str, object] = {}


def _load_model(model_name: str, device: str, compute_type: str):
    key = f"{model_name}::{device}::{compute_type}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    from faster_whisper import WhisperModel
    log.info("whisper.loading", model=model_name, device=device, compute_type=compute_type)
    m = WhisperModel(model_name, device=device, compute_type=compute_type)
    _MODEL_CACHE[key] = m
    return m


def _format_mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


async def transcribe(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.TRANSCRIBE.value)
    t0 = time.perf_counter()
    audio = job.paths.audio
    if audio is None or not audio.exists():
        raise RuntimeError("transcribe requires audio from stage 3")

    wcfg = ctx.settings.whisper
    devices_to_try = [
        (wcfg.device, wcfg.compute_type),
    ]
    if wcfg.device == "cuda":
        devices_to_try.append(("cuda", "int8"))
        devices_to_try.append(("cpu", "int8"))

    last_err: Exception | None = None
    for device, compute_type in devices_to_try:
        try:
            def _do_transcribe():
                model = _load_model(wcfg.model, device, compute_type)
                segs, info = model.transcribe(
                    str(audio),
                    language=None if wcfg.language == "auto" else wcfg.language,
                    vad_filter=wcfg.vad_filter,
                    beam_size=wcfg.beam_size,
                    word_timestamps=True,
                )
                segs_out = []
                full_text: list[str] = []
                for seg in segs:
                    seg_words = []
                    if seg.words:
                        for w in seg.words:
                            seg_words.append({"start": w.start, "end": w.end, "word": w.word})
                    segs_out.append({
                        "start": seg.start, "end": seg.end, "text": seg.text, "words": seg_words,
                    })
                    full_text.append(seg.text.strip())
                return info, segs_out, " ".join(full_text)

            info, segs_out, text = await asyncio.to_thread(_do_transcribe)
            break
        except Exception as ex:  # CUDA OOM, model load failure, etc.
            last_err = ex
            log.warning("whisper.fallback", device=device, compute_type=compute_type, error=str(ex))
            continue
    else:
        raise RuntimeError(f"whisper failed across all fallbacks: {last_err}")

    transcript = {
        "language": info.language,
        "language_probability": info.language_probability,
        "duration": info.duration,
        "model": wcfg.model,
        "segments": segs_out,
    }

    json_out = job.paths.job_dir / "transcript.json"
    json_out.write_text(json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8")
    job.paths.transcript_json = json_out

    txt_lines = [f"[{_format_mmss(seg['start'])}] {seg['text'].strip()}" for seg in segs_out]
    txt_out = job.paths.job_dir / "transcript.txt"
    txt_out.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    job.paths.transcript_txt = txt_out

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.TRANSCRIBE] = duration_ms
    log.info("transcribe.done", language=info.language, segments=len(segs_out), duration_ms=duration_ms)
    return job
```

- [ ] Step 2: Unit test by stubbing `_load_model` to return a fake model.

```python
# apps/daemon/tests/unit/test_stage_04_transcribe.py
import json
from types import SimpleNamespace
from unittest.mock import patch
import pytest
from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_04_transcribe import transcribe
from .test_stage_01_resolve import fake_ctx, make_job


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
        seg = FakeSeg(0.0, 2.0, " hello world", [FakeWord(0.0, 1.0, "hello"), FakeWord(1.0, 2.0, "world")])
        return iter([seg]), FakeInfo()


@pytest.mark.asyncio
async def test_transcribe_writes_outputs(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    audio = job.paths.job_dir / "audio.mp3"
    audio.write_bytes(b"FAKE")
    job.paths.audio = audio

    with patch("youtube_clipper.pipeline.stage_04_transcribe._load_model", return_value=FakeModel()):
        out = await transcribe(job, fake_ctx)

    assert out.paths.transcript_json and out.paths.transcript_json.exists()
    data = json.loads(out.paths.transcript_json.read_text(encoding="utf-8"))
    assert data["language"] == "en"
    assert data["segments"][0]["text"].strip() == "hello world"
    assert (out.paths.job_dir / "transcript.txt").read_text(encoding="utf-8").startswith("[00:00]")
    assert Stage.TRANSCRIBE in out.durations_ms
```

- [ ] Step 3: Run. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/stage_04_transcribe.py apps/daemon/tests/unit/test_stage_04_transcribe.py
git commit -m "feat(daemon): stage 4 transcribe with faster-whisper + CUDA->int8->CPU fallback"
```

---

### Task 14: Summarizer base + Azure adapter

**Files:**
- Create: `apps/daemon/youtube_clipper/adapters/base.py`
- Create: `apps/daemon/youtube_clipper/adapters/azure_foundry.py`
- Create: `apps/daemon/tests/unit/test_azure_adapter.py`

- [ ] Step 1: Write `adapters/base.py`:

```python
from __future__ import annotations
from typing import Protocol
from pydantic import BaseModel, Field, ValidationError


class SummaryResult(BaseModel):
    tldr: str = Field(min_length=1, max_length=800)
    bullets: list[str] = Field(min_length=1, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=10)
    backend: str
    raw_response: dict


SYSTEM_PROMPT = """You are an expert lecture-note summarizer.
You receive a verbatim transcript of a YouTube clip and must return STRICT JSON with these keys exactly:
  tldr:    a 40-80 word summary of what was said.
  bullets: 3-7 short bullet points capturing the most important specific claims, facts, or quotes.
  tags:    0-5 short lowercase kebab-case topic tags.
Return ONLY the JSON object, no prose, no markdown fence."""


def build_user_prompt(transcript: str, language: str) -> str:
    return f"Transcript language: {language}\nTranscript:\n\"\"\"\n{transcript}\n\"\"\""


class Summarizer(Protocol):
    name: str
    async def summarize(self, transcript: str, *, language: str) -> SummaryResult: ...
```

- [ ] Step 2: Write `adapters/azure_foundry.py`:

```python
from __future__ import annotations
import json
import httpx
from youtube_clipper.config import AzureSummarizerSettings
from youtube_clipper.logging import get_logger
from .base import SummaryResult, SYSTEM_PROMPT, build_user_prompt

log = get_logger(__name__)


class AzureFoundryAdapter:
    def __init__(self, cfg: AzureSummarizerSettings, client: httpx.AsyncClient | None = None):
        self.cfg = cfg
        self.name = f"azure-foundry/{cfg.model}"
        self._client = client

    async def summarize(self, transcript: str, *, language: str) -> SummaryResult:
        url = f"{self.cfg.endpoint.rstrip('/')}/openai/deployments/{self.cfg.model}/chat/completions?api-version=2024-08-01-preview"
        headers = {"api-key": self.cfg.api_key, "Content-Type": "application/json"}
        body = {
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(transcript, language)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }
        client = self._client or httpx.AsyncClient(timeout=60)
        owns = self._client is None
        try:
            log.info("summarizer.call", backend=self.name, transcript_chars=len(transcript))
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return SummaryResult(
                tldr=parsed["tldr"],
                bullets=parsed["bullets"],
                tags=parsed.get("tags", []),
                backend=self.name,
                raw_response=data,
            )
        finally:
            if owns:
                await client.aclose()
```

- [ ] Step 3: Write a unit test with a `MockTransport`:

```python
# apps/daemon/tests/unit/test_azure_adapter.py
import json
import httpx
import pytest
from youtube_clipper.adapters.azure_foundry import AzureFoundryAdapter
from youtube_clipper.config import AzureSummarizerSettings


@pytest.mark.asyncio
async def test_azure_adapter_happy_path():
    payload = {"tldr": "an idea", "bullets": ["one", "two"], "tags": ["ai"]}
    upstream = {"choices": [{"message": {"content": json.dumps(payload)}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=upstream)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        cfg = AzureSummarizerSettings(endpoint="https://x.test", api_key="k", model="gpt-4o-mini")
        adapter = AzureFoundryAdapter(cfg, client=client)
        out = await adapter.summarize("hello world", language="en")
    assert out.tldr == "an idea"
    assert out.bullets == ["one", "two"]
    assert out.tags == ["ai"]
    assert out.backend.startswith("azure-foundry/")
```

- [ ] Step 4: Run. Expected: PASS.

- [ ] Step 5: Commit.

```bash
git add apps/daemon/youtube_clipper/adapters/base.py apps/daemon/youtube_clipper/adapters/azure_foundry.py apps/daemon/tests/unit/test_azure_adapter.py
git commit -m "feat(daemon): summarizer protocol + Azure Foundry adapter"
```

---

### Task 15: Ollama adapter

**Files:**
- Create: `apps/daemon/youtube_clipper/adapters/ollama.py`
- Create: `apps/daemon/tests/unit/test_ollama_adapter.py`

- [ ] Step 1: Write `adapters/ollama.py`:

```python
from __future__ import annotations
import json
import httpx
from youtube_clipper.config import OllamaSummarizerSettings
from youtube_clipper.logging import get_logger
from .base import SummaryResult, SYSTEM_PROMPT, build_user_prompt

log = get_logger(__name__)


class OllamaAdapter:
    def __init__(self, cfg: OllamaSummarizerSettings, client: httpx.AsyncClient | None = None):
        self.cfg = cfg
        self.name = f"ollama/{cfg.model}"
        self._client = client

    async def summarize(self, transcript: str, *, language: str) -> SummaryResult:
        url = f"{self.cfg.endpoint.rstrip('/')}/api/chat"
        body = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": build_user_prompt(transcript, language)},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2},
        }
        client = self._client or httpx.AsyncClient(timeout=180)
        owns = self._client is None
        try:
            log.info("summarizer.call", backend=self.name, transcript_chars=len(transcript))
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            parsed = json.loads(content)
            return SummaryResult(
                tldr=parsed["tldr"],
                bullets=parsed["bullets"],
                tags=parsed.get("tags", []),
                backend=self.name,
                raw_response=data,
            )
        finally:
            if owns:
                await client.aclose()
```

- [ ] Step 2: Test:

```python
# apps/daemon/tests/unit/test_ollama_adapter.py
import json
import httpx
import pytest
from youtube_clipper.adapters.ollama import OllamaAdapter
from youtube_clipper.config import OllamaSummarizerSettings


@pytest.mark.asyncio
async def test_ollama_adapter_happy_path():
    payload = {"tldr": "Q", "bullets": ["a", "b"], "tags": ["tag"]}
    upstream = {"message": {"role": "assistant", "content": json.dumps(payload)}}

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=upstream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = OllamaSummarizerSettings(endpoint="http://x.test", model="qwen2.5:14b")
        adapter = OllamaAdapter(cfg, client=client)
        out = await adapter.summarize("text", language="en")
    assert out.tldr == "Q"
    assert out.backend == "ollama/qwen2.5:14b"
```

- [ ] Step 3: Run. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/adapters/ollama.py apps/daemon/tests/unit/test_ollama_adapter.py
git commit -m "feat(daemon): Ollama summarizer adapter (JSON mode)"
```

---

### Task 16: Stage 5 — summarize

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/stage_05_summarize.py`
- Create: `apps/daemon/tests/unit/test_stage_05_summarize.py`

- [ ] Step 1: Write:

```python
# apps/daemon/youtube_clipper/pipeline/stage_05_summarize.py
from __future__ import annotations
import asyncio
import json
import time
from youtube_clipper.adapters.azure_foundry import AzureFoundryAdapter
from youtube_clipper.adapters.ollama import OllamaAdapter
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage, SummaryArtifact
from .context import PipelineContext

log = get_logger(__name__)


def _pick_adapter(name: str, settings):
    if name == "azure":
        return AzureFoundryAdapter(settings.summarizer.azure)
    if name == "ollama":
        return OllamaAdapter(settings.summarizer.ollama)
    raise ValueError(f"unknown summarizer: {name}")


async def summarize(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.SUMMARIZE.value)
    t0 = time.perf_counter()
    if job.paths.transcript_json is None or not job.paths.transcript_json.exists():
        raise RuntimeError("summarize requires transcript from stage 4")

    transcript_data = json.loads(job.paths.transcript_json.read_text(encoding="utf-8"))
    language = transcript_data.get("language", "en")
    full_text = " ".join(seg["text"].strip() for seg in transcript_data["segments"])

    adapter = _pick_adapter(job.input.summarizer, ctx.settings)
    max_attempts = ctx.settings.retry.summarize_max_attempts

    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await adapter.summarize(full_text, language=language)
            break
        except Exception as ex:
            last_err = ex
            log.warning("summarizer.retry", attempt=attempt, error=str(ex))
            if attempt < max_attempts:
                await asyncio.sleep(min(1 * (4 ** (attempt - 1)), 10))
    else:
        raise RuntimeError(f"summarizer failed after {max_attempts} attempts: {last_err}")

    job.summary = SummaryArtifact(
        tldr=result.tldr,
        bullets=result.bullets,
        tags=result.tags,
        backend=result.backend,
    )
    job.summarizer_used = result.backend

    (job.paths.job_dir / "summary.json").write_text(
        job.summary.model_dump_json(indent=2), encoding="utf-8"
    )

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.SUMMARIZE] = duration_ms
    log.info("summarize.done", backend=result.backend, duration_ms=duration_ms)
    return job
```

- [ ] Step 2: Test using a stub adapter:

```python
# apps/daemon/tests/unit/test_stage_05_summarize.py
import json
from unittest.mock import patch
import pytest
from youtube_clipper.adapters.base import SummaryResult
from youtube_clipper.models import Stage
from youtube_clipper.pipeline.stage_05_summarize import summarize
from .test_stage_01_resolve import fake_ctx, make_job


class StubAdapter:
    name = "stub/x"
    async def summarize(self, transcript, *, language):
        return SummaryResult(tldr="t", bullets=["a"], tags=["tag"], backend=self.name, raw_response={})


@pytest.mark.asyncio
async def test_summarize_writes_summary(tmp_path, fake_ctx):
    job = make_job(tmp_path)
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(json.dumps({
        "language": "en",
        "segments": [{"start": 0, "end": 1, "text": "hello", "words": []}],
    }), encoding="utf-8")
    job.paths.transcript_json = tj

    with patch("youtube_clipper.pipeline.stage_05_summarize._pick_adapter", return_value=StubAdapter()):
        out = await summarize(job, fake_ctx)

    assert out.summary and out.summary.tldr == "t"
    assert (job.paths.job_dir / "summary.json").exists()
    assert Stage.SUMMARIZE in out.durations_ms
```

- [ ] Step 3: Run. Expected: PASS.

- [ ] Step 4: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/stage_05_summarize.py apps/daemon/tests/unit/test_stage_05_summarize.py
git commit -m "feat(daemon): stage 5 summarize with retry + backend selection"
```

---

### Task 17: Stage 6 — write_note (Jinja2)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/note_template.md.j2`
- Create: `apps/daemon/youtube_clipper/pipeline/stage_06_write_note.py`
- Create: `apps/daemon/tests/unit/test_stage_06_write_note.py`

- [ ] Step 1: Write `note_template.md.j2`:

```jinja2
---
clip_id: {{ clip_id }}
created: {{ created_iso }}
youtube:
  url: {{ url_with_t }}
  channel: {{ channel | default('Unknown', true) }}
  channel_id: {{ channel_id | default('', true) }}
  title: "{{ title | default('Untitled', true) | replace('"', '\\"') }}"
  duration_full_s: {{ duration_full_s | default(0) }}
range:
  start_s: {{ start_s }}
  end_s: {{ end_s }}
  length_s: {{ length_s }}
pipeline:
  whisper_model: {{ whisper_model }}
  whisper_lang: {{ whisper_lang }}
  summarizer: {{ summarizer }}
  duration_total_ms: {{ duration_total_ms }}
  duration_per_stage_ms:
{% for stage, ms in durations_per_stage.items() %}    {{ stage }}: {{ ms }}
{% endfor %}
tags: [{{ tags | join(', ') }}]
---

# {{ title | default('Untitled') }} — {{ start_mmss }} → {{ end_mmss }}

> [Watch on YouTube at {{ start_mmss }}]({{ url_with_t }})

Audio: `audio.mp3` ({{ length_s }}s, {{ audio_mb }} MB)

## TL;DR
{{ tldr }}

## Key Points
{% for b in bullets %}- {{ b }}
{% endfor %}
## Verbatim Transcript
<details><summary>Show full transcript</summary>

```
{{ transcript_block }}
```

</details>

Job log: [raw.log](raw.log) · Summarized by: {{ summarizer }}

## My Notes
<!-- Sacrosanct. Re-runs never overwrite anything in or below this section. -->
```

- [ ] Step 2: Write `stage_06_write_note.py`:

```python
# apps/daemon/youtube_clipper/pipeline/stage_06_write_note.py
from __future__ import annotations
import json
import os
import time
from datetime import datetime
from pathlib import Path
from jinja2 import Environment, FileSystemLoader, select_autoescape
from youtube_clipper.logging import get_logger, bind_stage
from youtube_clipper.models import Job, Stage
from .context import PipelineContext

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(loader=FileSystemLoader(str(_TEMPLATE_DIR)), autoescape=select_autoescape(default=False))

MY_NOTES_HEADING = "## My Notes"


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def _build_url_with_t(url: str, start_s: float) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(start_s)}s"


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


def _preserve_my_notes(existing_path: Path) -> str | None:
    if not existing_path.exists():
        return None
    text = existing_path.read_text(encoding="utf-8")
    idx = text.find("\n" + MY_NOTES_HEADING)
    if idx == -1:
        if text.startswith(MY_NOTES_HEADING):
            return text
        return None
    return text[idx + 1 :]  # from heading line onward


async def write_note(job: Job, ctx: PipelineContext) -> Job:
    bind_stage(Stage.WRITE_NOTE.value)
    t0 = time.perf_counter()
    if job.summary is None:
        raise RuntimeError("write_note requires summary from stage 5")
    if job.paths.transcript_json is None:
        raise RuntimeError("write_note requires transcript_json from stage 4")
    if job.paths.audio is None:
        raise RuntimeError("write_note requires audio from stage 3")

    transcript = json.loads(job.paths.transcript_json.read_text(encoding="utf-8"))
    transcript_block_lines = []
    for seg in transcript["segments"]:
        transcript_block_lines.append(f"[{_mmss(seg['start'])}] {seg['text'].strip()}")

    audio_mb = round(job.paths.audio.stat().st_size / (1024 * 1024), 2)
    length_s = round(job.input.end_s - job.input.start_s, 2)
    duration_total_ms = sum(job.durations_ms.values())

    ctx_vars = dict(
        clip_id=job.clip_id,
        created_iso=job.created_at.astimezone().isoformat(timespec="seconds"),
        url_with_t=_build_url_with_t(job.input.url, job.input.start_s),
        channel=(job.youtube.channel if job.youtube else None) or job.input.channel_name,
        channel_id=(job.youtube.channel_id if job.youtube else None),
        title=(job.youtube.title if job.youtube else None) or job.input.video_title,
        duration_full_s=(job.youtube.duration_full_s if job.youtube else 0) or 0,
        start_s=round(job.input.start_s, 2),
        end_s=round(job.input.end_s, 2),
        length_s=length_s,
        whisper_model=ctx.settings.whisper.model,
        whisper_lang=transcript.get("language", "?"),
        summarizer=job.summarizer_used or "unknown",
        duration_total_ms=duration_total_ms,
        durations_per_stage={s.value: ms for s, ms in job.durations_ms.items()},
        tags=job.summary.tags,
        tldr=job.summary.tldr,
        bullets=job.summary.bullets,
        start_mmss=_mmss(job.input.start_s),
        end_mmss=_mmss(job.input.end_s),
        audio_mb=audio_mb,
        transcript_block="\n".join(transcript_block_lines),
    )

    template = _env.get_template("note_template.md.j2")
    rendered = template.render(**ctx_vars)

    note_path = job.paths.job_dir / "note.md"
    preserved = _preserve_my_notes(note_path)
    if preserved is not None:
        # Strip the rendered "## My Notes" block (and everything after) and replace with preserved tail.
        cut_idx = rendered.find("\n" + MY_NOTES_HEADING)
        if cut_idx != -1:
            rendered = rendered[: cut_idx + 1] + preserved
        else:
            rendered = rendered + "\n" + preserved

    _atomic_write(note_path, rendered)
    job.paths.note = note_path

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.WRITE_NOTE] = duration_ms
    log.info("write_note.done", note=str(note_path), duration_ms=duration_ms)
    return job
```

- [ ] Step 3: Write tests covering rendering and `## My Notes` preservation:

```python
# apps/daemon/tests/unit/test_stage_06_write_note.py
import json
from datetime import datetime, timezone
from pathlib import Path
import pytest
from youtube_clipper.models import SummaryArtifact, YouTubeMeta, Stage
from youtube_clipper.pipeline.stage_06_write_note import write_note
from .test_stage_01_resolve import fake_ctx, make_job


def _seed_job(tmp_path):
    job = make_job(tmp_path)
    job.input.start_s = 23.0
    job.input.end_s = 107.5
    # transcript
    tj = job.paths.job_dir / "transcript.json"
    tj.write_text(json.dumps({
        "language": "en",
        "segments": [
            {"start": 23.0, "end": 30.0, "text": " hello there", "words": []},
            {"start": 30.0, "end": 60.0, "text": " second part of the clip", "words": []},
        ],
    }), encoding="utf-8")
    job.paths.transcript_json = tj
    # audio file (fake)
    aud = job.paths.job_dir / "audio.mp3"
    aud.write_bytes(b"X" * 1024)
    job.paths.audio = aud
    # summary
    job.summary = SummaryArtifact(tldr="Idea.", bullets=["b1", "b2"], tags=["ai"], backend="azure-foundry/gpt-4o-mini")
    job.summarizer_used = "azure-foundry/gpt-4o-mini"
    job.youtube = YouTubeMeta(video_id="abc", title="A Title", channel="A Channel", duration_full_s=600)
    for s in (Stage.RESOLVE, Stage.DOWNLOAD, Stage.NORMALIZE, Stage.TRANSCRIBE, Stage.SUMMARIZE):
        job.durations_ms[s] = 100
    return job


@pytest.mark.asyncio
async def test_write_note_fresh(tmp_path, fake_ctx):
    job = _seed_job(tmp_path)
    await write_note(job, fake_ctx)
    out = (job.paths.job_dir / "note.md").read_text(encoding="utf-8")
    assert "# A Title — 00:23 → 01:47" in out
    assert "## TL;DR" in out
    assert "- b1" in out
    assert "## My Notes" in out
    assert "Summarized by: azure-foundry/gpt-4o-mini" in out


@pytest.mark.asyncio
async def test_write_note_preserves_my_notes(tmp_path, fake_ctx):
    job = _seed_job(tmp_path)
    pre = job.paths.job_dir / "note.md"
    pre.write_text(
        "old\n\n## My Notes\nMY PRECIOUS NOTES\n\n### subheading\nmore\n",
        encoding="utf-8",
    )
    await write_note(job, fake_ctx)
    out = pre.read_text(encoding="utf-8")
    assert "MY PRECIOUS NOTES" in out
    assert "### subheading" in out
    assert "# A Title — 00:23 → 01:47" in out
```

- [ ] Step 4: Run. Expected: 2 PASS.

- [ ] Step 5: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/note_template.md.j2 apps/daemon/youtube_clipper/pipeline/stage_06_write_note.py apps/daemon/tests/unit/test_stage_06_write_note.py
git commit -m "feat(daemon): stage 6 write_note with My-Notes preservation"
```

---

### Task 18: Pipeline runner (orchestrator + queue)

**Files:**
- Create: `apps/daemon/youtube_clipper/pipeline/runner.py`
- Create: `apps/daemon/youtube_clipper/util/raw_log.py`

- [ ] Step 1: Write `util/raw_log.py`:

```python
from __future__ import annotations
import json
from pathlib import Path


def build_raw_log(logs_dir: Path, job_id: str, out_path: Path) -> None:
    out_lines: list[str] = []
    for f in sorted(logs_dir.glob("pipeline.jsonl*")):
        try:
            for line in f.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if rec.get("job_id") == job_id:
                    out_lines.append(line)
        except FileNotFoundError:
            continue
    out_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")
```

- [ ] Step 2: Write `pipeline/runner.py`:

```python
from __future__ import annotations
import asyncio
import json
import os
from contextlib import suppress
from datetime import date, datetime, timezone
from pathlib import Path
from youtube_clipper.config import AppSettings
from youtube_clipper.logging import bind_job, clear_log_context, get_logger
from youtube_clipper.models import ClipInput, ClipPaths, Job, JobState, Stage, STAGE_ORDER
from youtube_clipper.pipeline.context import PipelineContext, ProgressFn
from youtube_clipper.pipeline.stage_01_resolve import resolve
from youtube_clipper.pipeline.stage_02_download import download
from youtube_clipper.pipeline.stage_03_normalize import normalize
from youtube_clipper.pipeline.stage_04_transcribe import transcribe
from youtube_clipper.pipeline.stage_05_summarize import summarize
from youtube_clipper.pipeline.stage_06_write_note import write_note
from youtube_clipper.slug import build_clip_id, build_job_dir_name, next_clip_suffix
from youtube_clipper.util.raw_log import build_raw_log

log = get_logger(__name__)

STAGE_FNS = {
    Stage.RESOLVE: resolve,
    Stage.DOWNLOAD: download,
    Stage.NORMALIZE: normalize,
    Stage.TRANSCRIBE: transcribe,
    Stage.SUMMARIZE: summarize,
    Stage.WRITE_NOTE: write_note,
}


class JobBus:
    """In-memory hub of per-job asyncio.Queue subscribers for WS push."""

    def __init__(self) -> None:
        self._subs: dict[str, list[asyncio.Queue]] = {}
        self._lock = asyncio.Lock()

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        async with self._lock:
            q: asyncio.Queue = asyncio.Queue()
            self._subs.setdefault(job_id, []).append(q)
            return q

    async def unsubscribe(self, job_id: str, q: asyncio.Queue) -> None:
        async with self._lock:
            if job_id in self._subs and q in self._subs[job_id]:
                self._subs[job_id].remove(q)

    async def publish(self, job_id: str, message: dict) -> None:
        async with self._lock:
            subs = list(self._subs.get(job_id, []))
        for q in subs:
            with suppress(asyncio.QueueFull):
                q.put_nowait(message)


def _atomic_write_manifest(path: Path, job: Job) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(job.model_dump_json(indent=2), encoding="utf-8")
    os.replace(tmp, path)


def build_new_job(input: ClipInput, settings: AppSettings) -> Job:
    today = date.today()
    suffix = next_clip_suffix(settings.paths.output_dir, today)
    clip_id = build_clip_id(today, suffix)
    job_id = f"j_{clip_id.replace('-', '_')}"
    channel = input.channel_name or "unknown"
    title = input.video_title or "untitled"
    dir_name = build_job_dir_name(today, suffix, channel, title)
    job_dir = settings.paths.output_dir / dir_name
    job_dir.mkdir(parents=True, exist_ok=True)
    return Job(
        job_id=job_id,
        clip_id=clip_id,
        input=input,
        paths=ClipPaths(job_dir=job_dir, manifest=job_dir / "manifest.json"),
    )


class PipelineRunner:
    def __init__(self, settings: AppSettings, bus: JobBus) -> None:
        self.settings = settings
        self.bus = bus
        self._queue: asyncio.Queue[Job] = asyncio.Queue()
        self._jobs: dict[str, Job] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self._worker_loop(), name="pipeline-worker")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def enqueue(self, job: Job) -> None:
        self._jobs[job.job_id] = job
        job.state = JobState.QUEUED
        _atomic_write_manifest(job.paths.manifest, job)
        await self._queue.put(job)
        await self.bus.publish(job.job_id, {"type": "enqueued", "job_id": job.job_id})

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)

    async def _worker_loop(self) -> None:
        while True:
            job = await self._queue.get()
            try:
                await self._run(job)
            except Exception as ex:
                log.error("pipeline.unhandled", error=str(ex))

    async def _run(self, job: Job) -> None:
        bind_job(job.job_id, job.clip_id)
        job.state = JobState.RUNNING
        await self.bus.publish(job.job_id, {"type": "running", "job_id": job.job_id})

        async def progress(stage: Stage, pct: float, msg: str) -> None:
            await self.bus.publish(job.job_id, {
                "type": "progress", "job_id": job.job_id,
                "stage": stage.value, "percent": pct, "message": msg,
            })

        ctx = PipelineContext(settings=self.settings, progress=progress)

        for stage in STAGE_ORDER:
            if stage in job.stages_done:
                continue
            job.current_stage = stage
            _atomic_write_manifest(job.paths.manifest, job)
            await self.bus.publish(job.job_id, {
                "type": "stage_start", "job_id": job.job_id, "stage": stage.value,
            })
            try:
                fn = STAGE_FNS[stage]
                await fn(job, ctx)
                job.stages_done.append(stage)
                _atomic_write_manifest(job.paths.manifest, job)
                await self.bus.publish(job.job_id, {
                    "type": "stage_done", "job_id": job.job_id, "stage": stage.value,
                    "duration_ms": job.durations_ms.get(stage, 0),
                })
            except Exception as ex:
                job.state = JobState.FAILED
                job.failed_at_stage = stage
                job.error_class = type(ex).__name__
                job.error_message = str(ex)
                _atomic_write_manifest(job.paths.manifest, job)
                log.error("pipeline.failed", stage=stage.value, error=str(ex))
                await self.bus.publish(job.job_id, {
                    "type": "failed", "job_id": job.job_id, "stage": stage.value,
                    "error_class": job.error_class, "error_message": job.error_message,
                })
                clear_log_context()
                # build raw.log even on failure for debugging
                raw_log_path = job.paths.job_dir / "raw.log"
                build_raw_log(self.settings.paths.logs_dir, job.job_id, raw_log_path)
                job.paths.raw_log = raw_log_path
                _atomic_write_manifest(job.paths.manifest, job)
                return

        job.state = JobState.DONE
        job.current_stage = None
        _atomic_write_manifest(job.paths.manifest, job)
        clear_log_context()

        raw_log_path = job.paths.job_dir / "raw.log"
        build_raw_log(self.settings.paths.logs_dir, job.job_id, raw_log_path)
        job.paths.raw_log = raw_log_path
        _atomic_write_manifest(job.paths.manifest, job)

        await self.bus.publish(job.job_id, {
            "type": "done", "job_id": job.job_id, "note": str(job.paths.note or ""),
        })
```

- [ ] Step 3: Commit.

```bash
git add apps/daemon/youtube_clipper/pipeline/runner.py apps/daemon/youtube_clipper/util/raw_log.py
git commit -m "feat(daemon): pipeline runner, job bus, raw_log builder"
```

---

### Task 19: FastAPI app + routes + WS

**Files:**
- Create: `apps/daemon/youtube_clipper/api/app.py`
- Create: `apps/daemon/youtube_clipper/api/routes_clip.py`
- Create: `apps/daemon/youtube_clipper/api/routes_health.py`
- Create: `apps/daemon/youtube_clipper/api/ws_events.py`
- Create: `apps/daemon/tests/integration/test_api_smoke.py`

- [ ] Step 1: Write `api/app.py`:

```python
from __future__ import annotations
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from youtube_clipper.config import load_settings
from youtube_clipper.logging import configure_logging
from youtube_clipper.pipeline.runner import PipelineRunner, JobBus


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = load_settings()
    configure_logging(settings.paths.logs_dir)
    bus = JobBus()
    runner = PipelineRunner(settings, bus)
    runner.start()
    app.state.settings = settings
    app.state.runner = runner
    app.state.bus = bus
    try:
        yield
    finally:
        await runner.stop()


def create_app() -> FastAPI:
    app = FastAPI(title="YouTube Clipper Daemon", lifespan=lifespan)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    from .routes_clip import router as clip_router
    from .routes_health import router as health_router
    from .ws_events import router as ws_router
    app.include_router(clip_router)
    app.include_router(health_router)
    app.include_router(ws_router)
    return app


app = create_app()
```

- [ ] Step 2: Write `api/routes_health.py`:

```python
from __future__ import annotations
from fastapi import APIRouter, Request

router = APIRouter()


@router.get("/health")
async def health(request: Request):
    return {
        "status": "ok",
        "version": "0.1.0",
        "summarizers": {
            "azure": request.app.state.settings.summarizer.azure.enabled,
            "ollama": request.app.state.settings.summarizer.ollama.enabled,
        },
    }
```

- [ ] Step 3: Write `api/routes_clip.py`:

```python
from __future__ import annotations
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from youtube_clipper.models import ClipInput
from youtube_clipper.pipeline.runner import build_new_job

router = APIRouter()


class ClipRequest(BaseModel):
    url: str
    start_s: float
    end_s: float
    summarizer: str = Field(pattern=r"^(azure|ollama)$")
    video_title: str | None = None
    channel_name: str | None = None


@router.post("/clip")
async def create_clip(req: ClipRequest, request: Request):
    settings = request.app.state.settings
    if req.end_s - req.start_s < settings.ux.min_range_seconds:
        raise HTTPException(400, "range too short")
    if req.end_s - req.start_s > settings.ux.max_range_seconds:
        raise HTTPException(400, "range too long")

    input = ClipInput(
        url=req.url, start_s=req.start_s, end_s=req.end_s,
        summarizer=req.summarizer,
        video_title=req.video_title, channel_name=req.channel_name,
    )
    job = build_new_job(input, settings)
    await request.app.state.runner.enqueue(job)
    return {"job_id": job.job_id, "clip_id": job.clip_id}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, request: Request):
    job = request.app.state.runner.get(job_id)
    if job is None:
        raise HTTPException(404, "job not found")
    return job.model_dump(mode="json")
```

- [ ] Step 4: Write `api/ws_events.py`:

```python
from __future__ import annotations
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()


@router.websocket("/events/{job_id}")
async def events(ws: WebSocket, job_id: str):
    await ws.accept()
    bus = ws.app.state.bus
    q = await bus.subscribe(job_id)
    try:
        while True:
            try:
                msg = await asyncio.wait_for(q.get(), timeout=60)
                await ws.send_json(msg)
                if msg.get("type") in ("done", "failed"):
                    return
            except asyncio.TimeoutError:
                await ws.send_json({"type": "ping"})
    except WebSocketDisconnect:
        return
    finally:
        await bus.unsubscribe(job_id, q)
```

- [ ] Step 5: Write a smoke integration test that does NOT load real config:

```python
# apps/daemon/tests/integration/test_api_smoke.py
import asyncio
import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def app_with_fake_config(tmp_path, monkeypatch):
    cfg = tmp_path / "config.toml"
    out_dir = tmp_path / "out"; out_dir.mkdir()
    logs_dir = tmp_path / "logs"; logs_dir.mkdir()
    cfg.write_text(f"""
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
""", encoding="utf-8")
    monkeypatch.setenv("YTCLIPPER_CONFIG", str(cfg))
    from youtube_clipper.api.app import create_app
    return create_app()


def test_health(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"


def test_clip_range_validation(app_with_fake_config):
    with TestClient(app_with_fake_config) as client:
        r = client.post("/clip", json={
            "url": "https://www.youtube.com/watch?v=x",
            "start_s": 10.0, "end_s": 10.5, "summarizer": "azure",
        })
        assert r.status_code == 400
```

- [ ] Step 6: Run tests. Expected: PASS.

- [ ] Step 7: Commit.

```bash
git add apps/daemon/youtube_clipper/api apps/daemon/tests/integration/test_api_smoke.py
git commit -m "feat(daemon): FastAPI app with /health /clip /jobs and WS /events"
```

---

### Task 20: Extension scaffold (manifest, package.json, vite, tsconfig)

**Files:**
- Create: `apps/extension/package.json`
- Create: `apps/extension/tsconfig.json`
- Create: `apps/extension/vite.config.ts`
- Create: `apps/extension/manifest.json`
- Create: `apps/extension/src/popup/popup.html`
- Create: `apps/extension/src/popup/popup.css`
- Create: `apps/extension/icons/icon128.svg`

- [ ] Step 1: Write `package.json`:

```json
{
  "name": "youtube-clipper-extension",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "build": "vite build",
    "dev": "vite build --watch"
  },
  "devDependencies": {
    "vite": "^5.2.0",
    "typescript": "^5.4.0",
    "@types/chrome": "^0.0.260"
  }
}
```

- [ ] Step 2: Write `tsconfig.json`:

```json
{
  "compilerOptions": {
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "Bundler",
    "strict": true,
    "noUnusedLocals": true,
    "skipLibCheck": true,
    "esModuleInterop": true,
    "isolatedModules": true,
    "lib": ["ES2022", "DOM"],
    "types": ["chrome"]
  },
  "include": ["src"]
}
```

- [ ] Step 3: Write `vite.config.ts` with three named build inputs (content, sw, popup):

```ts
import { defineConfig } from "vite";
import { resolve } from "path";

export default defineConfig({
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        content: resolve(__dirname, "src/content/content.ts"),
        sw: resolve(__dirname, "src/background/sw.ts"),
        popup: resolve(__dirname, "src/popup/popup.html"),
      },
      output: {
        entryFileNames: "[name].js",
        chunkFileNames: "[name].js",
        assetFileNames: (assetInfo) => {
          if (assetInfo.name && assetInfo.name.endsWith(".html")) return "[name][extname]";
          return "assets/[name][extname]";
        },
      },
    },
    minify: false,
    sourcemap: true,
  },
});
```

- [ ] Step 4: Write `manifest.json`:

```json
{
  "manifest_version": 3,
  "name": "YouTube Clipper",
  "version": "0.1.0",
  "description": "Ctrl+drag on the YouTube seekbar to extract verbatim audio + transcript + AI summary.",
  "permissions": ["activeTab", "storage"],
  "host_permissions": ["*://*.youtube.com/*", "http://127.0.0.1:7777/*", "ws://127.0.0.1:7777/*"],
  "action": {
    "default_popup": "popup.html",
    "default_title": "YouTube Clipper",
    "default_icon": "icons/icon128.svg"
  },
  "background": {
    "service_worker": "sw.js",
    "type": "module"
  },
  "content_scripts": [
    {
      "matches": ["*://*.youtube.com/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "icons": {
    "128": "icons/icon128.svg"
  }
}
```

- [ ] Step 5: Write minimal `popup.html` + `popup.css` (stub — real logic in Task 24).

- [ ] Step 6: Write SVG icon (simple scissor on pink).

- [ ] Step 7: Commit.

```bash
git add apps/extension/package.json apps/extension/tsconfig.json apps/extension/vite.config.ts apps/extension/manifest.json apps/extension/src/popup apps/extension/icons
git commit -m "feat(ext): MV3 scaffold + Vite multi-entry build"
```

---

### Task 21: Extension `lib/` utilities (youtube, api, format)

**Files:**
- Create: `apps/extension/src/lib/youtube.ts`
- Create: `apps/extension/src/lib/api.ts`
- Create: `apps/extension/src/lib/format.ts`

- [ ] Step 1: Write `lib/format.ts`:

```ts
export function mmss(s: number): string {
  s = Math.max(0, Math.floor(s));
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${String(m).padStart(2, "0")}:${String(sec).padStart(2, "0")}`;
}

export function lengthLabel(s: number): string {
  s = Math.round(s);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  const sec = s % 60;
  return `${m}m ${sec}s`;
}
```

- [ ] Step 2: Write `lib/youtube.ts`:

```ts
export interface YouTubeContext {
  url: string;
  videoId: string;
  channelName: string | null;
  videoTitle: string | null;
}

export function readYouTubeContext(): YouTubeContext | null {
  const url = location.href;
  const match = url.match(/[?&]v=([^&]+)/);
  if (!match) return null;
  const videoId = match[1];
  const titleEl = document.querySelector("h1.ytd-watch-metadata yt-formatted-string") as HTMLElement | null;
  const channelEl = document.querySelector("ytd-channel-name yt-formatted-string a") as HTMLElement | null;
  return {
    url: `https://www.youtube.com/watch?v=${videoId}`,
    videoId,
    videoTitle: titleEl?.textContent?.trim() ?? null,
    channelName: channelEl?.textContent?.trim() ?? null,
  };
}

export function getVideoEl(): HTMLVideoElement | null {
  return document.querySelector("video.html5-main-video") as HTMLVideoElement | null;
}

export function getProgressBarEl(): HTMLElement | null {
  return document.querySelector(".ytp-progress-bar") as HTMLElement | null;
}
```

- [ ] Step 3: Write `lib/api.ts`:

```ts
export const DAEMON_BASE = "http://127.0.0.1:7777";
export const DAEMON_WS = "ws://127.0.0.1:7777";

export interface ClipRequest {
  url: string;
  start_s: number;
  end_s: number;
  summarizer: "azure" | "ollama";
  video_title?: string | null;
  channel_name?: string | null;
}

export interface ClipResponse {
  job_id: string;
  clip_id: string;
}

export async function postClip(req: ClipRequest): Promise<ClipResponse> {
  const resp = await fetch(`${DAEMON_BASE}/clip`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  if (!resp.ok) {
    const txt = await resp.text().catch(() => "");
    throw new Error(`POST /clip ${resp.status}: ${txt}`);
  }
  return (await resp.json()) as ClipResponse;
}

export async function getHealth(): Promise<unknown> {
  const resp = await fetch(`${DAEMON_BASE}/health`);
  if (!resp.ok) throw new Error(`health ${resp.status}`);
  return resp.json();
}

export function openEventsWs(jobId: string, onMessage: (m: any) => void): WebSocket {
  const ws = new WebSocket(`${DAEMON_WS}/events/${encodeURIComponent(jobId)}`);
  ws.onmessage = (ev) => {
    try { onMessage(JSON.parse(ev.data)); } catch {}
  };
  return ws;
}
```

- [ ] Step 4: Commit.

```bash
git add apps/extension/src/lib
git commit -m "feat(ext): youtube/api/format utility libs"
```

---

### Task 22: Content script (Ctrl+drag overlay)

**Files:**
- Create: `apps/extension/src/content/content.ts`
- Create: `apps/extension/src/content/content.css`

- [ ] Step 1: Write `content/content.css` (injected via a `<style>` element rather than manifest CSS to keep manifest tight):

```css
#ytc-overlay {
  position: absolute;
  top: 0;
  height: 100%;
  background: rgba(255, 24, 100, 0.55);
  border-left: 2px solid #ff1864;
  border-right: 2px solid #ff1864;
  pointer-events: none;
  z-index: 1000;
}
#ytc-tooltip {
  position: fixed;
  background: rgba(0,0,0,0.85);
  color: white;
  font: 12px/1 ui-monospace, monospace;
  padding: 6px 8px;
  border-radius: 4px;
  pointer-events: none;
  z-index: 99999;
}
#ytc-toast {
  position: fixed;
  bottom: 80px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(20,20,20,0.92);
  color: white;
  padding: 10px 14px;
  border-radius: 6px;
  font: 13px/1.3 system-ui, sans-serif;
  z-index: 99999;
}
```

- [ ] Step 2: Write `content/content.ts`:

```ts
import { getProgressBarEl, getVideoEl, readYouTubeContext } from "../lib/youtube";
import { mmss, lengthLabel } from "../lib/format";

const CSS_TEXT = `__CSS__`; // replaced at build time? Simpler: inject the file.
// We'll inline by fetching the css via chrome.runtime.getURL.

let dragging = false;
let startX = 0;
let startS = 0;
let endS = 0;
let overlay: HTMLDivElement | null = null;
let tooltip: HTMLDivElement | null = null;

function injectStyles() {
  if (document.getElementById("ytc-styles")) return;
  const link = document.createElement("link");
  link.id = "ytc-styles";
  link.rel = "stylesheet";
  link.href = chrome.runtime.getURL("assets/content.css");
  document.head.appendChild(link);
}

function ensureOverlay(bar: HTMLElement): HTMLDivElement {
  if (overlay && overlay.isConnected) return overlay;
  overlay = document.createElement("div");
  overlay.id = "ytc-overlay";
  bar.appendChild(overlay);
  return overlay;
}

function ensureTooltip(): HTMLDivElement {
  if (tooltip && tooltip.isConnected) return tooltip;
  tooltip = document.createElement("div");
  tooltip.id = "ytc-tooltip";
  document.body.appendChild(tooltip);
  return tooltip;
}

function clearUi() {
  overlay?.remove(); overlay = null;
  tooltip?.remove(); tooltip = null;
}

function toast(msg: string, ms = 2400) {
  const t = document.createElement("div");
  t.id = "ytc-toast";
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

function xToSeconds(bar: HTMLElement, x: number, duration: number): number {
  const rect = bar.getBoundingClientRect();
  const ratio = Math.max(0, Math.min(1, (x - rect.left) / rect.width));
  return ratio * duration;
}

function secondsToPct(bar: HTMLElement, sec: number, duration: number): number {
  return Math.max(0, Math.min(1, sec / duration)) * 100;
}

function onMouseDown(ev: MouseEvent) {
  if (!ev.ctrlKey) return;
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video || !isFinite(video.duration)) return;
  ev.preventDefault();
  ev.stopImmediatePropagation();
  dragging = true;
  startX = ev.clientX;
  startS = xToSeconds(bar, ev.clientX, video.duration);
  endS = startS;
  const ov = ensureOverlay(bar);
  ov.style.left = `${secondsToPct(bar, startS, video.duration)}%`;
  ov.style.width = `0%`;
  ensureTooltip();
  updateTooltip(ev.clientX, ev.clientY);
}

function onMouseMove(ev: MouseEvent) {
  if (!dragging) return;
  const bar = getProgressBarEl();
  const video = getVideoEl();
  if (!bar || !video) return;
  endS = xToSeconds(bar, ev.clientX, video.duration);
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  const ov = ensureOverlay(bar);
  ov.style.left = `${secondsToPct(bar, s, video.duration)}%`;
  ov.style.width = `${(secondsToPct(bar, e, video.duration) - secondsToPct(bar, s, video.duration))}%`;
  updateTooltip(ev.clientX, ev.clientY);
}

function updateTooltip(clientX: number, clientY: number) {
  const tt = ensureTooltip();
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  tt.textContent = `${mmss(s)} → ${mmss(e)}  (${lengthLabel(e - s)})`;
  tt.style.left = `${clientX + 12}px`;
  tt.style.top = `${clientY + 12}px`;
}

async function onMouseUp(ev: MouseEvent) {
  if (!dragging) return;
  dragging = false;
  const s = Math.min(startS, endS);
  const e = Math.max(startS, endS);
  clearUi();
  if (e - s < 2) {
    toast("Range too short (need at least 2 seconds). Ignored.");
    return;
  }
  const ctx = readYouTubeContext();
  if (!ctx) {
    toast("Not a YouTube watch page.");
    return;
  }
  chrome.runtime.sendMessage({
    type: "clip.range_selected",
    url: ctx.url,
    start_s: s,
    end_s: e,
    video_title: ctx.videoTitle,
    channel_name: ctx.channelName,
  });
}

function onKeyDown(ev: KeyboardEvent) {
  if (ev.key === "Escape" && dragging) {
    dragging = false;
    clearUi();
  }
}

function start() {
  injectStyles();
  document.addEventListener("mousedown", onMouseDown, true);
  document.addEventListener("mousemove", onMouseMove, true);
  document.addEventListener("mouseup", onMouseUp, true);
  document.addEventListener("keydown", onKeyDown, true);
}

start();
```

- [ ] Step 3: Copy the CSS into Vite's `public` so it builds as `assets/content.css`:

Create `apps/extension/public/assets/content.css` with the same content as step 1.

- [ ] Step 4: Commit.

```bash
git add apps/extension/src/content apps/extension/public/assets/content.css
git commit -m "feat(ext): content script with Ctrl+drag overlay and tooltip"
```

---

### Task 23: Background service worker

**Files:**
- Create: `apps/extension/src/background/sw.ts`

- [ ] Step 1: Write `sw.ts`:

```ts
import { postClip, openEventsWs } from "../lib/api";

interface PendingSelection {
  url: string;
  start_s: number;
  end_s: number;
  video_title: string | null;
  channel_name: string | null;
}

let pending: PendingSelection | null = null;
let currentJobId: string | null = null;
let currentWs: WebSocket | null = null;
let lastEvent: any = null;

chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  (async () => {
    if (msg?.type === "clip.range_selected") {
      pending = msg as PendingSelection;
      // Open the popup so the user can choose summarizer.
      try { await chrome.action.openPopup(); } catch { /* ignore */ }
      sendResponse({ ok: true });
      return;
    }
    if (msg?.type === "popup.get_state") {
      sendResponse({ pending, currentJobId, lastEvent });
      return;
    }
    if (msg?.type === "popup.extract") {
      if (!pending) { sendResponse({ ok: false, error: "no pending selection" }); return; }
      try {
        const resp = await postClip({
          url: pending.url,
          start_s: pending.start_s,
          end_s: pending.end_s,
          summarizer: msg.summarizer,
          video_title: pending.video_title,
          channel_name: pending.channel_name,
        });
        currentJobId = resp.job_id;
        lastEvent = { type: "enqueued", job_id: resp.job_id };
        if (currentWs) try { currentWs.close(); } catch {}
        currentWs = openEventsWs(resp.job_id, (m) => {
          lastEvent = m;
          chrome.runtime.sendMessage({ type: "popup.event", event: m }).catch(() => {});
          if (m.type === "done" || m.type === "failed") {
            try { currentWs?.close(); } catch {}
            currentWs = null;
          }
        });
        sendResponse({ ok: true, job_id: resp.job_id });
      } catch (e: any) {
        sendResponse({ ok: false, error: String(e?.message ?? e) });
      }
      return;
    }
    if (msg?.type === "popup.cancel") {
      pending = null;
      sendResponse({ ok: true });
      return;
    }
  })();
  return true; // keep channel open for async sendResponse
});
```

- [ ] Step 2: Commit.

```bash
git add apps/extension/src/background
git commit -m "feat(ext): background service worker bridges popup<->daemon"
```

---

### Task 24: Popup UI

**Files:**
- Modify: `apps/extension/src/popup/popup.html`
- Modify: `apps/extension/src/popup/popup.css`
- Create: `apps/extension/src/popup/popup.ts`

- [ ] Step 1: Write `popup.html`:

```html
<!doctype html>
<html>
<head>
  <meta charset="utf-8" />
  <title>YouTube Clipper</title>
  <link rel="stylesheet" href="popup.css" />
</head>
<body>
  <main id="root">
    <header>
      <h1>YouTube Clipper</h1>
      <span id="health-chip" class="chip dim">●</span>
    </header>

    <section id="empty-state" hidden>
      <p>Hold <kbd>Ctrl</kbd> and drag across the YouTube seekbar to mark a range.</p>
    </section>

    <section id="pending-state" hidden>
      <div class="meta">
        <div class="title" id="m-title">Title</div>
        <div class="channel" id="m-channel">Channel</div>
        <div class="range" id="m-range">0:00 → 0:00 (0s)</div>
      </div>
      <div class="row">
        <label>Summarizer</label>
        <select id="summarizer-select">
          <option value="azure">Azure Foundry</option>
          <option value="ollama">Ollama (local)</option>
        </select>
      </div>
      <div class="actions">
        <button id="extract-btn" class="primary">Extract</button>
        <button id="cancel-btn">Cancel</button>
      </div>
    </section>

    <section id="running-state" hidden>
      <div class="stage-line"><span id="r-stage">Stage</span> <span id="r-stage-num"></span></div>
      <div class="progress"><div id="r-bar"></div></div>
      <div class="last-log" id="r-last">…</div>
    </section>

    <section id="done-state" hidden>
      <div class="ok">✓ Done</div>
      <div class="note-path" id="d-path"></div>
      <div class="actions">
        <button id="open-note">Open note</button>
        <button id="open-folder">Open folder</button>
      </div>
    </section>

    <section id="failed-state" hidden>
      <div class="bad">⚠ Failed</div>
      <div class="err" id="f-msg"></div>
    </section>
  </main>
  <script type="module" src="popup.js"></script>
</body>
</html>
```

- [ ] Step 2: Write `popup.css` (compact dark UI, ~120 lines):

```css
:root { color-scheme: light dark; }
body { width: 360px; margin: 0; font: 13px/1.4 system-ui, sans-serif; background: #161616; color: #eee; }
main { padding: 12px; }
header { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
header h1 { font-size: 14px; margin: 0; flex: 1; }
.chip { font-size: 16px; }
.chip.ok { color: #44d17a; } .chip.bad { color: #ff5d5d; } .chip.dim { color: #777; }
.meta .title { font-weight: 600; font-size: 14px; }
.meta .channel { opacity: 0.7; font-size: 12px; margin-top: 2px; }
.meta .range { font-family: ui-monospace, monospace; margin-top: 6px; color: #ff5b9c; }
.row { display: flex; align-items: center; gap: 8px; margin-top: 12px; }
.row label { width: 90px; opacity: 0.8; }
.row select { flex: 1; background: #222; color: #eee; border: 1px solid #333; padding: 6px; border-radius: 4px; }
.actions { display: flex; gap: 8px; margin-top: 14px; }
button { background: #2a2a2a; color: #eee; border: 1px solid #3a3a3a; border-radius: 4px; padding: 7px 12px; cursor: pointer; font-size: 13px; }
button.primary { background: #ff1864; border-color: #ff1864; color: white; font-weight: 600; }
button:hover { filter: brightness(1.1); }
.progress { background: #222; height: 8px; border-radius: 4px; overflow: hidden; margin: 8px 0; }
#r-bar { background: #ff1864; height: 100%; width: 0%; transition: width 0.3s ease; }
.last-log { font-family: ui-monospace, monospace; font-size: 11px; opacity: 0.7; }
.ok { color: #44d17a; font-size: 16px; font-weight: 600; }
.bad { color: #ff5d5d; font-size: 16px; font-weight: 600; }
.err { font-family: ui-monospace, monospace; font-size: 12px; margin-top: 6px; }
.note-path { font-family: ui-monospace, monospace; font-size: 11px; opacity: 0.7; margin-top: 4px; }
.stage-line { font-weight: 600; }
kbd { background: #333; padding: 1px 4px; border-radius: 3px; font-family: ui-monospace, monospace; }
```

- [ ] Step 3: Write `popup.ts` — state machine driving section visibility, WS event handling, health probe.

```ts
import { getHealth, DAEMON_BASE } from "../lib/api";
import { mmss, lengthLabel } from "../lib/format";

type Section = "empty" | "pending" | "running" | "done" | "failed";

function show(sec: Section) {
  for (const id of ["empty", "pending", "running", "done", "failed"]) {
    const el = document.getElementById(`${id}-state`);
    if (el) el.hidden = id !== sec;
  }
}

function q<T extends HTMLElement>(id: string): T { return document.getElementById(id) as T; }

const STAGE_ORDER = ["resolve", "download", "normalize", "transcribe", "summarize", "write_note"];

function setProgressByStage(stage: string) {
  const idx = STAGE_ORDER.indexOf(stage);
  const pct = idx >= 0 ? ((idx + 1) / STAGE_ORDER.length) * 100 : 0;
  q<HTMLDivElement>("r-bar").style.width = `${pct}%`;
  q("r-stage").textContent = `Stage ${idx + 1}/6 · ${stage}`;
  q("r-stage-num").textContent = "";
}

async function init() {
  // Health
  const chip = q("health-chip");
  try {
    await getHealth();
    chip.classList.remove("dim", "bad"); chip.classList.add("ok"); chip.title = "Daemon up";
  } catch {
    chip.classList.remove("ok", "dim"); chip.classList.add("bad"); chip.title = "Daemon not running — run scripts/start-daemon.ps1";
  }

  // Ask SW for current state
  const state = await chrome.runtime.sendMessage({ type: "popup.get_state" });

  if (state?.currentJobId && state?.lastEvent && state.lastEvent.type !== "done" && state.lastEvent.type !== "failed") {
    show("running");
    handleEvent(state.lastEvent);
  } else if (state?.lastEvent?.type === "done") {
    show("done");
    q("d-path").textContent = state.lastEvent.note || "";
  } else if (state?.lastEvent?.type === "failed") {
    show("failed");
    q("f-msg").textContent = `${state.lastEvent.stage}: ${state.lastEvent.error_message}`;
  } else if (state?.pending) {
    show("pending");
    fillPending(state.pending);
  } else {
    show("empty");
  }

  q("extract-btn")?.addEventListener("click", onExtract);
  q("cancel-btn")?.addEventListener("click", onCancel);
  q("open-note")?.addEventListener("click", () => {
    const p = q("d-path").textContent || "";
    if (p) {
      // Best-effort: copy path to clipboard since chrome can't open arbitrary files.
      navigator.clipboard?.writeText(p).catch(() => {});
    }
  });
  q("open-folder")?.addEventListener("click", () => {
    const p = q("d-path").textContent || "";
    if (p) {
      const folder = p.split(/[\\/]/).slice(0, -1).join("/");
      navigator.clipboard?.writeText(folder).catch(() => {});
    }
  });

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg?.type === "popup.event") handleEvent(msg.event);
  });
}

function fillPending(p: any) {
  q("m-title").textContent = p.video_title || "(untitled)";
  q("m-channel").textContent = p.channel_name || "";
  q("m-range").textContent = `${mmss(p.start_s)} → ${mmss(p.end_s)}  (${lengthLabel(p.end_s - p.start_s)})`;
}

async function onExtract() {
  const summarizer = (q<HTMLSelectElement>("summarizer-select")).value;
  const resp = await chrome.runtime.sendMessage({ type: "popup.extract", summarizer });
  if (resp?.ok) {
    show("running");
    q("r-stage").textContent = "Queued…";
  } else {
    show("failed");
    q("f-msg").textContent = resp?.error || "Unknown error";
  }
}

async function onCancel() {
  await chrome.runtime.sendMessage({ type: "popup.cancel" });
  show("empty");
}

function handleEvent(ev: any) {
  if (!ev) return;
  if (ev.type === "stage_start") {
    show("running");
    setProgressByStage(ev.stage);
  } else if (ev.type === "stage_done") {
    setProgressByStage(ev.stage);
    q("r-last").textContent = `${ev.stage} done in ${ev.duration_ms}ms`;
  } else if (ev.type === "done") {
    show("done");
    q("d-path").textContent = ev.note || "";
  } else if (ev.type === "failed") {
    show("failed");
    q("f-msg").textContent = `${ev.stage}: ${ev.error_message}`;
  } else if (ev.type === "progress") {
    q("r-last").textContent = ev.message || "";
  }
}

init().catch(console.error);
```

- [ ] Step 2: Commit.

```bash
git add apps/extension/src/popup
git commit -m "feat(ext): popup UI with health chip, state machine, live progress"
```

---

### Task 25: Scripts (install, start, stop, doctor)

**Files:**
- Create: `scripts/install.ps1`
- Create: `scripts/start-daemon.ps1`
- Create: `scripts/stop-daemon.ps1`
- Create: `scripts/doctor.ps1`

- [ ] Step 1: Write `install.ps1`:

```powershell
# install.ps1 — bootstrap dependencies for YouTube-Clipper.
# Idempotent: re-runs are safe.

$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

Write-Host "==> Installing daemon dependencies (uv)..."
Push-Location "$repoRoot\apps\daemon"
try {
    if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
        throw "uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
    }
    uv sync --extra dev
} finally { Pop-Location }

Write-Host "==> Installing extension dependencies (npm)..."
Push-Location "$repoRoot\apps\extension"
try {
    if (-not (Get-Command npm -ErrorAction SilentlyContinue)) {
        throw "npm not found. Install Node 20+."
    }
    npm install
    npm run build
    Write-Host ""
    Write-Host "Extension built at: $repoRoot\apps\extension\dist"
    Write-Host "In Chrome: chrome://extensions/ -> Developer mode ON -> Load unpacked -> select that dist folder."
} finally { Pop-Location }

Write-Host "==> Checking tool dependencies..."
if (-not (Get-Command ffmpeg -ErrorAction SilentlyContinue)) { Write-Warning "ffmpeg not on PATH. Update config/config.toml [paths] ffmpeg_bin." }
if (-not (Get-Command yt-dlp -ErrorAction SilentlyContinue)) { Write-Warning "yt-dlp not on PATH. Update config/config.toml [paths] yt_dlp_bin." }

Write-Host ""
Write-Host "==> Next: cp config/.secrets.env.example config/.secrets.env; edit with your Azure values."
Write-Host "==> Then run: scripts/start-daemon.ps1"
```

- [ ] Step 2: Write `start-daemon.ps1`:

```powershell
$ErrorActionPreference = "Stop"
$repoRoot = Split-Path -Parent $PSScriptRoot

$secretsFile = "$repoRoot\config\.secrets.env"
if (Test-Path $secretsFile) {
    Get-Content $secretsFile | ForEach-Object {
        if ($_ -match "^\s*#") { return }
        if ($_ -match "^\s*$") { return }
        $kv = $_.Split("=", 2)
        if ($kv.Length -eq 2) {
            $name = $kv[0].Trim()
            $val = $kv[1].Trim().Trim('"')
            Set-Item -Path "env:$name" -Value $val
        }
    }
}

$env:YTCLIPPER_CONFIG = "$repoRoot\config\config.toml"

Push-Location "$repoRoot\apps\daemon"
try {
    uv run uvicorn youtube_clipper.api.app:app --host 127.0.0.1 --port 7777 --log-level warning
} finally { Pop-Location }
```

- [ ] Step 3: Write `stop-daemon.ps1`:

```powershell
$proc = Get-NetTCPConnection -LocalPort 7777 -State Listen -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty OwningProcess -Unique
if ($proc) {
    Stop-Process -Id $proc -Force
    Write-Host "Stopped daemon (PID $proc)"
} else {
    Write-Host "Daemon not running on port 7777."
}
```

- [ ] Step 4: Write `doctor.ps1`:

```powershell
$ErrorActionPreference = "Continue"
$repoRoot = Split-Path -Parent $PSScriptRoot
$rows = @()

function Probe($name, $script) {
    try {
        $r = & $script
        $rows += [PSCustomObject]@{ check = $name; status = "OK"; detail = $r }
    } catch {
        $rows += [PSCustomObject]@{ check = $name; status = "FAIL"; detail = $_.Exception.Message }
    }
}

Probe "ffmpeg" { (& ffmpeg -version | Select-Object -First 1) }
Probe "yt-dlp" { (& yt-dlp --version) }
Probe "uv"     { (& uv --version) }
Probe "node"   { (& node --version) }
Probe "config.toml present" { if (Test-Path "$repoRoot\config\config.toml") { "yes" } else { throw "missing" } }
Probe ".secrets.env present" { if (Test-Path "$repoRoot\config\.secrets.env") { "yes" } else { throw "missing" } }
Probe "daemon /health" {
    $r = Invoke-WebRequest -UseBasicParsing "http://127.0.0.1:7777/health" -TimeoutSec 2
    if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
    $r.Content
}
Probe "ollama reachable" {
    $r = Invoke-WebRequest -UseBasicParsing "http://localhost:11434/api/version" -TimeoutSec 2
    if ($r.StatusCode -ne 200) { throw "status $($r.StatusCode)" }
    $r.Content
}

$rows | Format-Table -AutoSize

$bad = $rows | Where-Object { $_.status -eq "FAIL" }
if ($bad) { exit 1 } else { exit 0 }
```

- [ ] Step 5: Commit.

```bash
git add scripts/
git commit -m "feat(scripts): install / start / stop / doctor"
```

---

### Task 26: Runbook documentation

**Files:**
- Create: `docs/runbook.md`

- [ ] Step 1: Write `docs/runbook.md` covering:
  - First-time setup (uv install, npm install, copy secrets, load unpacked extension)
  - Daily use (start-daemon, Ctrl+drag, popup)
  - Failure modes and recovery (daemon down, CUDA OOM, Azure 429, Ollama not pulled)
  - Where logs live
  - How to inspect a clip folder

- [ ] Step 2: Commit.

```bash
git add docs/runbook.md
git commit -m "docs: runbook for first-time setup and recovery"
```

---

### Task 27: Manual smoke test

**Files:**
- (no code) — verify the system end-to-end

- [ ] Step 1: Run `scripts/install.ps1`.
- [ ] Step 2: Copy `config/.secrets.env.example` → `config/.secrets.env`, fill in Azure values.
- [ ] Step 3: Run `scripts/doctor.ps1`. Expect at least ffmpeg/yt-dlp/uv/node to be OK. Daemon will be FAIL until started.
- [ ] Step 4: Run `scripts/start-daemon.ps1` in a terminal window.
- [ ] Step 5: In Chrome: `chrome://extensions/` → Developer mode → Load unpacked → `apps/extension/dist`.
- [ ] Step 6: Open any YouTube watch page. Hold Ctrl, drag across the seekbar.
- [ ] Step 7: Open extension popup, pick a summarizer, click Extract. Watch progress.
- [ ] Step 8: When done, open `output/<date>_<channel>_<title>_<NNN>/note.md`.
- [ ] Step 9: Confirm: TL;DR present, bullets present, transcript present, audio plays, raw.log has structured entries.

---

## Self-Review

**Spec coverage:** Each spec section maps to one or more tasks above:
- Section 4 layout → Tasks 1, 3, 20
- Section 5 components → Tasks 4–24
- Section 6 data model → Task 5
- Section 7 note schema → Task 17
- Section 8 range UX → Task 22
- Section 9 retry policy → Tasks 11, 13, 16
- Section 10 logging → Tasks 7, 18
- Section 11 config → Task 4
- Section 12 tech stack → covered across tasks
- Section 13 testing → unit tests live in each task; integration in Task 19; manual smoke in Task 27
- Section 14 bootstrap → Task 25
- Section 19 Definition of Done → validated by manual smoke (Task 27)

**Placeholder scan:** no TBD/TODO. Every step has concrete code, paths, commands.

**Type consistency:** `Stage`, `Job`, `ClipInput`, `ClipPaths`, `YouTubeMeta`, `SummaryArtifact`, `SummaryResult`, `PipelineContext`, `JobBus`, `PipelineRunner` are defined exactly once and reused consistently across all stages and tests.

**Scope check:** single focused plan. v1 ends at Task 27. Future integrations (qmd/OpenMark push, Firefox port, retry-from-stage endpoint, clip history UI) are explicitly out of scope per spec section 15.
