"""Ollama LLM provider — local model inference via httpx streaming."""

import json
from collections.abc import AsyncIterator

import httpx

from backend.config import OllamaSettings, get_logger
from backend.providers.base import LLMProvider, Message

log = get_logger(__name__)


class OllamaProvider(LLMProvider):
    def __init__(self, settings: OllamaSettings) -> None:
        self.base_url = settings.base_url.rstrip("/")
        self.model = settings.model
        self._client = httpx.AsyncClient(base_url=self.base_url, timeout=120.0)

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        payload = {
            "model": self.model,
            "messages": [m.model_dump() for m in messages],
            "stream": True,
        }
        log.debug("Ollama request: model=%s, %d messages", self.model, len(messages))

        async with self._client.stream("POST", "/api/chat", json=payload) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line:
                    continue
                data = json.loads(line)
                if chunk := data.get("message", {}).get("content", ""):
                    yield chunk
                if data.get("done"):
                    break

    async def is_available(self) -> bool:
        try:
            resp = await self._client.get("/api/tags")
            return resp.status_code == 200
        except httpx.HTTPError:
            return False

    async def close(self) -> None:
        await self._client.aclose()
