"""Store SimpleFIN account ↔ Firefly account links (Persistence-Design §3)."""

import sqlite3
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from firesimplefin.storage.connection_store import get_db_path, init_schema


@dataclass
class LinkRecord:
    """One account link: SimpleFIN (connection + account id) ↔ Firefly account id."""

    id: str
    connection_id: str
    simplefin_account_id: str
    firefly_account_id: int
    created_at: str  # ISO 8601
    last_sync_at: str | None = None
    last_push_at: str | None = None


class LinkStore:
    """
    CRUD for simplefin_account_links.
    One Firefly account at most one SimpleFIN link; one (connection, simplefin_account) at most one link.
    """

    def __init__(self, db_path: Path | None = None):
        self._db_path = db_path or get_db_path()

    def _connect(self) -> sqlite3.Connection:
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        init_schema(conn)
        return conn

    def create_or_replace(
        self,
        connection_id: str,
        simplefin_account_id: str,
        firefly_account_id: int,
    ) -> LinkRecord:
        """
        Create or replace a link. Ensures at most one link per Firefly account and per (connection, SimpleFIN account).
        Replaces any existing link for this firefly_account_id or (connection_id, simplefin_account_id).
        """
        link_id = str(uuid.uuid4())
        created = datetime.now(timezone.utc).isoformat()

        conn = self._connect()
        try:
            # Remove any existing link for this Firefly account (one Firefly account = one link)
            conn.execute(
                "DELETE FROM simplefin_account_links WHERE firefly_account_id = ?",
                (firefly_account_id,),
            )
            # Remove any existing link for this (connection, SimpleFIN account)
            conn.execute(
                "DELETE FROM simplefin_account_links WHERE connection_id = ? AND simplefin_account_id = ?",
                (connection_id, simplefin_account_id),
            )
            conn.execute(
                "INSERT INTO simplefin_account_links (id, connection_id, simplefin_account_id, firefly_account_id, created_at, last_sync_at, last_push_at) VALUES (?, ?, ?, ?, ?, NULL, NULL)",
                (link_id, connection_id, simplefin_account_id, firefly_account_id, created),
            )
            conn.commit()
            return LinkRecord(
                id=link_id,
                connection_id=connection_id,
                simplefin_account_id=simplefin_account_id,
                firefly_account_id=firefly_account_id,
                created_at=created,
                last_sync_at=None,
                last_push_at=None,
            )
        finally:
            conn.close()

    def list_links(
        self,
        connection_id: str | None = None,
        firefly_account_id: int | None = None,
    ) -> list[LinkRecord]:
        """List links, optionally filtered by connection_id and/or firefly_account_id."""
        conn = self._connect()
        try:
            cols = "id, connection_id, simplefin_account_id, firefly_account_id, created_at, last_sync_at, last_push_at"
            if connection_id is not None and firefly_account_id is not None:
                rows = conn.execute(
                    f"SELECT {cols} FROM simplefin_account_links WHERE connection_id = ? AND firefly_account_id = ? ORDER BY created_at",
                    (connection_id, firefly_account_id),
                ).fetchall()
            elif connection_id is not None:
                rows = conn.execute(
                    f"SELECT {cols} FROM simplefin_account_links WHERE connection_id = ? ORDER BY created_at",
                    (connection_id,),
                ).fetchall()
            elif firefly_account_id is not None:
                rows = conn.execute(
                    f"SELECT {cols} FROM simplefin_account_links WHERE firefly_account_id = ? ORDER BY created_at",
                    (firefly_account_id,),
                ).fetchall()
            else:
                rows = conn.execute(
                    f"SELECT {cols} FROM simplefin_account_links ORDER BY created_at"
                ).fetchall()
            return [
                LinkRecord(
                    id=r["id"],
                    connection_id=r["connection_id"],
                    simplefin_account_id=r["simplefin_account_id"],
                    firefly_account_id=r["firefly_account_id"],
                    created_at=r["created_at"],
                    last_sync_at=r["last_sync_at"] if "last_sync_at" in r.keys() else None,
                    last_push_at=r["last_push_at"] if "last_push_at" in r.keys() else None,
                )
                for r in rows
            ]
        finally:
            conn.close()

    def get_link(self, link_id: str) -> LinkRecord | None:
        """Return link by id."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT id, connection_id, simplefin_account_id, firefly_account_id, created_at, last_sync_at, last_push_at FROM simplefin_account_links WHERE id = ?",
                (link_id,),
            ).fetchone()
            if not row:
                return None
            return LinkRecord(
                id=row["id"],
                connection_id=row["connection_id"],
                simplefin_account_id=row["simplefin_account_id"],
                firefly_account_id=row["firefly_account_id"],
                created_at=row["created_at"],
                last_sync_at=row["last_sync_at"] if "last_sync_at" in row.keys() else None,
                last_push_at=row["last_push_at"] if "last_push_at" in row.keys() else None,
            )
        finally:
            conn.close()

    def get_by_firefly_account_id(self, firefly_account_id: int) -> LinkRecord | None:
        """Return the link for this Firefly account, if any."""
        links = self.list_links(firefly_account_id=firefly_account_id)
        return links[0] if links else None

    def delete(self, link_id: str) -> bool:
        """Delete link by id. Returns True if deleted, False if not found."""
        conn = self._connect()
        try:
            cur = conn.execute("DELETE FROM simplefin_account_links WHERE id = ?", (link_id,))
            conn.commit()
            return cur.rowcount > 0
        finally:
            conn.close()

    def delete_by_connection_id(self, connection_id: str) -> int:
        """Delete all links for a connection. Returns number of links deleted."""
        conn = self._connect()
        try:
            cur = conn.execute(
                "DELETE FROM simplefin_account_links WHERE connection_id = ?",
                (connection_id,),
            )
            conn.commit()
            return cur.rowcount
        finally:
            conn.close()

    def count_links_for_connection(self, connection_id: str) -> int:
        """Return number of links for a connection (for connection list)."""
        conn = self._connect()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM simplefin_account_links WHERE connection_id = ?",
                (connection_id,),
            ).fetchone()
            return row["n"] if row else 0
        finally:
            conn.close()

    def set_last_sync(self, firefly_account_id: int) -> None:
        """Record that a sync (pull) was completed for this linked account."""
        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE simplefin_account_links SET last_sync_at = ? WHERE firefly_account_id = ?",
                (now, firefly_account_id),
            )
            conn.commit()
        finally:
            conn.close()

    def set_last_push(self, firefly_account_id: int) -> None:
        """Record that a push was completed for this linked account."""
        conn = self._connect()
        try:
            now = datetime.now(timezone.utc).isoformat()
            conn.execute(
                "UPDATE simplefin_account_links SET last_push_at = ? WHERE firefly_account_id = ?",
                (now, firefly_account_id),
            )
            conn.commit()
        finally:
            conn.close()
