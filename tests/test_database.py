"""Unit tests for Database — uses real SQLite with temp files."""

import sqlite3

import pytest

from backend.db.database import Database


def test_connect_enables_wal(tmp_db: Database):
    row = tmp_db.fetch_one("PRAGMA journal_mode")
    assert row is not None
    assert row[0] == "wal"


def test_connect_enables_foreign_keys(tmp_db: Database):
    row = tmp_db.fetch_one("PRAGMA foreign_keys")
    assert row is not None
    assert row[0] == 1


def test_migrations_apply_cleanly(tmp_db: Database):
    tables = {
        row[0]
        for row in tmp_db.fetch_all(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE '\\_%' ESCAPE '\\'"
        )
    }
    assert "conversations" in tables
    assert "messages" in tables
    assert "settings" in tables


def test_migrations_are_idempotent(tmp_db: Database):
    # Running migrations again should not raise
    tmp_db.run_migrations()


def test_execute_and_fetch(tmp_db: Database):
    tmp_db.execute("INSERT INTO settings (key, value) VALUES (?, ?)", ("k1", "v1"))
    row = tmp_db.fetch_one("SELECT value FROM settings WHERE key = ?", ("k1",))
    assert row is not None
    assert row["value"] == "v1"

    rows = tmp_db.fetch_all("SELECT key FROM settings")
    assert len(rows) == 1
    assert rows[0]["key"] == "k1"


def test_foreign_key_constraint(tmp_db: Database):
    with pytest.raises(sqlite3.IntegrityError):
        tmp_db.execute(
            "INSERT INTO messages (id, conversation_id, role, content) "
            "VALUES ('m1', 'nonexistent', 'user', 'hello')"
        )


def test_close_and_reopen(tmp_db: Database):
    tmp_db.execute(
        "INSERT INTO settings (key, value) VALUES (?, ?)", ("persist", "yes")
    )
    db_path = tmp_db.db_path
    tmp_db.close()

    db2 = Database(db_path=db_path)
    db2.connect()
    try:
        row = db2.fetch_one("SELECT value FROM settings WHERE key = ?", ("persist",))
        assert row is not None
        assert row["value"] == "yes"
    finally:
        db2.close()
