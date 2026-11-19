"""Tests for connection list, connection accounts, and disconnect."""

import base64
import tempfile
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from firesimplefin.main import app


@pytest.fixture
def encryption_key() -> str:
    return base64.standard_b64encode(b"k" * 32).decode()


@pytest.fixture
def temp_db(encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "conn_test.db"
        monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
        monkeypatch.setenv("DATABASE_PATH", str(db))
        yield db


@respx.mock
def test_list_connections_empty(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    client = TestClient(app)
    response = client.get("/api/simplefin/connections")
    assert response.status_code == 200
    assert response.json() == []


@respx.mock
def test_list_connections_after_claim(
    temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://u:p@h.example/a"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))
    accounts_url = "https://u:p@h.example/a/accounts"
    respx.get(accounts_url).mock(
        return_value=respx.MockResponse(200, json={"accounts": [], "errors": []})
    )

    client = TestClient(app)
    claim_resp = client.post("/api/simplefin/claim", json={"setup_token": setup_token})
    assert claim_resp.status_code == 200
    conn_id = claim_resp.json()["connection_id"]

    list_resp = client.get("/api/simplefin/connections")
    assert list_resp.status_code == 200
    conns = list_resp.json()
    assert len(conns) == 1
    assert conns[0]["id"] == conn_id
    assert conns[0]["link_count"] == 0


@respx.mock
def test_get_connection_accounts(
    temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://u:p@h.example/a"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))
    accounts_url = "https://u:p@h.example/a/accounts"
    respx.get(accounts_url).mock(
        return_value=respx.MockResponse(
            200,
            json={
                "accounts": [
                    {"id": "1", "name": "Checking", "currency": "USD", "org": {"name": "Bank"}},
                ],
                "errors": [],
            },
        )
    )

    client = TestClient(app)
    claim_resp = client.post("/api/simplefin/claim", json={"setup_token": setup_token})
    conn_id = claim_resp.json()["connection_id"]

    acc_resp = client.get(f"/api/simplefin/connections/{conn_id}/accounts")
    assert acc_resp.status_code == 200
    accounts = acc_resp.json()
    assert len(accounts) == 1
    assert accounts[0]["id"] == "1"
    assert accounts[0]["name"] == "Checking"


def test_get_connection_accounts_404(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    client = TestClient(app)
    response = client.get("/api/simplefin/connections/nonexistent-id/accounts")
    assert response.status_code == 404


@respx.mock
def test_disconnect(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://u:p@h.example/a"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))
    respx.get("https://u:p@h.example/a/accounts").mock(
        return_value=respx.MockResponse(200, json={"accounts": [], "errors": []})
    )

    client = TestClient(app)
    claim_resp = client.post("/api/simplefin/claim", json={"setup_token": setup_token})
    conn_id = claim_resp.json()["connection_id"]

    del_resp = client.delete(f"/api/simplefin/connections/{conn_id}")
    assert del_resp.status_code == 204

    list_resp = client.get("/api/simplefin/connections")
    assert list_resp.json() == []


@respx.mock
def test_get_connection_accounts_403(
    temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://u:p@h.example/a"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))
    respx.get("https://u:p@h.example/a/accounts").mock(
        return_value=respx.MockResponse(200, json={"accounts": [], "errors": []})
    )
    client = TestClient(app)
    claim_resp = client.post("/api/simplefin/claim", json={"setup_token": setup_token})
    conn_id = claim_resp.json()["connection_id"]
    respx.get("https://u:p@h.example/a/accounts").mock(
        return_value=respx.MockResponse(403, text="Revoked")
    )
    acc_resp = client.get(f"/api/simplefin/connections/{conn_id}/accounts")
    assert acc_resp.status_code == 403
    assert "disable" in acc_resp.json().get("detail", "").lower() or "reconnect" in acc_resp.json().get("detail", "").lower()


def test_disconnect_404(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    client = TestClient(app)
    response = client.delete("/api/simplefin/connections/nonexistent-id")
    assert response.status_code == 404
