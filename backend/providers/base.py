"""LLM provider interface."""

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from pydantic import BaseModel


class Message(BaseModel):
    role: str  # "system", "user", "assistant"
    content: str


class LLMProvider(ABC):
    """Abstract base class for LLM providers.

    All providers implement stream_chat to yield response text chunks.
    """

    @abstractmethod
    async def stream_chat(self, messages: list[Message]) -> AsyncIterator[str]:
        """Stream a chat completion as text chunks.

        Args:
            messages: Conversation history including system prompt.

        Yields:
            Response text fragments as they arrive.
        """
        ...

    @abstractmethod
    async def is_available(self) -> bool:
        """Check if the provider is reachable and ready."""
        ...
