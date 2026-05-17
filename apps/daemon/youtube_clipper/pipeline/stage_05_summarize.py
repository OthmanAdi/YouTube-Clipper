"""Stage 5: send the transcript to the chosen summarizer (Azure or Ollama)."""
from __future__ import annotations

import asyncio
import json
import time

from youtube_clipper.adapters.azure_foundry import AzureFoundryAdapter
from youtube_clipper.adapters.ollama import OllamaAdapter
from youtube_clipper.logging import bind_stage, get_logger
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
    full_text = " ".join(
        seg["text"].strip() for seg in transcript_data["segments"]
    ).strip()

    adapter = _pick_adapter(job.input.summarizer, ctx.settings)
    max_attempts = ctx.settings.retry.summarize_max_attempts

    result = None
    last_err: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            result = await adapter.summarize(full_text, language=language)
            last_err = None
            break
        except Exception as ex:
            last_err = ex
            log.warning("summarizer.retry", attempt=attempt, error=str(ex))
            if attempt < max_attempts:
                backoff = min(1 * (4 ** (attempt - 1)), 10)
                await asyncio.sleep(backoff)

    if result is None:
        raise RuntimeError(
            f"summarizer failed after {max_attempts} attempts: {last_err}"
        )

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
