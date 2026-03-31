"""L402 HTTP interceptor — detect 402, pay invoice, retry with token."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from saturnzap import output
from saturnzap.config import data_dir

# ── Token cache ──────────────────────────────────────────────────

def _cache_dir() -> Path:
    p = data_dir() / "l402_tokens"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _cache_key(url: str) -> str:
    """Deterministic filename for a URL (safe for filesystem)."""
    import hashlib
    return hashlib.sha256(url.encode()).hexdigest()[:32]


def _load_cached_token(url: str) -> str | None:
    """Return cached 'LSAT <macaroon>:<preimage>' string if available."""
    path = _cache_dir() / _cache_key(url)
    if path.exists():
        return path.read_text().strip()
    return None


def _save_token(url: str, token: str) -> None:
    """Persist an L402 token for a URL."""
    path = _cache_dir() / _cache_key(url)
    path.write_text(token)
    path.chmod(0o600)


# ── L402 parsing ─────────────────────────────────────────────────

@dataclass
class L402Challenge:
    """Parsed L402 / LSAT challenge from a WWW-Authenticate header."""
    macaroon: str
    invoice: str
    raw: str = ""


# Patterns for extracting macaroon and invoice from WWW-Authenticate
# Supports both "LSAT" and "L402" schemes.
_AUTH_RE = re.compile(
    r'(?:LSAT|L402)\s+'
    r'(?:macaroon\s*=\s*"?([^",\s]+)"?|([^,\s]+))'
    r'[,\s]+'
    r'(?:invoice\s*=\s*"?([^",\s]+)"?)',
    re.IGNORECASE,
)

# Simpler fallback: 'LSAT <macaroon>, invoice="<invoice>"'
_AUTH_SIMPLE_RE = re.compile(
    r'(?:LSAT|L402)\s+([A-Za-z0-9+/=]+)[,\s]+invoice\s*=\s*"?(ln[a-z0-9]+)"?',
    re.IGNORECASE,
)


def parse_l402_challenge(header: str) -> L402Challenge:
    """Extract macaroon and invoice from a WWW-Authenticate header.

    Supports formats:
        LSAT macaroon="<mac>", invoice="<inv>"
        L402 macaroon="<mac>", invoice="<inv>"
        LSAT <mac>, invoice="<inv>"
    """
    m = _AUTH_RE.search(header)
    if m:
        mac = m.group(1) or m.group(2)
        inv = m.group(3)
        return L402Challenge(macaroon=mac, invoice=inv, raw=header)

    m = _AUTH_SIMPLE_RE.search(header)
    if m:
        return L402Challenge(macaroon=m.group(1), invoice=m.group(2), raw=header)

    output.error(
        "L402_PARSE_FAILED",
        f"Could not parse L402 challenge from: {header}",
    )
    return L402Challenge(macaroon="", invoice="")  # unreachable


# ── Core fetch flow ──────────────────────────────────────────────

@dataclass
class FetchResult:
    """Result of an L402-aware fetch."""
    url: str
    http_status: int
    body: str
    payment_hash: str | None = None
    amount_sats: int | None = None
    fee_sats: int | None = None
    duration_ms: int | None = None
    headers: dict = field(default_factory=dict)


def fetch(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: str | None = None,
    max_sats: int | None = None,
    timeout: float = 30.0,
) -> FetchResult:
    """Make an HTTP request; if 402 is returned, pay and retry.

    Args:
        url: The URL to fetch.
        method: HTTP method (GET, POST, etc.).
        headers: Extra request headers.
        body: Request body for POST/PUT.
        max_sats: Maximum sats to pay. If the invoice exceeds this, abort.
        timeout: HTTP timeout in seconds.

    Returns:
        FetchResult with response data and optional payment info.
    """
    from saturnzap.node import _use_ipc

    if _use_ipc():
        from saturnzap.ipc import ipc_call

        result = ipc_call("l402_fetch", {
            "url": url, "method": method, "headers": headers,
            "body": body, "max_sats": max_sats, "timeout": timeout,
        })
        return FetchResult(**result)

    req_headers = dict(headers or {})

    # Check for a cached token first
    cached = _load_cached_token(url)
    if cached:
        req_headers["Authorization"] = cached

    t0 = time.monotonic()

    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.request(method, url, headers=req_headers, content=body)

        # If we used a cached token and still got 402, token is stale
        if resp.status_code == 402 and cached:
            req_headers.pop("Authorization", None)
            resp = client.request(method, url, headers=req_headers, content=body)

        if resp.status_code != 402:
            elapsed = int((time.monotonic() - t0) * 1000)
            return FetchResult(
                url=url,
                http_status=resp.status_code,
                body=resp.text,
                duration_ms=elapsed,
                headers=dict(resp.headers),
            )

        # ── 402 Payment Required ─────────────────────────────
        www_auth = resp.headers.get("www-authenticate", "")
        if not www_auth:
            output.error(
                "L402_NO_CHALLENGE",
                "Received HTTP 402 but no WWW-Authenticate header.",
            )

        challenge = parse_l402_challenge(www_auth)

        # Enforce spending cap
        if max_sats is not None:
            _check_invoice_amount(challenge.invoice, max_sats)

        # Pay the invoice
        from saturnzap import payments
        pay_result = payments.pay_invoice(challenge.invoice)

        # Build authorization header: LSAT <macaroon>:<preimage>
        preimage = pay_result.get("preimage", "")
        auth_token = f"LSAT {challenge.macaroon}:{preimage}"
        req_headers["Authorization"] = auth_token

        # Cache the token for future requests to the same URL
        _save_token(url, auth_token)

        # Retry the original request with the token
        resp2 = client.request(method, url, headers=req_headers, content=body)

        elapsed = int((time.monotonic() - t0) * 1000)
        return FetchResult(
            url=url,
            http_status=resp2.status_code,
            body=resp2.text,
            payment_hash=pay_result.get("payment_hash"),
            amount_sats=pay_result.get("amount_sats"),
            fee_sats=pay_result.get("fee_sats"),
            duration_ms=elapsed,
            headers=dict(resp2.headers),
        )


def _check_invoice_amount(invoice_str: str, max_sats: int) -> None:
    """Abort if the invoice amount exceeds the spending cap."""
    from ldk_node import Bolt11Invoice

    from saturnzap.node import _require_node

    inv = Bolt11Invoice.from_str(invoice_str)
    amount_msat = inv.amount_milli_satoshis()
    if amount_msat is not None:
        amount_sats = amount_msat // 1000
        if amount_sats > max_sats:
            output.error(
                "SPENDING_CAP_EXCEEDED",
                f"Invoice requires {amount_sats} sats but cap is {max_sats} sats.",
            )
        # Pre-flight: also check Lightning balance
        node = _require_node()
        bal = node.list_balances()
        available = bal.total_lightning_balance_sats
        if amount_sats > available:
            output.error(
                "INSUFFICIENT_FUNDS",
                f"L402 invoice requires {amount_sats} sats but Lightning "
                f"balance is {available} sats.",
            )
