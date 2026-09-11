"""
Filename: store.py
Author: Christian Blank
Created Date: 2026-09-11
Description: SQLite storage for configuration, requests, audit events and notifications.
"""

import json
import os
import secrets
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA = """
CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE users (
 id INTEGER PRIMARY KEY, name TEXT NOT NULL, role TEXT NOT NULL DEFAULT 'member',
 status TEXT NOT NULL DEFAULT 'pending', auto_approve INTEGER NOT NULL DEFAULT 0,
 locale TEXT NOT NULL DEFAULT 'en-us', chat_id INTEGER);
CREATE TABLE admins (id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL);
CREATE TABLE sessions (token TEXT PRIMARY KEY, admin_id INTEGER NOT NULL, expires REAL NOT NULL);
CREATE TABLE invites (token TEXT PRIMARY KEY, expires REAL NOT NULL, used INTEGER NOT NULL DEFAULT 0);
CREATE TABLE requests (
 id INTEGER PRIMARY KEY, user_id INTEGER NOT NULL, media TEXT NOT NULL, options TEXT NOT NULL,
 identity TEXT NOT NULL, scope TEXT NOT NULL, state TEXT NOT NULL,
 created REAL NOT NULL, updated REAL NOT NULL, attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0, remote_id INTEGER, error TEXT NOT NULL DEFAULT '',
 progress TEXT NOT NULL DEFAULT '', reason TEXT NOT NULL DEFAULT '');
CREATE INDEX request_work ON requests(state, next_attempt);
CREATE TABLE events (id INTEGER PRIMARY KEY, request_id INTEGER, actor TEXT NOT NULL,
 action TEXT NOT NULL, at REAL NOT NULL, detail TEXT NOT NULL DEFAULT '');
CREATE TABLE outbox (id INTEGER PRIMARY KEY, event_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
 locale TEXT NOT NULL, key TEXT NOT NULL, payload TEXT NOT NULL,
 state TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
 next_attempt REAL NOT NULL DEFAULT 0, UNIQUE(event_id, chat_id));
CREATE TABLE operations (key TEXT PRIMARY KEY, state TEXT NOT NULL, remote_id INTEGER);
CREATE TABLE imports (digest TEXT PRIMARY KEY, at REAL NOT NULL);
"""


class Store:
    """One SQLite connection for application state in a local data directory.

    Writes use autocommit unless grouped with transaction(). Callers must not
    hold a transaction across an await, or share it with concurrent writers.
    close() releases the connection; the caller owns the directory and backups.
    """
    def __init__(self, directory: Path):
        """Open addarr.db, enable WAL and create the schema on first use.

        Raises RuntimeError if the database schema is newer than this application.
        The application lifespan owns the separate ProcessLock.
        """
        directory.mkdir(parents=True, exist_ok=True)
        self.directory = directory
        self.path = directory / "addarr.db"
        self.db = sqlite3.connect(self.path, isolation_level=None, check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute("PRAGMA busy_timeout=5000")
        self.db.execute("PRAGMA foreign_keys=ON")
        self.db.execute("PRAGMA synchronous=FULL")
        version = self.db.execute("PRAGMA user_version").fetchone()[0]
        if version > 1:
            self.db.close()
            raise RuntimeError("Database is newer than this Addarr version; restore a matching backup")
        if version == 0:
            self.db.executescript("BEGIN IMMEDIATE;" + SCHEMA + "PRAGMA user_version=1; COMMIT;")
        if os.name != "nt":
            self.path.chmod(0o600)

    @contextmanager
    def transaction(self) -> Iterator[None]:
        """Commit a group of synchronous writes, or roll back on any exception.

        Uses BEGIN IMMEDIATE. Nested transactions and network awaits inside this
        context are not supported.
        """
        self.db.execute("BEGIN IMMEDIATE")
        try:
            yield
            self.db.execute("COMMIT")
        except BaseException:
            self.db.execute("ROLLBACK")
            raise

    def all(self, sql: str, args: tuple[Any, ...] = ()) -> list[dict[str, Any]]:
        """Return matching rows as dictionaries using bound SQL parameters."""
        return [dict(row) for row in self.db.execute(sql, args).fetchall()]

    def one(self, sql: str, args: tuple[Any, ...] = ()) -> dict[str, Any] | None:
        """Return the first matching row, or None if the query has no result."""
        row = self.db.execute(sql, args).fetchone()
        return dict(row) if row else None

    def execute(self, sql: str, args: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        """Execute parameterized SQL and return its cursor without starting a transaction."""
        return self.db.execute(sql, args)

    def setting(self, key: str, default: Any = None) -> Any:
        """Decode a stored JSON setting, falling back to default only when the key is absent."""
        row = self.one("SELECT value FROM settings WHERE key=?", (key,))
        return json.loads(row["value"]) if row else default

    def set_setting(self, key: str, value: Any) -> None:
        """Insert or replace a JSON-serializable setting in the current transaction."""
        self.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, json.dumps(value)))

    def user(self, user_id: int) -> dict[str, Any] | None:
        """Return a Telegram user by numeric ID, or None if they have never contacted the bot."""
        return self.one("SELECT * FROM users WHERE id=?", (user_id,))

    def audit(self, actor: str, action: str, request_id: int | None = None, detail: str = "") -> int:
        """Append an audit event and return its ID; detail must not contain credentials."""
        row = self.execute(
            "INSERT INTO events(request_id,actor,action,at,detail) VALUES(?,?,?,?,?)",
            (request_id, actor, action, time.time(), detail),
        )
        assert row.lastrowid is not None
        return row.lastrowid

    def bootstrap_token(self) -> str:
        """Read the setup token, creating it with exclusive file creation if absent."""
        path = self.directory / "bootstrap-token"
        if not path.exists():
            fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w") as stream:
                stream.write(secrets.token_urlsafe(32))
        return path.read_text().strip()

    def backup(self, destination: Path) -> None:
        """Copy a consistent database snapshot using the SQLite backup API.

        Args:
            destination: Database path whose parent directory already exists.
                Callers choose a fresh path when overwriting is not intended.

        The snapshot includes credentials and sessions. POSIX permissions are
        restricted to the owner after the copy completes.
        """
        target = sqlite3.connect(destination)
        try:
            self.db.backup(target)
        finally:
            target.close()
        if os.name != "nt":
            destination.chmod(0o600)

    def close(self) -> None:
        """Close the database connection after its workers have stopped."""
        self.db.close()
