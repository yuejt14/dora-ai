"""Unit tests for OllamaProvider — all HTTP calls are mocked."""

import json
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.config import OllamaSettings
from backend.providers.base import Message
from backend.providers.ollama import OllamaProvider


def _make_provider() -> OllamaProvider:
    return OllamaProvider(
        OllamaSettings(base_url="http://localhost:11434", model="test-model")
    )


def _json_line(content: str = "", done: bool = False) -> str:
    obj: dict = {"done": done}
    if content:
        obj["message"] = {"content": content}
    return json.dumps(obj)


class FakeStreamResponse:
    """Simulates an httpx streaming response."""

    def __init__(self, lines: list[str], status_code: int = 200) -> None:
        self._lines = lines
        self.status_code = status_code

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(
                "error",
                request=MagicMock(),
                response=MagicMock(status_code=self.status_code),
            )

    async def aiter_lines(self) -> AsyncIterator[str]:
        for line in self._lines:
            yield line

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        pass


MESSAGES = [Message(role="user", content="hi")]


@pytest.mark.asyncio
async def test_stream_chat_yields_chunks():
    provider = _make_provider()
    lines = [_json_line("Hello"), _json_line(" world"), _json_line(done=True)]
    with patch.object(
        provider._client, "stream", return_value=FakeStreamResponse(lines)
    ):
        chunks = [c async for c in provider.stream_chat(MESSAGES)]
    assert chunks == ["Hello", " world"]


@pytest.mark.asyncio
async def test_stream_chat_stops_on_done():
    provider = _make_provider()
    lines = [_json_line("A"), _json_line(done=True), _json_line("ignored")]
    with patch.object(
        provider._client, "stream", return_value=FakeStreamResponse(lines)
    ):
        chunks = [c async for c in provider.stream_chat(MESSAGES)]
    assert chunks == ["A"]


@pytest.mark.asyncio
async def test_stream_chat_skips_empty_content():
    provider = _make_provider()
    lines = [_json_line(), _json_line("ok"), _json_line(done=True)]
    with patch.object(
        provider._client, "stream", return_value=FakeStreamResponse(lines)
    ):
        chunks = [c async for c in provider.stream_chat(MESSAGES)]
    assert chunks == ["ok"]


@pytest.mark.asyncio
async def test_stream_chat_raises_on_http_error():
    provider = _make_provider()
    lines: list[str] = []
    with patch.object(
        provider._client,
        "stream",
        return_value=FakeStreamResponse(lines, status_code=500),
    ):
        with pytest.raises(httpx.HTTPStatusError):
            _ = [c async for c in provider.stream_chat(MESSAGES)]


@pytest.mark.asyncio
async def test_is_available_true():
    provider = _make_provider()
    mock_resp = MagicMock(status_code=200)
    with patch.object(
        provider._client, "get", new_callable=AsyncMock, return_value=mock_resp
    ):
        assert await provider.is_available() is True


@pytest.mark.asyncio
async def test_is_available_false_on_error():
    provider = _make_provider()
    with patch.object(
        provider._client,
        "get",
        new_callable=AsyncMock,
        side_effect=httpx.ConnectError("refused"),
    ):
        assert await provider.is_available() is False
