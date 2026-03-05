"""Asyncio bridge — dedicated thread with a persistent event loop.

Sync code dispatches coroutines via asyncio.run_coroutine_threadsafe().
Used by pywebview API methods and CLI to call async providers from sync context.
"""

import asyncio
import queue
import threading
from collections.abc import AsyncIterator, Iterator
from typing import TypeVar

from backend.config import get_logger

log = get_logger(__name__)

T = TypeVar("T")

_SENTINEL = object()


class AsyncBridge:
    """Bridges sync code to async providers via a dedicated event loop thread."""

    def __init__(self) -> None:
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Spawn a daemon thread running an asyncio event loop."""
        self._loop = asyncio.new_event_loop()
        self._thread = threading.Thread(
            target=self._run_loop, daemon=True, name="asyncio-bridge"
        )
        self._thread.start()
        log.info("AsyncBridge started")

    def _run_loop(self) -> None:
        assert self._loop is not None
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def run(self, coro: object, timeout: float = 120.0) -> object:
        """Submit a coroutine and block until it completes.

        Args:
            coro: An awaitable coroutine.
            timeout: Max seconds to wait.

        Returns:
            The coroutine's return value.
        """
        assert self._loop is not None, "AsyncBridge not started"
        future = asyncio.run_coroutine_threadsafe(coro, self._loop)  # type: ignore[arg-type]
        return future.result(timeout=timeout)

    def run_iter(self, async_gen: AsyncIterator[T]) -> Iterator[T]:
        """Bridge an async generator into a sync iterator via a queue.

        Each item yielded by the async generator is put into a thread-safe
        queue and yielded synchronously. Exceptions are propagated.
        """
        assert self._loop is not None, "AsyncBridge not started"
        q: queue.Queue[object] = queue.Queue()

        async def _drain() -> None:
            try:
                async for item in async_gen:
                    q.put(item)
            except Exception as exc:
                q.put(exc)
            finally:
                q.put(_SENTINEL)

        asyncio.run_coroutine_threadsafe(_drain(), self._loop)

        while True:
            item = q.get()
            if item is _SENTINEL:
                break
            if isinstance(item, Exception):
                raise item
            yield item  # type: ignore[misc]

    def stop(self) -> None:
        """Stop the event loop and join the thread."""
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._loop.stop)
        if self._thread is not None:
            self._thread.join(timeout=5.0)
            self._thread = None
        if self._loop is not None:
            self._loop.close()
            self._loop = None
        log.info("AsyncBridge stopped")
