"""Store SimpleFIN connections with encrypted Access URL (Persistence-Design §3, §5)."""

import os
import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from firesimplefin.storage.encryption import decrypt_access_url, encrypt_access_url

# Access URL is never written to logs or returned in API responses; only used internally.


@dataclass
class ConnectionRecord:
    """One SimpleFIN connection (id, label, created_at). Access URL stored encrypted, never exposed."""

    id: str
    label: str | None
    created_at: str  # ISO 8601


def _db_path() -> Path:
    path = os.getenv("DATABASE_PATH")
    if path:
        return Path(path)
    return Path(__file__).resolve().parent.parent.parent.parent / "data" / "firesimplefin.db"


def _migrate_links_add_last_dates(conn: sqlite3.Connection) -> None:
    """Add last_sync_at and last_push_at to simplefin_account_links if missing."""
    try:
        rows = conn.execute("PRAGMA table_info(simplefin_account_links)").fetchall()
        if not rows:
            return  # Table not created yet
        names = [r[1] for r in rows]
        if "last_sync_at" not in names:
            conn.execute("ALTER TABLE simplefin_account_links ADD COLUMN last_sync_at TEXT")
        if "last_push_at" not in names:
            conn.execute("ALTER TABLE simplefin_account_links ADD COLUMN last_push_at TEXT")
    except sqlite3.OperationalError:
        pass


def _init_db(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS simplefin_connections (
          id TEXT PRIMARY KEY,
          label TEXT,
          access_url_encrypted BLOB NOT NULL,
          created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS simplefin_account_links (
          id TEXT PRIMARY KEY,
          connection_id TEXT NOT NULL REFERENCES simplefin_connections(id) ON DELETE CASCADE,
          simplefin_account_id TEXT NOT NULL,
          firefly_account_id INTEGER NOT NULL,
          created_at TEXT NOT NULL,
          last_sync_at TEXT,
          last_push_at TEXT,
          UNIQUE(connection_id, simplefin_account_id),
          UNIQUE(firefly_account_id)
        )
        """
    )
    _migrate_links_add_last_dates(conn)
    conn.commit()


class ConnectionStore:
    """
    Persist one or more SimpleFIN connections.
    Access URL is encrypted at rest; never logged or returned to callers.
    """

    def __init__(self, encryption_key: str, db_path: Path | None = None):
        if not encryption_key or not encryption_key.strip():
            raise ValueError("ENCRYPTION_KEY is required for connection storage")
        self._encryption_key = encryption_key.strip()
        self._db_path = db_path or _db_path()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        _init_db(conn)
        return conn

    def create(self, access_url: str, label: str | None = None) -> ConnectionRecord:
        """Store a new connection. Access URL is encrypted; never logged."""
        conn_id = str(uuid.uuid4())
        created = datetime.now(timezone.utc).isoformat()
        encrypted = encrypt_access_url(access_url, self._encryption_key)
        conn = self._connect()
        try:
            conn.execute(
                "INSERT INTO simplefin_connections (id, label, access_url_encrypted, created_at) VALUES (?, ?, ?, ?)",
                (conn_id, label, encrypted, created),
            )
            conn.commit()
            return ConnectionRecord(id=conn_id, label=label, created_at=created)
        finally:
            conn.close()

    def get_access_url(self, connection_id: str) -> str | None:
        """Return decrypted Access URL for the connection, or None if not found. Caller must not log or expose it."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT access_url_encrypted FROM simplefin_connections WHERE id = ?",
                (connection_id,),
            ).fetchone()
            if not row:
                return None
            return decrypt_access_url(bytes(row["access_url_encrypted"]), self._encryption_key)
        finally:
            conn.close()

    def get_connection(self, connection_id: str) -> ConnectionRecord | None:
        """Return connection metadata (no Access URL)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, label, created_at FROM simplefin_connections WHERE id = ?",
                (connection_id,),
            ).fetchone()
            if not row:
                return None
            return ConnectionRecord(
                id=row["id"],
                label=row["label"],
                created_at=row["created_at"],
            )
        finally:
            conn.close()

    def list_connections(self) -> list[ConnectionRecord]:
        """List all connections (metadata only; no Access URL)."""
        conn = self._connect()
        try:
            rows = conn.execute(
                "SELECT id, label, created_at FROM simplefin_connections ORDER BY created_at"
            ).fetchall()
            return [
                ConnectionRecord(id=r["id"], label=r["label"], created_at=r["created_at"])
                for r in rows
            ]
        finally:
            conn.close()

    def delete(self, connection_id: str) -> bool:
        """Delete connection and its links. Returns True if deleted, False if not found."""
        conn = self._connect()
        try:
            # Delete links first (SQLite does not enforce FK CASCADE by default)
            conn.execute("DELETE FROM simplefin_account_links WHERE connection_id = ?", (connection_id,))
            cur = conn.execute("DELETE FROM simplefin_connections WHERE id = ?", (connection_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()


def get_db_path() -> Path:
    """Return default DB path for use by other stores (e.g. LinkStore)."""
    return _db_path()


def init_schema(conn: sqlite3.Connection) -> None:
    """Ensure all tables exist. Used by LinkStore."""
    _init_db(conn)
