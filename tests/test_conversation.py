"""Unit tests for ConversationPipeline — uses real temp DB + mock provider."""

import time
from collections.abc import AsyncIterator
from unittest.mock import MagicMock

from backend.async_bridge import AsyncBridge
from backend.conversation import ConversationPipeline
from backend.db.database import Database
from backend.providers.base import Message
from backend.providers.router import ProviderRouter


class FakeProvider:
    """Mock LLM provider that yields predefined chunks."""

    def __init__(self, chunks: list[str]) -> None:
        self._chunks = chunks

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        for c in self._chunks:
            yield c


class ErrorProvider:
    """Mock LLM provider that raises mid-stream."""

    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        yield "partial"
        raise RuntimeError("LLM exploded")


def _make_pipeline(
    tmp_db: Database, async_bridge: AsyncBridge, provider: object
) -> ConversationPipeline:
    router = MagicMock(spec=ProviderRouter)
    router.get.return_value = provider
    return ConversationPipeline(tmp_db, router, async_bridge)


def test_create_and_list_conversations(tmp_db: Database, async_bridge: AsyncBridge):
    pipeline = _make_pipeline(tmp_db, async_bridge, FakeProvider([]))
    id1 = pipeline.create_conversation("First")
    time.sleep(0.01)  # ensure different updated_at
    id2 = pipeline.create_conversation("Second")

    convos = pipeline.list_conversations()
    assert len(convos) == 2
    # Most recently updated first
    assert convos[0]["id"] == id2
    assert convos[1]["id"] == id1


def test_send_message_persists_both(tmp_db: Database, async_bridge: AsyncBridge):
    pipeline = _make_pipeline(tmp_db, async_bridge, FakeProvider(["Hi", " there"]))
    conv_id = pipeline.create_conversation()

    chunks = list(pipeline.send_message(conv_id, "Hello"))
    assert chunks == ["Hi", " there"]

    msgs = tmp_db.fetch_all(
        "SELECT role, content FROM messages WHERE conversation_id = ? ORDER BY created_at",
        (conv_id,),
    )
    assert len(msgs) == 2
    assert msgs[0]["role"] == "user"
    assert msgs[0]["content"] == "Hello"
    assert msgs[1]["role"] == "assistant"
    assert msgs[1]["content"] == "Hi there"


def test_send_message_streams_chunks(tmp_db: Database, async_bridge: AsyncBridge):
    pipeline = _make_pipeline(tmp_db, async_bridge, FakeProvider(["a", "b", "c"]))
    conv_id = pipeline.create_conversation()

    chunks = list(pipeline.send_message(conv_id, "test"))
    assert chunks == ["a", "b", "c"]


def test_stream_error_skips_assistant_persist(
    tmp_db: Database, async_bridge: AsyncBridge
):
    pipeline = _make_pipeline(tmp_db, async_bridge, ErrorProvider())
    conv_id = pipeline.create_conversation()

    # Consume the generator — error is caught internally
    chunks = list(pipeline.send_message(conv_id, "trigger error"))
    assert chunks == ["partial"]

    msgs = tmp_db.fetch_all(
        "SELECT role FROM messages WHERE conversation_id = ?", (conv_id,)
    )
    roles = [m["role"] for m in msgs]
    assert "user" in roles
    assert "assistant" not in roles


def test_get_history_ordered(tmp_db: Database, async_bridge: AsyncBridge):
    pipeline = _make_pipeline(tmp_db, async_bridge, FakeProvider(["r1"]))
    conv_id = pipeline.create_conversation()

    list(pipeline.send_message(conv_id, "first"))
    # Swap to new provider for second message
    pipeline._router.get.return_value = FakeProvider(["r2"])
    list(pipeline.send_message(conv_id, "second"))

    history = pipeline.get_history(conv_id)
    assert len(history) == 4
    assert history[0].content == "first"
    assert history[1].content == "r1"
    assert history[2].content == "second"
    assert history[3].content == "r2"
