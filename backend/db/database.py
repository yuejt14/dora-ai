"""SQLite connection manager, migration runner, and query helpers."""

import sqlite3
from pathlib import Path

from backend.config import DB_PATH, get_logger

log = get_logger(__name__)


class Database:
    """SQLite database with WAL mode, migration support, and query helpers."""

    def __init__(self, db_path: Path = DB_PATH) -> None:
        self.db_path = db_path
        self._conn: sqlite3.Connection | None = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("Database not connected — call connect() first")
        return self._conn

    def connect(self) -> None:
        """Open connection with WAL mode and foreign keys enabled."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._conn.execute("PRAGMA busy_timeout=5000")
        log.info("Connected to %s", self.db_path)

    def close(self) -> None:
        """Close the database connection."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
            log.info("Closed database connection")

    # ── Migrations ────────────────────────────────────────────────────────

    def run_migrations(self, migrations_dir: Path | None = None) -> None:
        """Apply unapplied SQL migration files in order."""
        if migrations_dir is None:
            migrations_dir = Path(__file__).parent / "migrations"

        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS _migrations ("
            "  name TEXT PRIMARY KEY,"
            "  applied_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP"
            ")"
        )

        applied = {
            row["name"]
            for row in self.conn.execute("SELECT name FROM _migrations").fetchall()
        }

        migration_files = sorted(migrations_dir.glob("*.sql"))
        for path in migration_files:
            if path.name in applied:
                continue
            log.info("Applying migration: %s", path.name)
            sql = path.read_text()
            self.conn.executescript(sql)
            self.conn.execute("INSERT INTO _migrations (name) VALUES (?)", (path.name,))
            self.conn.commit()

    # ── Query helpers ─────────────────────────────────────────────────────

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        """Execute a statement and commit."""
        cursor = self.conn.execute(sql, params)
        self.conn.commit()
        return cursor

    def fetch_one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        """Fetch a single row."""
        return self.conn.execute(sql, params).fetchone()

    def fetch_all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        """Fetch all rows."""
        return self.conn.execute(sql, params).fetchall()
