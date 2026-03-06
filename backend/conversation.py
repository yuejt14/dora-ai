"""Conversation pipeline — orchestrates message flow through LLM and DB."""

import uuid
from collections.abc import Iterator

from backend.async_bridge import AsyncBridge
from backend.config import get_logger
from backend.db.database import Database
from backend.providers.base import Message
from backend.providers.router import ProviderRouter
from backend.utils import utc_now

log = get_logger(__name__)


class ConversationPipeline:
    """Sends user messages to the LLM, streams responses, persists both."""

    def __init__(
        self, db: Database, router: ProviderRouter, bridge: AsyncBridge
    ) -> None:
        self._db = db
        self._router = router
        self._bridge = bridge

    def create_conversation(
        self, title: str | None = None, soul_id: str = "default"
    ) -> str:
        """Create a new conversation and return its ID."""
        conv_id = uuid.uuid4().hex
        now = utc_now()
        self._db.execute(
            "INSERT INTO conversations (id, title, soul_id, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (conv_id, title or "New conversation", soul_id, now, now),
        )
        log.info("Created conversation %s", conv_id)
        return conv_id

    def list_conversations(self) -> list[dict]:
        """Return all conversations ordered by most recently updated."""
        rows = self._db.fetch_all(
            "SELECT id, title, soul_id, created_at, updated_at "
            "FROM conversations ORDER BY updated_at DESC"
        )
        return [dict(row) for row in rows]

    def get_history(self, conversation_id: str) -> list[Message]:
        """Fetch message history for LLM context."""
        rows = self._db.fetch_all(
            "SELECT role, content FROM messages "
            "WHERE conversation_id = ? ORDER BY created_at",
            (conversation_id,),
        )
        return [Message(role=row["role"], content=row["content"]) for row in rows]

    def send_message(self, conversation_id: str, text: str) -> Iterator[str]:
        """Send a user message, stream LLM response, persist both.

        Yields:
            Response text chunks as they arrive from the LLM.
        """
        # 1. Persist user message
        user_msg_id = uuid.uuid4().hex
        now = utc_now()
        self._db.execute(
            "INSERT INTO messages (id, conversation_id, role, content, created_at) "
            "VALUES (?, ?, 'user', ?, ?)",
            (user_msg_id, conversation_id, text, now),
        )

        # 2. Load history for LLM context
        messages = self.get_history(conversation_id)

        # 3. Stream LLM response via async bridge
        provider = self._router.get()
        full_response: list[str] = []
        try:
            for chunk in self._bridge.run_iter(provider.stream_chat(messages)):
                full_response.append(chunk)
                yield chunk
        except Exception:
            log.exception(
                "Stream error in conversation %s — assistant message not persisted",
                conversation_id,
            )
            return

        # 4. Persist assistant message
        assistant_text = "".join(full_response)
        if assistant_text:
            assistant_msg_id = uuid.uuid4().hex
            now = utc_now()
            self._db.execute(
                "INSERT INTO messages (id, conversation_id, role, content, created_at) "
                "VALUES (?, ?, 'assistant', ?, ?)",
                (assistant_msg_id, conversation_id, assistant_text, now),
            )

        # 5. Update conversation timestamp
        self._db.execute(
            "UPDATE conversations SET updated_at = ? WHERE id = ?",
            (utc_now(), conversation_id),
        )
