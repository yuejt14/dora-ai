"""Tests for migration 002_add_souls — souls table, character_state, triggers."""

import json

import pytest

from backend.db.database import Database
from backend.soul.state import CharacterState


@pytest.fixture
def db(tmp_db: Database) -> Database:
    """tmp_db already has all migrations applied (including 002)."""
    return tmp_db


class TestSoulsTable:
    def test_insert_soul(self, db: Database) -> None:
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", "Soul 1", "hash1", "{}", 0),
        )
        row = db.fetch_one("SELECT * FROM souls WHERE id = ?", ("s1",))
        assert row is not None
        assert row["name"] == "Soul 1"

    def test_single_active_trigger_on_update(self, db: Database) -> None:
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", "Soul 1", "h1", "{}", 1),
        )
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s2", "Soul 2", "h2", "{}", 0),
        )

        # Activate s2 — s1 should be deactivated
        db.execute("UPDATE souls SET is_active = 1 WHERE id = ?", ("s2",))

        active = db.fetch_all("SELECT id FROM souls WHERE is_active = 1")
        assert len(active) == 1
        assert active[0]["id"] == "s2"

    def test_single_active_trigger_on_insert(self, db: Database) -> None:
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", "Soul 1", "h1", "{}", 1),
        )
        # Insert s2 as active — should deactivate s1
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s2", "Soul 2", "h2", "{}", 1),
        )

        active = db.fetch_all("SELECT id FROM souls WHERE is_active = 1")
        assert len(active) == 1
        assert active[0]["id"] == "s2"

    def test_no_op_update_doesnt_trigger(self, db: Database) -> None:
        """Updating already-active soul should not fire the trigger."""
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s1", "Soul 1", "h1", "{}", 1),
        )
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition, is_active) "
            "VALUES (?, ?, ?, ?, ?)",
            ("s2", "Soul 2", "h2", "{}", 1),
        )
        # Now only s2 is active. Update s2's hash (is_active stays 1)
        db.execute("UPDATE souls SET yaml_hash = 'h2_new' WHERE id = ?", ("s2",))

        active = db.fetch_all("SELECT id FROM souls WHERE is_active = 1")
        assert len(active) == 1
        assert active[0]["id"] == "s2"


class TestCharacterStateTable:
    def test_insert_and_read_state(self, db: Database) -> None:
        db.execute(
            "INSERT INTO souls (id, name, yaml_hash, definition) VALUES (?, ?, ?, ?)",
            ("s1", "Soul", "h", "{}"),
        )
        cs = CharacterState(soul_id="s1", total_turns=10)
        db.execute(
            "INSERT INTO character_state (soul_id, state_json) VALUES (?, ?)",
            ("s1", cs.model_dump_json()),
        )

        row = db.fetch_one("SELECT state_json FROM character_state WHERE soul_id = ?", ("s1",))
        assert row is not None
        loaded = CharacterState.model_validate_json(row["state_json"])
        assert loaded.soul_id == "s1"
        assert loaded.total_turns == 10

    def test_foreign_key_enforced(self, db: Database) -> None:
        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO character_state (soul_id, state_json) VALUES (?, ?)",
                ("nonexistent", "{}"),
            )
