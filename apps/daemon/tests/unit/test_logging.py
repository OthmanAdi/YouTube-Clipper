import json
import logging

import structlog

from youtube_clipper.logging import (
    bind_job,
    bind_stage,
    clear_log_context,
    configure_logging,
    get_logger,
)


def _force_reset(monkeypatch):
    """Reset module-level guards + structlog so tests can reconfigure logging cleanly."""
    import youtube_clipper.logging as logmod

    monkeypatch.setattr(logmod, "_CONFIGURED", False)
    structlog.reset_defaults()
    # Drop any handlers attached to the root logger from a previous run so the new file_handler
    # is what gets written to.
    root = logging.getLogger()
    for h in list(root.handlers):
        root.removeHandler(h)
        h.close()


def test_logger_emits_json(tmp_path, monkeypatch):
    _force_reset(monkeypatch)
    configure_logging(tmp_path)
    bind_job(job_id="j1", clip_id="c1")
    bind_stage("resolve")
    log = get_logger("test")
    log.info("event.happened", count=3)

    # Flush all handlers so the line lands on disk.
    for h in logging.getLogger().handlers:
        h.flush()

    files = list(tmp_path.glob("pipeline.jsonl*"))
    assert files, "expected pipeline.jsonl"
    last = files[0].read_text(encoding="utf-8").strip().splitlines()[-1]
    parsed = json.loads(last)
    assert parsed["event"] == "event.happened"
    assert parsed["job_id"] == "j1"
    assert parsed["clip_id"] == "c1"
    assert parsed["stage"] == "resolve"
    assert parsed["count"] == 3
    clear_log_context()
