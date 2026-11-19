"""Tests for encrypted connection storage."""

import tempfile
from pathlib import Path

import pytest

from firesimplefin.storage import (
    ConnectionStore,
    LinkStore,
    decrypt_access_url,
    encrypt_access_url,
)


def test_encrypt_decrypt_roundtrip() -> None:
    import base64
    env_key = base64.standard_b64encode(b"1" * 32).decode()
    plain = "https://user:secret@host/path"
    cipher = encrypt_access_url(plain, env_key)
    assert isinstance(cipher, bytes)
    assert decrypt_access_url(cipher, env_key) == plain


def test_encrypt_decrypt_with_openssl_style_key() -> None:
    import base64
    key_bytes = b"a" * 32
    env_key = base64.standard_b64encode(key_bytes).decode()
    plain = "https://u:p@example.com/access/xyz"
    cipher = encrypt_access_url(plain, env_key)
    assert decrypt_access_url(cipher, env_key) == plain


def test_decrypt_wrong_key_fails() -> None:
    import base64
    k1 = base64.standard_b64encode(b"1" * 32).decode()
    k2 = base64.standard_b64encode(b"2" * 32).decode()
    cipher = encrypt_access_url("https://x@y.z/a", k1)
    with pytest.raises(ValueError, match="Decryption"):
        decrypt_access_url(cipher, k2)


def test_connection_store_create_and_retrieve() -> None:
    import base64
    key = base64.standard_b64encode(b"k" * 32).decode()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = ConnectionStore(encryption_key=key, db_path=db)
        record = store.create("https://user:pass@host/access/abc", label="My Bank")
        assert record.id
        assert record.label == "My Bank"
        assert record.created_at

        access_url = store.get_access_url(record.id)
        assert access_url == "https://user:pass@host/access/abc"

        meta = store.get_connection(record.id)
        assert meta and meta.id == record.id and meta.label == record.label


def test_connection_store_get_unknown_returns_none() -> None:
    import base64
    key = base64.standard_b64encode(b"k" * 32).decode()
    with tempfile.TemporaryDirectory() as tmp:
        store = ConnectionStore(encryption_key=key, db_path=Path(tmp) / "test.db")
        assert store.get_access_url("nonexistent") is None
        assert store.get_connection("nonexistent") is None


def test_connection_store_list() -> None:
    import base64
    key = base64.standard_b64encode(b"k" * 32).decode()
    with tempfile.TemporaryDirectory() as tmp:
        store = ConnectionStore(encryption_key=key, db_path=Path(tmp) / "test.db")
        store.create("https://a@b/c1", label="First")
        store.create("https://a@b/c2", label="Second")
        listed = store.list_connections()
        assert len(listed) == 2
        ids = {r.id for r in listed}
        assert len(ids) == 2


def test_connection_store_delete() -> None:
    import base64
    key = base64.standard_b64encode(b"k" * 32).decode()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        store = ConnectionStore(encryption_key=key, db_path=db)
        record = store.create("https://a@b/c", label="One")
        assert store.delete(record.id) is True
        assert store.get_connection(record.id) is None
        assert store.delete("nonexistent") is False


def test_link_store_create_and_list() -> None:
    import base64
    key = base64.standard_b64encode(b"k" * 32).decode()
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "test.db"
        conn_store = ConnectionStore(encryption_key=key, db_path=db)
        conn = conn_store.create("https://a@b/c", label="Bank")
        link_store = LinkStore(db_path=db)
        link = link_store.create_or_replace(conn.id, "sfin-1", 100)
        assert link.connection_id == conn.id
        assert link.simplefin_account_id == "sfin-1"
        assert link.firefly_account_id == 100
        assert link_store.list_links(connection_id=conn.id) == [link]
        assert link_store.get_by_firefly_account_id(100) == link
        assert link_store.delete(link.id) is True
        assert link_store.list_links() == []
