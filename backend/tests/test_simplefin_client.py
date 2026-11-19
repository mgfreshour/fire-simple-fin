"""Unit tests for SimpleFIN client (claim + fetch) with mocked HTTP."""

import base64

import pytest
import respx

from firesimplefin.simplefin_client import (
    SimpleFINClaimError,
    SimpleFINFetchError,
    claim,
    fetch_accounts,
)
from firesimplefin.simplefin_models import SimpleFINAccountSet


@respx.mock
def test_claim_success() -> None:
    claim_url = "https://bridge.simplefin.org/claim/abc123"
    access_url = "https://user:secret@bridge.simplefin.org/access/xyz"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()

    respx.post(claim_url).mock(return_value=respx.MockResponse(200, text=access_url))

    result = claim(setup_token, timeout=5.0)
    assert result == access_url
    assert respx.calls.call_count == 1
    call = respx.calls.last
    assert call.request.method == "POST"
    assert call.request.content == b""


@respx.mock
def test_claim_403_returns_safe_message() -> None:
    claim_url = "https://bridge.simplefin.org/claim/used"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()

    respx.post(claim_url).mock(return_value=respx.MockResponse(403, text="Forbidden"))

    with pytest.raises(SimpleFINClaimError) as exc_info:
        claim(setup_token, timeout=5.0)
    assert exc_info.value.status_code == 403
    assert "disable" in exc_info.value.safe_message.lower() or "rejected" in exc_info.value.safe_message.lower()


@respx.mock
def test_claim_invalid_token() -> None:
    with pytest.raises(SimpleFINClaimError) as exc_info:
        claim("not-valid-base64!!!", timeout=5.0)
    assert exc_info.value.safe_message
    assert respx.calls.call_count == 0


def test_claim_empty_token() -> None:
    with pytest.raises(SimpleFINClaimError) as exc_info:
        claim("", timeout=5.0)
    assert "required" in exc_info.value.safe_message.lower()


@respx.mock
def test_claim_http_only_rejected() -> None:
    claim_url = "http://insecure.example/claim"
    setup_token = base64.standard_b64encode(claim_url.encode()).decode()

    with pytest.raises(SimpleFINClaimError) as exc_info:
        claim(setup_token, timeout=5.0)
    assert "HTTPS" in str(exc_info.value) or "https" in str(exc_info.value).lower()
    assert respx.calls.call_count == 0


@respx.mock
def test_fetch_accounts_success() -> None:
    access_url = "https://user:secret@bridge.simplefin.org/access/xyz"
    accounts_url = "https://user:secret@bridge.simplefin.org/access/xyz/accounts"

    payload = {
        "accounts": [
            {
                "id": "2930002",
                "name": "Savings",
                "currency": "USD",
                "org": {"name": "Test Bank", "domain": "test.com"},
            }
        ],
        "errors": [],
    }
    respx.get(accounts_url).mock(return_value=respx.MockResponse(200, json=payload))

    result = fetch_accounts(access_url, balances_only=True, timeout=5.0)
    assert isinstance(result, SimpleFINAccountSet)
    assert len(result.accounts) == 1
    assert result.accounts[0].id == "2930002"
    assert result.accounts[0].name == "Savings"
    assert result.accounts[0].currency == "USD"
    assert result.errors == []
    assert respx.calls.call_count == 1
    call = respx.calls.last
    assert "balances-only=1" in str(call.request.url)


@respx.mock
def test_fetch_accounts_with_query_params() -> None:
    access_url = "https://u:p@h.example/path"
    accounts_url = "https://u:p@h.example/path/accounts"

    respx.get(accounts_url).mock(
        return_value=respx.MockResponse(200, json={"accounts": [], "errors": []})
    )

    fetch_accounts(
        access_url,
        start_date=1000000,
        end_date=2000000,
        account_ids=["id1", "id2"],
        pending=True,
        timeout=5.0,
    )
    call = respx.calls.last
    q = str(call.request.url)
    assert "start-date=1000000" in q
    assert "end-date=2000000" in q
    assert "account=id1" in q
    assert "account=id2" in q
    assert "pending=1" in q


@respx.mock
def test_fetch_accounts_empty_and_errors() -> None:
    access_url = "https://u:p@h.example/p"
    accounts_url = "https://u:p@h.example/p/accounts"

    payload = {"accounts": [], "errors": ["Rate limit warning"]}
    respx.get(accounts_url).mock(return_value=respx.MockResponse(200, json=payload))

    result = fetch_accounts(access_url, timeout=5.0)
    assert len(result.accounts) == 0
    assert result.errors == ["Rate limit warning"]


@respx.mock
def test_fetch_accounts_403() -> None:
    access_url = "https://u:p@h.example/p"
    accounts_url = "https://u:p@h.example/p/accounts"

    respx.get(accounts_url).mock(return_value=respx.MockResponse(403, text="Revoked"))

    with pytest.raises(SimpleFINFetchError) as exc_info:
        fetch_accounts(access_url, timeout=5.0)
    assert exc_info.value.status_code == 403
    assert any("disable" in e.lower() or "reconnect" in e.lower() for e in exc_info.value.errors)


@respx.mock
def test_fetch_http_only_rejected() -> None:
    access_url = "http://u:p@insecure.example/p"
    with pytest.raises(ValueError, match="HTTPS"):
        fetch_accounts(access_url, timeout=5.0)
    assert respx.calls.call_count == 0
