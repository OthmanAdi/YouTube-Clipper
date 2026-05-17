import json

import httpx
import pytest

from youtube_clipper.adapters.azure_foundry import AzureFoundryAdapter
from youtube_clipper.adapters.ollama import OllamaAdapter
from youtube_clipper.config import AzureSummarizerSettings, OllamaSummarizerSettings


@pytest.mark.asyncio
async def test_azure_adapter_happy_path():
    payload = {"tldr": "an idea", "bullets": ["one", "two"], "tags": ["ai"]}
    upstream = {"choices": [{"message": {"content": json.dumps(payload)}}]}

    def handler(request: httpx.Request) -> httpx.Response:
        # Ensure URL has the deployment + api-version
        assert "/openai/deployments/" in str(request.url)
        assert "api-version=" in str(request.url)
        assert request.headers.get("api-key") == "k"
        return httpx.Response(200, json=upstream)

    transport = httpx.MockTransport(handler)
    async with httpx.AsyncClient(transport=transport) as client:
        cfg = AzureSummarizerSettings(
            endpoint="https://x.test", api_key="k", model="gpt-4o-mini"
        )
        adapter = AzureFoundryAdapter(cfg, client=client)
        out = await adapter.summarize("hello world", language="en")
    assert out.tldr == "an idea"
    assert out.bullets == ["one", "two"]
    assert out.tags == ["ai"]
    assert out.backend.startswith("azure-foundry/")


@pytest.mark.asyncio
async def test_ollama_adapter_happy_path():
    payload = {"tldr": "Q", "bullets": ["a", "b"], "tags": ["tag"]}
    upstream = {"message": {"role": "assistant", "content": json.dumps(payload)}}

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/api/chat")
        return httpx.Response(200, json=upstream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = OllamaSummarizerSettings(endpoint="http://x.test", model="qwen2.5:14b")
        adapter = OllamaAdapter(cfg, client=client)
        out = await adapter.summarize("text", language="en")
    assert out.tldr == "Q"
    assert out.backend == "ollama/qwen2.5:14b"


@pytest.mark.asyncio
async def test_azure_adapter_propagates_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": "rate limit"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = AzureSummarizerSettings(
            endpoint="https://x.test", api_key="k", model="gpt-4o-mini"
        )
        adapter = AzureFoundryAdapter(cfg, client=client)
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.summarize("text", language="en")
