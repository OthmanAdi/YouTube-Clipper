"""PipelineContext — passed to each stage with settings + a progress callback."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Awaitable, Callable

from youtube_clipper.config import AppSettings
from youtube_clipper.models import Stage

ProgressFn = Callable[[Stage, float, str], Awaitable[None]]


@dataclass
class PipelineContext:
    settings: AppSettings
    progress: ProgressFn
