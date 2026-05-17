"""Summarizer protocol + shared prompts + result model."""
from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, Field

DetailLevel = Literal["quick", "standard", "deep"]


class SummaryResult(BaseModel):
    tldr: str = Field(min_length=1, max_length=4000)
    bullets: list[str] = Field(min_length=1, max_length=15)
    notable_quotes: list[str] = Field(default_factory=list, max_length=8)
    tags: list[str] = Field(default_factory=list, max_length=10)
    backend: str
    raw_response: dict = Field(default_factory=dict)


# Detail-level shape: each tier dials bullet count + bullet length + quote count + tldr length.
_DETAIL_SPEC: dict[DetailLevel, dict] = {
    "quick": {
        "label": "QUICK",
        "tldr_words": "30-60",
        "bullet_count": "3-5",
        "bullet_words": "8-20",
        "quote_max": 1,
    },
    "standard": {
        "label": "STANDARD",
        "tldr_words": "60-110",
        "bullet_count": "5-8",
        "bullet_words": "12-28",
        "quote_max": 3,
    },
    "deep": {
        "label": "DEEP",
        "tldr_words": "100-180",
        "bullet_count": "8-12",
        "bullet_words": "18-40",
        "quote_max": 5,
    },
}


def build_system_prompt(detail: DetailLevel = "standard") -> str:
    s = _DETAIL_SPEC.get(detail, _DETAIL_SPEC["standard"])
    return (
        "You are an expert lecture-note summarizer for a working educator who teaches AI and "
        "engineering to professionals.\n"
        "You receive a verbatim transcript of a YouTube clip.\n"
        f"Detail level: {s['label']}.\n"
        "\n"
        "Return STRICT JSON with EXACTLY these keys:\n"
        "\n"
        f'  "tldr": one paragraph, {s["tldr_words"]} words. Capture the central idea AND the\n'
        "          specific reasoning, numbers, or distinctions the speaker uses to support it.\n"
        "          No hedging. No filler like \"In this clip the speaker discusses\". Lead with\n"
        "          the claim or finding itself, in clear specific language.\n"
        "\n"
        f'  "bullets": {s["bullet_count"]} bullet points. Each bullet:\n'
        f'    - is {s["bullet_words"]} words long — long enough to convey the FULL specific point,\n'
        "      not a vague topic label.\n"
        "    - is a single concrete claim, fact, number, definition, mechanism, name, dollar\n"
        "      amount, date, or example from the transcript. PREFER specifics over generalities.\n"
        '    - does NOT start with "the speaker says", "they explain", "the video covers", or any\n'
        "      similar meta phrasing. State the point itself.\n"
        "    - keeps proper nouns, technical terms, and exact numbers as said.\n"
        '    - includes the WHY or HOW if it is given in the transcript (e.g. "X because Y").\n'
        "\n"
        f'  "notable_quotes": 0-{s["quote_max"]} short verbatim quotes (under 30 words each).\n'
        "    Copy VERBATIM from the transcript — no paraphrasing. Pick lines that are unusually\n"
        "    well-phrased, surprising, controversial, or quotable for a class. If nothing in the\n"
        "    transcript qualifies, return [].\n"
        "\n"
        '  "tags": 0-5 short lowercase kebab-case domain tags (e.g. "self-defense",\n'
        '    "neural-network", "berlin"). No formats or meta-tags like "transcript" or "clip".\n'
        "\n"
        "Return ONLY the JSON object. No prose. No markdown fence. No surrounding text."
    )


# Keep the symbol for any older import sites; default to standard.
SYSTEM_PROMPT = build_system_prompt("standard")


def build_user_prompt(transcript: str, language: str) -> str:
    return (
        f"Transcript language: {language}\n"
        f"Transcript:\n"
        f'"""\n{transcript}\n"""'
    )


class Summarizer(Protocol):
    name: str

    async def summarize(
        self,
        transcript: str,
        *,
        language: str,
        detail: DetailLevel = "standard",
    ) -> SummaryResult: ...
