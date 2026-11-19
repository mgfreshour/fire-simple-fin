"""Tests for POST /api/simplefin/claim."""

import base64
import tempfile
from pathlib import Path

import pytest
import respx
from fastapi.testclient import TestClient

from firesimplefin.main import app


@pytest.fixture
def encryption_key() -> str:
    return base64.standard_b64encode(b"t" * 32).decode()


@pytest.fixture
def temp_db(encryption_key: str, monkeypatch: pytest.MonkeyPatch) -> Path:
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "claim_test.db"
        monkeypatch.setenv("DATABASE_PATH", str(db))
        monkeypatch.setenv("ENCRYPTION_KEY", encryption_key)
        yield db


@respx.mock
def test_claim_success_returns_connection_and_accounts(
    temp_db: Path, encryption_key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    from firesimplefin.config import settings
    monkeypatch.setattr(settings, "encryption_key", encryption_key)
    monkeypatch.setenv("DATABASE_PATH", str(temp_db))

    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://user:secret@bridge.simplefin.org/access/xyz"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()

    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))
    accounts_url = "https://user:secret@bridge.simplefin.org/access/xyz/accounts"
    respx.get(accounts_url).mock(
        return_value=respx.MockResponse(
            200,
            json={
                "accounts": [
                    {"id": "1", "name": "Checking", "currency": "USD", "org": {"name": "Bank"}}
                ],
                "errors": [],
            },
        )
    )

    client = TestClient(app)
    response = client.post(
        "/api/simplefin/claim",
        json={"setup_token": setup_token},
    )

    assert response.status_code == 200
    data = response.json()
    assert "connection_id" in data
    assert data["connection_id"]
    assert len(data["accounts"]) == 1
    assert data["accounts"][0]["id"] == "1"
    assert data["accounts"][0]["name"] == "Checking"
    assert data["accounts"][0]["currency"] == "USD"
    assert data["accounts"][0]["org_name"] == "Bank"
    assert "errors" in data


@respx.mock
def test_claim_403_returns_forbidden() -> None:
    claim_url = "https://bridge.simplefin.org/claim/used"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(403, text="Forbidden"))

    client = TestClient(app)
    response = client.post("/api/simplefin/claim", json={"setup_token": setup_token})

    assert response.status_code == 403
    assert "disable" in response.json().get("detail", "").lower() or "rejected" in response.json().get("detail", "").lower()


@respx.mock
def test_claim_without_encryption_key_returns_503(monkeypatch: pytest.MonkeyPatch) -> None:
    from firesimplefin.config import settings
    monkeypatch.setattr(settings, "encryption_key", None)
    claim_url = "https://bridge.simplefin.org/claim/abc"
    access_url = "https://u:p@h.example/a"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()
    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))

    client = TestClient(app)
    response = client.post("/api/simplefin/claim", json={"setup_token": setup_token})

    assert response.status_code == 503
    assert "ENCRYPTION_KEY" in response.json().get("detail", "")


def test_claim_missing_setup_token() -> None:
    client = TestClient(app)
    response = client.post("/api/simplefin/claim", json={})
    assert response.status_code == 422
