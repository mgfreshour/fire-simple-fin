"""Tests for POST /api/simplefin/push."""

import base64

import pytest
from fastapi.testclient import TestClient

from firesimplefin.main import app


@pytest.fixture
def encryption_key() -> str:
    return base64.standard_b64encode(b"k" * 32).decode()


def test_push_404_when_not_linked(
    encryption_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "push.db"))
    client = TestClient(app)
    response = client.post(
        "/api/simplefin/push",
        json={
            "firefly_account_id": 999,
            "transactions": [],
        },
    )
    assert response.status_code == 404
    assert "not linked" in response.json().get("detail", "").lower()


def test_push_503_when_firefly_not_configured(
    encryption_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_base_url", None)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_token", None)
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "push.db"))
    from firesimplefin.storage import ConnectionStore, LinkStore

    store = ConnectionStore(encryption_key=encryption_key, db_path=tmp_path / "push.db")
    store.create("https://u:p@h.example/a", label=None)
    conn_id = store.list_connections()[0].id
    link_store = LinkStore(db_path=tmp_path / "push.db")
    link_store.create_or_replace(conn_id, "sfin-1", 123)

    client = TestClient(app)
    response = client.post(
        "/api/simplefin/push",
        json={
            "firefly_account_id": 123,
            "transactions": [],
        },
    )
    assert response.status_code == 503
    assert "Firefly" in response.json().get("detail", "")


def test_push_202_accepted_with_job_id(
    encryption_key: str, monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_base_url", "https://ff.example")
    monkeypatch.setattr("firesimplefin.config.settings.firefly_token", "tk")
    monkeypatch.setenv("DATABASE_PATH", str(tmp_path / "push.db"))
    from firesimplefin.storage import ConnectionStore, LinkStore

    store = ConnectionStore(encryption_key=encryption_key, db_path=tmp_path / "push.db")
    store.create("https://u:p@h.example/a", label=None)
    conn_id = store.list_connections()[0].id
    link_store = LinkStore(db_path=tmp_path / "push.db")
    link_store.create_or_replace(conn_id, "sfin-1", 123)

    client = TestClient(app)
    response = client.post(
        "/api/simplefin/push",
        json={
            "firefly_account_id": 123,
            "transactions": [],
        },
    )
    assert response.status_code == 202
    data = response.json()
    assert "job_id" in data
    assert response.headers.get("X-Running-Background-Jobs") is not None


def test_push_status_404_for_unknown_job() -> None:
    client = TestClient(app)
    response = client.get("/api/simplefin/push/status/unknown-job-id")
    assert response.status_code == 404
    assert response.headers.get("X-Running-Background-Jobs") is not None
