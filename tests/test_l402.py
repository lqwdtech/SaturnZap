"""Tests for the L402 module — parsing, caching, and fetch flow."""

from __future__ import annotations

import json
from unittest.mock import patch

import httpx
import pytest
from typer.testing import CliRunner

from saturnzap import l402
from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    """Point data dir to a temp directory."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


# ── Parsing tests ────────────────────────────────────────────────


def test_parse_l402_macaroon_invoice_quoted():
    header = 'LSAT macaroon="AgBheLJ0ZXN0", invoice="lnsb100n1p0..."'
    c = l402.parse_l402_challenge(header)
    assert c.macaroon == "AgBheLJ0ZXN0"
    assert c.invoice == "lnsb100n1p0..."


def test_parse_l402_scheme():
    header = 'L402 macaroon="mac123abc", invoice="lntbs100..."'
    c = l402.parse_l402_challenge(header)
    assert c.macaroon == "mac123abc"
    assert c.invoice == "lntbs100..."


def test_parse_l402_simple_format():
    header = 'LSAT AgBheLJ0ZXN0, invoice="lnsb100n1p0xyz"'
    c = l402.parse_l402_challenge(header)
    assert c.macaroon == "AgBheLJ0ZXN0"
    assert c.invoice == "lnsb100n1p0xyz"


def test_parse_l402_unquoted():
    header = "LSAT macaroon=AgBheLJ0ZXN0, invoice=lnsb100n1p0abc"
    c = l402.parse_l402_challenge(header)
    assert c.macaroon == "AgBheLJ0ZXN0"
    assert c.invoice == "lnsb100n1p0abc"


def test_parse_l402_fails_on_garbage():
    with pytest.raises(SystemExit):
        l402.parse_l402_challenge("Bearer token=abc123")


# ── Token cache tests ────────────────────────────────────────────


def test_cache_round_trip(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    url = "https://api.example.com/data"
    token = "LSAT mac123:preimage456"

    assert l402._load_cached_token(url) is None
    l402._save_token(url, token)
    assert l402._load_cached_token(url) == token


def test_cache_key_deterministic():
    assert l402._cache_key("https://a.com") == l402._cache_key("https://a.com")
    assert l402._cache_key("https://a.com") != l402._cache_key("https://b.com")


# ── Fetch flow tests (mocked HTTP) ──────────────────────────────


def test_fetch_non_402_passes_through():
    """A normal 200 response should be returned directly, no LN payment."""
    mock_response = httpx.Response(
        200,
        text='{"data": "hello"}',
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://example.com"),
    )
    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.request.return_value = mock_response

        result = l402.fetch("https://example.com")

    assert result.http_status == 200
    assert result.body == '{"data": "hello"}'
    assert result.payment_hash is None


def test_fetch_402_with_payment():
    """A 402 response should trigger invoice parsing, payment, and retry."""
    challenge_header = 'LSAT macaroon="testmac123", invoice="lntbs100n1ptest"'

    resp_402 = httpx.Response(
        402,
        text="Payment Required",
        headers={"www-authenticate": challenge_header},
        request=httpx.Request("GET", "https://api.example.com/paid"),
    )
    resp_200 = httpx.Response(
        200,
        text='{"result": "paid content"}',
        request=httpx.Request("GET", "https://api.example.com/paid"),
    )

    mock_pay_result = {
        "payment_id": "payid_abc",
        "payment_hash": "abc123",
        "preimage": "pre456",
        "amount_msat": 100_000,
        "amount_sats": 100,
        "fee_sats": 1,
    }

    with (
        patch("httpx.Client") as mock_client,
        patch("saturnzap.payments.pay_invoice", return_value=mock_pay_result),
    ):
        instance = mock_client.return_value.__enter__.return_value
        instance.request.side_effect = [resp_402, resp_200]

        result = l402.fetch("https://api.example.com/paid")

    assert result.http_status == 200
    assert result.payment_hash == "abc123"
    assert result.amount_sats == 100
    assert result.fee_sats == 1
    assert "paid content" in result.body


def test_fetch_402_authorization_header_includes_preimage():
    """The retry request should include the preimage in the LSAT header."""
    challenge_header = 'LSAT macaroon="mac_abc", invoice="lntbs100n1ptest"'

    resp_402 = httpx.Response(
        402,
        text="Payment Required",
        headers={"www-authenticate": challenge_header},
        request=httpx.Request("GET", "https://api.example.com/paid"),
    )
    resp_200 = httpx.Response(
        200,
        text='{"ok": true}',
        request=httpx.Request("GET", "https://api.example.com/paid"),
    )

    mock_pay_result = {
        "payment_id": "payid_xyz",
        "payment_hash": "hash_xyz",
        "preimage": "deadbeef01234567",
        "amount_msat": 100_000,
    }

    with (
        patch("httpx.Client") as mock_client,
        patch("saturnzap.payments.pay_invoice", return_value=mock_pay_result),
    ):
        instance = mock_client.return_value.__enter__.return_value
        instance.request.side_effect = [resp_402, resp_200]

        l402.fetch("https://api.example.com/paid")

    # The second call should have the LSAT token with preimage
    retry_call = instance.request.call_args_list[1]
    auth_header = retry_call.kwargs.get("headers", {}).get("Authorization", "")
    assert "mac_abc:deadbeef01234567" in auth_header


def test_fetch_402_no_www_authenticate():
    """A 402 without WWW-Authenticate header should error."""
    resp_402 = httpx.Response(
        402,
        text="Payment Required",
        headers={},
        request=httpx.Request("GET", "https://api.example.com"),
    )

    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.request.return_value = resp_402

        with pytest.raises(SystemExit):
            l402.fetch("https://api.example.com")


def test_fetch_spending_cap_exceeded():
    """If invoice amount exceeds max_sats, abort before paying."""
    challenge_header = 'LSAT macaroon="testmac", invoice="lntbs500n1ptest"'

    resp_402 = httpx.Response(
        402,
        text="Payment Required",
        headers={"www-authenticate": challenge_header},
        request=httpx.Request("GET", "https://api.example.com"),
    )

    # Mock Bolt11Invoice to return an amount above our cap
    with (
        patch("httpx.Client") as mock_client,
        patch("ldk_node.Bolt11Invoice") as mock_inv_cls,
    ):
        instance = mock_client.return_value.__enter__.return_value
        instance.request.return_value = resp_402

        mock_inv = mock_inv_cls.from_str.return_value
        mock_inv.amount_milli_satoshis.return_value = 500_000  # 500 sats

        with pytest.raises(SystemExit):
            l402.fetch("https://api.example.com", max_sats=100)


# ── CLI integration tests ───────────────────────────────────────


def test_fetch_help():
    from tests.conftest import strip_ansi

    result = runner.invoke(app, ["fetch", "--help"])
    assert result.exit_code == 0
    out = strip_ansi(result.output)
    assert "URL" in out or "url" in out
    assert "--max-sats" in out
    assert "--header" in out
    assert "--method" in out


def test_fetch_cli_normal_response():
    """Test the full sz fetch command with a mock 200 response."""
    mock_response = httpx.Response(
        200,
        text='{"data": "test"}',
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://example.com"),
    )

    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.request.return_value = mock_response

        result = runner.invoke(app, ["fetch", "https://example.com"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["status"] == "ok"
    assert data["http_status"] == 200
    assert data["body"] == {"data": "test"}


# ── Additional tests ─────────────────────────────────────────────


def test_cache_token_reuse():
    """A cached token should be used on the second fetch (skip payment)."""
    mock_resp_200 = httpx.Response(
        200,
        text='{"data": "cached"}',
        headers={"content-type": "application/json"},
        request=httpx.Request("GET", "https://api.cached.com"),
    )

    # Pre-seed the cache
    l402._save_token("https://api.cached.com", "LSAT mac:pre")

    with patch("httpx.Client") as mock_client:
        instance = mock_client.return_value.__enter__.return_value
        instance.request.return_value = mock_resp_200

        result = l402.fetch("https://api.cached.com")

    assert result.http_status == 200
    # Should have sent Authorization header with cached token
    call_kwargs = instance.request.call_args
    assert call_kwargs.kwargs.get("headers", {}).get("Authorization") == "LSAT mac:pre"


def test_stale_token_evicted(tmp_path, monkeypatch):
    """If a cached token gets a 402, it should be evicted and re-challenged."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    l402._save_token("https://api.stale.com", "LSAT old_mac:old_pre")

    challenge_header = 'LSAT macaroon="newmac", invoice="lntbs100n1pfresh"'
    resp_402 = httpx.Response(
        402, text="", headers={"www-authenticate": challenge_header},
        request=httpx.Request("GET", "https://api.stale.com"),
    )
    resp_200 = httpx.Response(
        200, text='{"ok": true}',
        request=httpx.Request("GET", "https://api.stale.com"),
    )

    mock_pay = {
        "payment_id": "payid_new",
        "payment_hash": "newhash", "preimage": "newpre",
        "amount_msat": 100_000, "amount_sats": 100, "fee_sats": 0,
    }

    with (
        patch("httpx.Client") as mock_client,
        patch("saturnzap.payments.pay_invoice", return_value=mock_pay),
    ):
        instance = mock_client.return_value.__enter__.return_value
        # First call (with stale token) -> 402,
        # second (without) -> 402, third (paid) -> 200
        instance.request.side_effect = [resp_402, resp_402, resp_200]

        result = l402.fetch("https://api.stale.com")

    assert result.http_status == 200
    assert result.payment_hash == "newhash"


def test_cache_key_length():
    """Cache key should be 32 characters (first 32 of SHA256 hex)."""
    key = l402._cache_key("https://example.com/anything")
    assert len(key) == 32
    assert all(c in "0123456789abcdef" for c in key)
