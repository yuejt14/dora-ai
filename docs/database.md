# Database

## Schema

```sql
CREATE TABLE conversations (
    id          TEXT PRIMARY KEY,
    title       TEXT,
    soul_id     TEXT NOT NULL,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE messages (
    id              TEXT PRIMARY KEY,
    conversation_id TEXT NOT NULL REFERENCES conversations(id),
    role            TEXT NOT NULL CHECK(role IN ('user', 'assistant', 'system')),
    content         TEXT NOT NULL,
    emotion         TEXT,
    token_count     INTEGER,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE memories (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL CHECK(type IN ('fact', 'summary', 'preference', 'event')),
    content         TEXT NOT NULL,
    source_msg_id   TEXT REFERENCES messages(id),
    importance      REAL DEFAULT 0.5,
    last_accessed   TIMESTAMP,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE VIRTUAL TABLE memory_vectors USING vec0(
    id TEXT PRIMARY KEY,
    embedding float[768]
);

CREATE TABLE souls (
    id          TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    definition  TEXT NOT NULL,
    is_active   BOOLEAN DEFAULT 0,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
```

## Migrations

Numbered SQL files in `backend/db/migrations/` (e.g., `001_initial.sql`, `002_add_memories.sql`).

- `database.py` tracks applied migrations in a `_migrations` table.
- On startup, apply unapplied migrations in order.
- No Alembic — just ordered SQL files.

## sqlite-vec

Requires loading as an extension:
```python
db.enable_load_extension(True)
sqlite_vec.load(db)
```

If loading fails, fall back to SQL LIKE queries for memory search.
