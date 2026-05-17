"""Ollama summarizer adapter — local chat model with JSON-mode output."""
from __future__ import annotations

import json

import httpx

from youtube_clipper.config import OllamaSummarizerSettings
from youtube_clipper.logging import get_logger

from .base import DetailLevel, SummaryResult, build_system_prompt, build_user_prompt

log = get_logger(__name__)


class OllamaAdapter:
    def __init__(
        self,
        cfg: OllamaSummarizerSettings,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cfg = cfg
        self.name = f"ollama/{cfg.model}"
        self._client = client

    async def summarize(
        self,
        transcript: str,
        *,
        language: str,
        detail: DetailLevel = "standard",
    ) -> SummaryResult:
        url = f"{self.cfg.endpoint.rstrip('/')}/api/chat"
        body = {
            "model": self.cfg.model,
            "messages": [
                {"role": "system", "content": build_system_prompt(detail)},
                {"role": "user", "content": build_user_prompt(transcript, language)},
            ],
            "format": "json",
            "stream": False,
            "options": {"temperature": 0.2},
        }

        client = self._client or httpx.AsyncClient(timeout=300)
        owns = self._client is None
        try:
            log.info(
                "summarizer.call",
                backend=self.name,
                transcript_chars=len(transcript),
            )
            resp = await client.post(url, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["message"]["content"]
            parsed = json.loads(content)
            return SummaryResult(
                tldr=parsed["tldr"],
                bullets=parsed["bullets"],
                notable_quotes=parsed.get("notable_quotes", []),
                tags=parsed.get("tags", []),
                backend=self.name,
                raw_response=data,
            )
        finally:
            if owns:
                await client.aclose()
