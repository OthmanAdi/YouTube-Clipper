"""Summarizer protocol + shared prompts + result model."""
from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, Field


class SummaryResult(BaseModel):
    tldr: str = Field(min_length=1, max_length=2000)
    bullets: list[str] = Field(min_length=1, max_length=12)
    tags: list[str] = Field(default_factory=list, max_length=10)
    backend: str
    raw_response: dict = Field(default_factory=dict)


SYSTEM_PROMPT = (
    "You are an expert lecture-note summarizer.\n"
    "You receive a verbatim transcript of a YouTube clip and must return STRICT JSON "
    "with these keys exactly:\n"
    "  tldr:    a 40-80 word summary of what was said.\n"
    "  bullets: 3-7 short bullet points capturing the most important specific claims, "
    "facts, or quotes.\n"
    "  tags:    0-5 short lowercase kebab-case topic tags.\n"
    "Return ONLY the JSON object. No prose. No markdown fence. No surrounding text."
)


def build_user_prompt(transcript: str, language: str) -> str:
    return (
        f"Transcript language: {language}\n"
        f"Transcript:\n"
        f'"""\n{transcript}\n"""'
    )


class Summarizer(Protocol):
    name: str

    async def summarize(self, transcript: str, *, language: str) -> SummaryResult: ...
