"""Unit tests for AsyncBridge."""

import pytest

from backend.async_bridge import AsyncBridge


def test_run_coroutine(async_bridge: AsyncBridge):
    async def add(a: int, b: int) -> int:
        return a + b

    result = async_bridge.run(add(2, 3))
    assert result == 5


def test_run_iter_async_generator(async_bridge: AsyncBridge):
    async def count_up(n: int):
        for i in range(n):
            yield i

    items = list(async_bridge.run_iter(count_up(4)))
    assert items == [0, 1, 2, 3]


def test_run_iter_propagates_exception(async_bridge: AsyncBridge):
    async def exploding():
        yield 1
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        list(async_bridge.run_iter(exploding()))
