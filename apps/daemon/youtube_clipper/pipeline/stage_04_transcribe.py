"""Stage 4: transcribe audio with faster-whisper. CUDA → int8 → CPU fallback chain."""
from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from youtube_clipper.logging import bind_stage, get_logger
from youtube_clipper.models import Job, Stage

from .context import PipelineContext

log = get_logger(__name__)

_MODEL_CACHE: dict[str, Any] = {}


def _load_model(model_name: str, device: str, compute_type: str):
    """Load (and memoize) a faster-whisper model. Imports are local so unit tests can stub."""
    key = f"{model_name}::{device}::{compute_type}"
    if key in _MODEL_CACHE:
        return _MODEL_CACHE[key]
    from faster_whisper import WhisperModel  # local import keeps tests light

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
    devices_to_try: list[tuple[str, str]] = [(wcfg.device, wcfg.compute_type)]
    if wcfg.device == "cuda":
        devices_to_try.append(("cuda", "int8"))
        devices_to_try.append(("cpu", "int8"))

    last_err: Exception | None = None
    info: Any = None
    segs_out: list[dict] | None = None

    for device, compute_type in devices_to_try:
        try:
            def _do_transcribe(_dev=device, _ct=compute_type):
                model = _load_model(wcfg.model, _dev, _ct)
                segs, inf = model.transcribe(
                    str(audio),
                    language=None if wcfg.language == "auto" else wcfg.language,
                    vad_filter=wcfg.vad_filter,
                    beam_size=wcfg.beam_size,
                    word_timestamps=True,
                )
                out: list[dict] = []
                for seg in segs:
                    words_out: list[dict] = []
                    if getattr(seg, "words", None):
                        for w in seg.words:
                            words_out.append(
                                {"start": w.start, "end": w.end, "word": w.word}
                            )
                    out.append(
                        {
                            "start": seg.start,
                            "end": seg.end,
                            "text": seg.text,
                            "words": words_out,
                        }
                    )
                return inf, out

            info, segs_out = await asyncio.to_thread(_do_transcribe)
            break
        except Exception as ex:
            last_err = ex
            log.warning(
                "whisper.fallback",
                device=device,
                compute_type=compute_type,
                error=str(ex),
            )
            continue

    if info is None or segs_out is None:
        raise RuntimeError(f"whisper failed across all fallbacks: {last_err}")

    transcript = {
        "language": info.language,
        "language_probability": getattr(info, "language_probability", None),
        "duration": getattr(info, "duration", None),
        "model": wcfg.model,
        "segments": segs_out,
    }

    json_out = job.paths.job_dir / "transcript.json"
    json_out.write_text(
        json.dumps(transcript, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    job.paths.transcript_json = json_out

    txt_lines = [
        f"[{_format_mmss(seg['start'])}] {seg['text'].strip()}" for seg in segs_out
    ]
    txt_out = job.paths.job_dir / "transcript.txt"
    txt_out.write_text("\n".join(txt_lines) + "\n", encoding="utf-8")
    job.paths.transcript_txt = txt_out

    duration_ms = int((time.perf_counter() - t0) * 1000)
    job.durations_ms[Stage.TRANSCRIBE] = duration_ms
    log.info(
        "transcribe.done",
        language=info.language,
        segments=len(segs_out),
        duration_ms=duration_ms,
    )
    return job
