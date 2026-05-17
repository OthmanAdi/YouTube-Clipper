"""Render a self-contained editorial index.html for a completed clip.

Self-contained means: zero CDN deps, zero remote fetches, single HTML file that the user can
open by double-clicking or host anywhere. The audio + transcript files live next to it.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from youtube_clipper.logging import get_logger
from youtube_clipper.models import Job

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(default=True),  # HTML escaping ON (we're rendering HTML)
    keep_trailing_newline=True,
)


def _mmss(t: float) -> str:
    m, s = divmod(int(t), 60)
    return f"{m:02d}:{s:02d}"


def _length_label(seconds: float) -> str:
    seconds = max(0, int(round(seconds)))
    if seconds < 60:
        return f"{seconds}s"
    m, s = divmod(seconds, 60)
    if m < 60:
        return f"{m}m {s}s"
    h, m = divmod(m, 60)
    return f"{h}h {m}m {s}s"


def _build_url_with_t(url: str, start_s: float) -> str:
    sep = "&" if "?" in url else "?"
    return f"{url}{sep}t={int(start_s)}s"


def _channel_url(channel_id: str | None) -> str | None:
    if not channel_id:
        return None
    return f"https://www.youtube.com/channel/{channel_id}"


def _atomic_write(path: Path, content: str) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(content, encoding="utf-8", newline="\n")
    os.replace(tmp, path)


class WebsiteNotReady(Exception):
    """Raised when the job is missing artifacts required to render the website."""


def render_website(job: Job, whisper_model: str) -> Path:
    """Render the website to `index.html` inside the job folder and return its path."""
    if job.summary is None:
        raise WebsiteNotReady("summary missing (job not done yet)")
    if job.paths.transcript_json is None or not job.paths.transcript_json.exists():
        raise WebsiteNotReady("transcript.json missing")
    if job.paths.audio is None or not job.paths.audio.exists():
        raise WebsiteNotReady("audio.mp3 missing")

    transcript = json.loads(job.paths.transcript_json.read_text(encoding="utf-8"))
    segments = transcript.get("segments", [])
    transcript_lines = [
        {
            "mmss": _mmss(seg["start"]),
            "start_int": int(seg["start"]),
            "text": seg["text"].strip(),
        }
        for seg in segments
    ]
    length_s = round(job.input.end_s - job.input.start_s, 2)
    channel_id = job.youtube.channel_id if job.youtube else None

    ctx = dict(
        lang=transcript.get("language", "en"),
        clip_id=job.clip_id,
        created_iso=job.created_at.astimezone().isoformat(timespec="seconds"),
        title=(job.youtube.title if job.youtube else None)
        or job.input.video_title
        or "Untitled",
        channel=(job.youtube.channel if job.youtube else None) or job.input.channel_name,
        channel_url=_channel_url(channel_id),
        start_mmss=_mmss(job.input.start_s),
        end_mmss=_mmss(job.input.end_s),
        length_label=_length_label(length_s),
        url_with_t=_build_url_with_t(job.input.url, job.input.start_s),
        tldr=job.summary.tldr,
        bullets=job.summary.bullets,
        notable_quotes=job.summary.notable_quotes,
        tags=job.summary.tags,
        transcript_lines=transcript_lines,
        whisper_model=whisper_model,
        whisper_lang=transcript.get("language", "?"),
        summarizer=job.summarizer_used or "unknown",
        duration_total_ms=sum(job.durations_ms.values()),
    )

    template = _env.get_template("template.html.j2")
    rendered = template.render(**ctx)

    out = job.paths.job_dir / "index.html"
    _atomic_write(out, rendered)
    log.info("website.rendered", path=str(out), bytes=out.stat().st_size)
    return out
