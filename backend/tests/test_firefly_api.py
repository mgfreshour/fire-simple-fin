"""Tests for GET /api/firefly/accounts."""

import pytest
from fastapi.testclient import TestClient

from firesimplefin.main import app


def test_firefly_accounts_503_when_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("firesimplefin.config.settings.firefly_base_url", None)
    monkeypatch.setattr("firesimplefin.config.settings.firefly_token", None)
    client = TestClient(app)
    response = client.get("/api/firefly/accounts")
    assert response.status_code == 503
    assert "Firefly" in response.json().get("detail", "")
