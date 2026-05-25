import json

import httpx
import pytest

from youtube_clipper.adapters.azure_foundry import AzureFoundryAdapter
from youtube_clipper.adapters.ollama import OllamaAdapter
from youtube_clipper.adapters.qwen import QwenAdapter
from youtube_clipper.config import (
    AzureSummarizerSettings,
    OllamaSummarizerSettings,
    QwenSummarizerSettings,
)


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


@pytest.mark.asyncio
async def test_qwen_adapter_happy_path():
    payload = {
        "tldr": "qwen-summary",
        "bullets": ["one", "two", "three"],
        "notable_quotes": ["a verbatim line"],
        "tags": ["alibaba", "qwen"],
    }
    upstream = {"choices": [{"message": {"content": json.dumps(payload)}}]}

    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        # Qwen compatible-mode is plain OpenAI v1 — URL ends in /chat/completions,
        # bears a Bearer token, and the model goes in the JSON body (not the URL).
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=upstream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = QwenSummarizerSettings(
            endpoint="https://ws-x.eu-central-1.maas.aliyuncs.com/compatible-mode/v1",
            api_key="sk-test",
            model="qwen-plus",
        )
        adapter = QwenAdapter(cfg, client=client)
        out = await adapter.summarize("text", language="en")
    assert out.tldr == "qwen-summary"
    assert out.bullets == ["one", "two", "three"]
    assert out.notable_quotes == ["a verbatim line"]
    assert out.tags == ["alibaba", "qwen"]
    assert out.backend == "qwen/qwen-plus"
    assert seen["url"].endswith("/chat/completions")
    assert seen["auth"] == "Bearer sk-test"
    assert seen["body"]["model"] == "qwen-plus"
    assert seen["body"]["response_format"] == {"type": "json_object"}


@pytest.mark.asyncio
async def test_qwen_adapter_model_override_beats_config():
    payload = {"tldr": "t", "bullets": ["b"], "tags": []}
    upstream = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["body"] = json.loads(request.content.decode("utf-8"))
        return httpx.Response(200, json=upstream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = QwenSummarizerSettings(
            endpoint="https://x.test/compatible-mode/v1",
            api_key="sk-test",
            model="qwen-plus",
        )
        adapter = QwenAdapter(cfg, model_override="qwen3.7-max", client=client)
        out = await adapter.summarize("text", language="en")
    assert seen["body"]["model"] == "qwen3.7-max", "override must beat config default"
    assert out.backend == "qwen/qwen3.7-max"


@pytest.mark.asyncio
async def test_qwen_adapter_propagates_http_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = QwenSummarizerSettings(
            endpoint="https://x.test/compatible-mode/v1",
            api_key="sk-bad",
            model="qwen-plus",
        )
        adapter = QwenAdapter(cfg, client=client)
        with pytest.raises(httpx.HTTPStatusError):
            await adapter.summarize("text", language="en")


@pytest.mark.asyncio
async def test_azure_adapter_model_override_changes_url():
    """Azure model lives in the URL path (/openai/deployments/{model}/) — override must rewrite it."""
    payload = {"tldr": "t", "bullets": ["b"], "tags": []}
    upstream = {"choices": [{"message": {"content": json.dumps(payload)}}]}
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json=upstream)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        cfg = AzureSummarizerSettings(
            endpoint="https://x.test", api_key="k", model="gpt-5-mini"
        )
        adapter = AzureFoundryAdapter(cfg, model_override="gpt-5.5", client=client)
        out = await adapter.summarize("text", language="en")
    assert "/openai/deployments/gpt-5.5/" in seen["url"], "override must rewrite URL deployment"
    assert "/openai/deployments/gpt-5-mini/" not in seen["url"]
    assert out.backend == "azure-foundry/gpt-5.5"
