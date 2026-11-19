"""Tests for account link create, list, delete."""

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
        db = Path(tmp) / "links_test.db"
        monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
        monkeypatch.setenv("DATABASE_PATH", str(db))
        yield db


@respx.mock
def test_create_link(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
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

    link_resp = client.post(
        "/api/simplefin/links",
        json={
            "connection_id": conn_id,
            "simplefin_account_id": "sfin-1",
            "firefly_account_id": 42,
        },
    )
    assert link_resp.status_code == 200
    data = link_resp.json()
    assert data["connection_id"] == conn_id
    assert data["simplefin_account_id"] == "sfin-1"
    assert data["firefly_account_id"] == 42
    assert "id" in data
    assert "created_at" in data

    list_resp = client.get("/api/simplefin/links")
    assert len(list_resp.json()) == 1
    assert list_resp.json()[0]["firefly_account_id"] == 42


def test_create_link_connection_not_found(
    temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    client = TestClient(app)
    response = client.post(
        "/api/simplefin/links",
        json={
            "connection_id": "nonexistent",
            "simplefin_account_id": "sfin-1",
            "firefly_account_id": 42,
        },
    )
    assert response.status_code == 404


@respx.mock
def test_create_link_replaces_existing_firefly_account(
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

    client.post(
        "/api/simplefin/links",
        json={"connection_id": conn_id, "simplefin_account_id": "sfin-1", "firefly_account_id": 100},
    )
    client.post(
        "/api/simplefin/links",
        json={"connection_id": conn_id, "simplefin_account_id": "sfin-2", "firefly_account_id": 100},
    )
    links = client.get("/api/simplefin/links").json()
    assert len(links) == 1
    assert links[0]["simplefin_account_id"] == "sfin-2"
    assert links[0]["firefly_account_id"] == 100


@respx.mock
def test_list_links_filter_by_connection(
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
    client.post(
        "/api/simplefin/links",
        json={"connection_id": conn_id, "simplefin_account_id": "s1", "firefly_account_id": 1},
    )

    response = client.get("/api/simplefin/links", params={"connection_id": conn_id})
    assert response.status_code == 200
    assert len(response.json()) == 1
    response2 = client.get("/api/simplefin/links", params={"connection_id": "other-id"})
    assert response2.json() == []


@respx.mock
def test_delete_link(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
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
    link_resp = client.post(
        "/api/simplefin/links",
        json={"connection_id": conn_id, "simplefin_account_id": "s1", "firefly_account_id": 1},
    )
    link_id = link_resp.json()["id"]

    del_resp = client.delete(f"/api/simplefin/links/{link_id}")
    assert del_resp.status_code == 204
    assert client.get("/api/simplefin/links").json() == []


def test_delete_link_404(temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))
    client = TestClient(app)
    response = client.delete("/api/simplefin/links/nonexistent-link-id")
    assert response.status_code == 404
