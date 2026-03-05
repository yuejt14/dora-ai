"""Shared test fixtures."""

from pathlib import Path

import pytest

from backend.async_bridge import AsyncBridge
from backend.db.database import Database


@pytest.fixture
def tmp_db(tmp_path: Path) -> Database:
    """Provide a temporary Database with migrations applied."""
    db = Database(db_path=tmp_path / "test.db")
    db.connect()
    db.run_migrations()
    yield db  # type: ignore[misc]
    db.close()


@pytest.fixture
def async_bridge() -> AsyncBridge:
    """Provide a running AsyncBridge."""
    bridge = AsyncBridge()
    bridge.start()
    yield bridge  # type: ignore[misc]
    bridge.stop()
