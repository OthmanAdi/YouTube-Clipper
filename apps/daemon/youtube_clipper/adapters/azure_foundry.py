"""Azure Foundry / Azure OpenAI summarizer adapter."""
from __future__ import annotations

import json

import httpx

from youtube_clipper.config import AzureSummarizerSettings
from youtube_clipper.logging import get_logger

from .base import DetailLevel, SummaryResult, build_system_prompt, build_user_prompt

log = get_logger(__name__)

API_VERSION = "2024-08-01-preview"


class AzureFoundryAdapter:
    def __init__(
        self,
        cfg: AzureSummarizerSettings,
        *,
        model_override: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self.cfg = cfg
        # Per-job model override beats config default — lets the popup pick gpt-5-mini/5.4/5.5 per clip.
        self.model = model_override or cfg.model
        self.name = f"azure-foundry/{self.model}"
        self._client = client

    async def summarize(
        self,
        transcript: str,
        *,
        language: str,
        detail: DetailLevel = "standard",
    ) -> SummaryResult:
        url = (
            f"{self.cfg.endpoint.rstrip('/')}"
            f"/openai/deployments/{self.model}"
            f"/chat/completions?api-version={API_VERSION}"
        )
        headers = {"api-key": self.cfg.api_key, "Content-Type": "application/json"}
        body = {
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
