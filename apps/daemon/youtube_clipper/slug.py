"""Slug + clip_id utility helpers (no external deps)."""
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
        return "untitled"
    return s[:max_len].rstrip("-") or "untitled"


def next_clip_suffix(output_dir: Path, today: date) -> int:
    prefix = today.isoformat()
    if not output_dir.exists():
        return 1
    n = 0
    for entry in output_dir.iterdir():
        if entry.is_dir() and entry.name.startswith(prefix + "_"):
            n += 1
    return n + 1


def build_clip_id(today: date, suffix: int) -> str:
    return f"{today.isoformat()}-{suffix:03d}"


def build_job_dir_name(today: date, suffix: int, channel: str, title: str) -> str:
    return (
        f"{today.isoformat()}_"
        f"{slugify(channel)}_"
        f"{slugify(title)}_"
        f"{suffix:03d}"
    )
