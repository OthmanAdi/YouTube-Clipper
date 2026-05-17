"""Stage 6: render note.md (Jinja2) and preserve any user-written `## My Notes`."""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage

from .context import PipelineContext

log = get_logger(__name__)

_TEMPLATE_DIR = Path(__file__).parent
_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATE_DIR)),
    autoescape=select_autoescape(default=False),
    keep_trailing_newline=True,
)

MY_NOTES_HEADING = "## My Notes"


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


def _preserve_my_notes(existing_path: Path) -> str | None:
    """Return the slice of an existing note.md from `## My Notes` to EOF, or None."""
    if not existing_path.exists():
        return None
    text = existing_path.read_text(encoding="utf-8")
    needle = "\n" + MY_NOTES_HEADING
    idx = text.find(needle)
    if idx == -1:
        if text.startswith(MY_NOTES_HEADING):
            return text
        return None
    return text[idx + 1 :]


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
    transcript_segments = transcript.get("segments", [])
    transcript_lines = [
        {
            "mmss": _mmss(seg["start"]),
            "start_int": int(seg["start"]),
            "text": seg["text"].strip(),
        }
        for seg in transcript_segments
    ]
    word_count = sum(len(seg.get("text", "").split()) for seg in transcript_segments)

    audio_mb = round(job.paths.audio.stat().st_size / (1024 * 1024), 2)
    length_s = round(job.input.end_s - job.input.start_s, 2)
    duration_total_ms = sum(job.durations_ms.values())
    channel_id = job.youtube.channel_id if job.youtube else None

    # url_base is the URL with no &t suffix, used for per-line jump links.
    url_base = job.input.url
    if "?" not in url_base:
        url_base = url_base + "?dummy=1"  # ensures the & in &t works in the template

    ctx_vars = dict(
        clip_id=job.clip_id,
        created_iso=job.created_at.astimezone().isoformat(timespec="seconds"),
        url_with_t=_build_url_with_t(job.input.url, job.input.start_s),
        url_base=url_base,
        channel=(job.youtube.channel if job.youtube else None) or job.input.channel_name,
        channel_id=channel_id,
        channel_url=_channel_url(channel_id) or "",
        title=(job.youtube.title if job.youtube else None) or job.input.video_title,
        duration_full_s=(job.youtube.duration_full_s if job.youtube else 0) or 0,
        start_s=round(job.input.start_s, 2),
        end_s=round(job.input.end_s, 2),
        length_s=length_s,
        length_label=_length_label(length_s),
        whisper_model=ctx.settings.whisper.model,
        whisper_lang=transcript.get("language", "?"),
        summarizer=job.summarizer_used or "unknown",
        duration_total_ms=duration_total_ms,
        durations_per_stage={s.value: ms for s, ms in job.durations_ms.items()},
        tags=job.summary.tags,
        tldr=job.summary.tldr,
        bullets=job.summary.bullets,
        notable_quotes=job.summary.notable_quotes,
        start_mmss=_mmss(job.input.start_s),
        end_mmss=_mmss(job.input.end_s),
        audio_mb=audio_mb,
        transcript_lines=transcript_lines,
        transcript_segments=len(transcript_segments),
        transcript_words=word_count,
    )

    template = _env.get_template("note_template.md.j2")
    rendered = template.render(**ctx_vars)

    note_path = job.paths.job_dir / "note.md"
    preserved = _preserve_my_notes(note_path)
    if preserved is not None:
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
