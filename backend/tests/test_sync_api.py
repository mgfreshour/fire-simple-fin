"""Tests for POST /api/simplefin/sync."""

import base64

import pytest
import respx
from fastapi.testclient import TestClient

from firesimplefin.main import app


@pytest.fixture
def encryption_key() -> str:
    return base64.standard_b64encode(b"k" * 32).decode()


def test_sync_404_when_not_linked(
    encryption_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sync.db"))
    client = TestClient(app)
    response = client.post(
        "/api/simplefin/sync",
        json={
            "firefly_account_id": 999,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
    )
    assert response.status_code == 404
    assert "not linked" in response.json().get("detail", "").lower()


@respx.mock
def test_sync_503_when_firefly_not_configured(
    encryption_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_base_url", None)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_token", None)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "sync.db"))
    respx.get("https://u:p@h.example/a/accounts").mock(
        return_value=respx.MockResponse(200, json={"accounts": [], "errors": []})
    )
    from firesimplefin.storage import ConnectionStore, LinkStore
    store = ConnectionStore(encryption_key=encryption_key, db_path=tmp_path / "sync.db")
    store.create("https://u:p@h.example/a", label=None)
    conn_id = store.list_connections()[0].id
    link_store = LinkStore(db_path=tmp_path / "sync.db")
    link_store.create_or_replace(conn_id, "sfin-1", 123)

    client = TestClient(app)
    response = client.post(
        "/api/simplefin/sync",
        json={
            "firefly_account_id": 123,
            "start_date": "2024-01-01",
            "end_date": "2024-01-31",
        },
    )
    assert response.status_code == 503
    assert "Firefly" in response.json().get("detail", "")
