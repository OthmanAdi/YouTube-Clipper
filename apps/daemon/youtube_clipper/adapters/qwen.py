"""Qwen (Alibaba Cloud MaaS) summarizer adapter — OpenAI-compatible mode.

Qwen exposes a "compatible-mode" endpoint that speaks the OpenAI v1 chat-completions
protocol verbatim, so the wire format is nearly identical to Azure. Differences:

  - Auth header is `Authorization: Bearer <key>` (Azure uses `api-key: <key>`).
  - URL is `{endpoint}/chat/completions` — no /openai/deployments/{model} segment.
  - Model goes in the request body (`"model": ...`) instead of in the URL.
  - No api-version query param.

JSON-mode is supported via `response_format={"type": "json_object"}` exactly like OpenAI.
"""
from __future__ import annotations

import json

import httpx

from youtube_clipper.config import QwenSummarizerSettings
from youtube_clipper.logging import get_logger

from .base import DetailLevel, SummaryResult, build_system_prompt, build_user_prompt

log = get_logger(__name__)


class QwenAdapter:
    def __init__(
        self,
        cfg: QwenSummarizerSettings,
        *,
        model_override: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cfg = cfg
        # Per-job model override beats config default — lets the popup pick turbo/plus/max per clip.
        self.model = model_override or cfg.model
        self.name = f"qwen/{self.model}"
        self._client = client

    async def summarize(
        self,
        transcript: str,
        *,
        language: str,
        detail: DetailLevel = "standard",
    ) -> SummaryResult:
        url = f"{self.cfg.endpoint.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.cfg.api_key}",
            "Content-Type": "application/json",
        }
        body = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": build_system_prompt(detail)},
                {"role": "user", "content": build_user_prompt(transcript, language)},
            ],
            "temperature": 0.2,
            "response_format": {"type": "json_object"},
        }

        client = self._client or httpx.AsyncClient(timeout=120)
        owns = self._client is None
        try:
            log.info(
                "summarizer.call",
                backend=self.name,
                transcript_chars=len(transcript),
            )
            resp = await client.post(url, headers=headers, json=body)
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
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
