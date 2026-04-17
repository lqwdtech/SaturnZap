"""Lightning payments — invoice, pay, keysend, transaction history."""

from __future__ import annotations

from ldk_node import Bolt11Invoice

from saturnzap.node import _require_node, _use_ipc

DEFAULT_INVOICE_EXPIRY_SECS = 3600  # 1 hour

# Maximum attempts to look up the preimage after a successful send.
_PREIMAGE_POLL_ATTEMPTS = 10
_PREIMAGE_POLL_INTERVAL = 0.5  # seconds


def _extract_preimage(node: object, payment_id: object) -> str | None:
    """Look up a completed payment and return its preimage hex string.

    ``bolt11_payment().send()`` is synchronous — the preimage should be
    available immediately.  We poll briefly as a safety net.
    """
    import time

    pid_str = str(payment_id)
    for _ in range(_PREIMAGE_POLL_ATTEMPTS):
        for p in node.list_payments():  # type: ignore[union-attr]
            if str(p.id) != pid_str:
                continue
            if hasattr(p.kind, "preimage") and p.kind.preimage is not None:
                return str(p.kind.preimage)
        time.sleep(_PREIMAGE_POLL_INTERVAL)
    return None


def _ipc(method: str, **params: object) -> object:
    from saturnzap.ipc import ipc_call

    return ipc_call(method, params if params else None)


def create_invoice(
    amount_sats: int,
    memo: str = "",
    expiry_secs: int = DEFAULT_INVOICE_EXPIRY_SECS,
) -> dict:
    """Create a BOLT11 invoice for *amount_sats*."""
    from saturnzap import output

    if amount_sats < 0:
        output.error("INVALID_ARGS", "amount_sats must be >= 0 (0 = variable amount).")
    if expiry_secs <= 0:
        output.error("INVALID_ARGS", "expiry_secs must be positive.")
    if _use_ipc():
        return _ipc(  # type: ignore[return-value]
            "create_invoice",
            amount_sats=amount_sats, memo=memo, expiry_secs=expiry_secs,
        )
    from ldk_node import Bolt11InvoiceDescription

    node = _require_node()
    amount_msat = amount_sats * 1000
    description = Bolt11InvoiceDescription.DIRECT(memo or "SaturnZap invoice")
    invoice = node.bolt11_payment().receive(amount_msat, description, expiry_secs)
    return {
        "invoice": str(invoice),
        "amount_sats": amount_sats,
        "payment_hash": invoice.payment_hash(),
        "expiry_secs": expiry_secs,
    }


def create_variable_invoice(
    memo: str = "",
    expiry_secs: int = DEFAULT_INVOICE_EXPIRY_SECS,
) -> dict:
    """Create a BOLT11 invoice with no fixed amount (payer chooses)."""
    if _use_ipc():
        return _ipc("create_variable_invoice", memo=memo, expiry_secs=expiry_secs)  # type: ignore[return-value]
    from ldk_node import Bolt11InvoiceDescription

    node = _require_node()
    description = Bolt11InvoiceDescription.DIRECT(memo or "SaturnZap invoice")
    invoice = node.bolt11_payment().receive_variable_amount(description, expiry_secs)
    return {
        "invoice": str(invoice),
        "amount_sats": None,
        "payment_hash": invoice.payment_hash(),
        "expiry_secs": expiry_secs,
    }


def pay_invoice(invoice_str: str, max_sats: int | None = None) -> dict:
    """Pay a BOLT11 invoice. Optionally enforce a spending cap."""
    if _use_ipc():
        return _ipc("pay_invoice", invoice_str=invoice_str, max_sats=max_sats)  # type: ignore[return-value]
    from saturnzap import output

    node = _require_node()
    invoice = Bolt11Invoice.from_str(invoice_str)

    invoice_amount_msat = invoice.amount_milli_satoshis()

    if (
        invoice_amount_msat is not None
        and max_sats is not None
        and invoice_amount_msat > max_sats * 1000
    ):
            output.error(
                "EXCEEDS_MAX_SATS",
                f"Invoice amount ({invoice_amount_msat // 1000} sats) "
                f"exceeds spending cap ({max_sats} sats).",
            )

    # Pre-flight balance check
    if invoice_amount_msat is not None:
        bal = node.list_balances()
        available = bal.total_lightning_balance_sats
        needed = invoice_amount_msat // 1000
        if needed > available:
            output.error(
                "INSUFFICIENT_FUNDS",
                f"Invoice requires {needed} sats but Lightning balance "
                f"is {available} sats.",
            )

    payment_id = node.bolt11_payment().send(invoice, None)
    preimage = _extract_preimage(node, payment_id)
    result = {
        "payment_id": str(payment_id),
        "payment_hash": invoice.payment_hash(),
        "amount_msat": invoice_amount_msat,
        "preimage": preimage,
    }

    # Post-payment capacity warnings
    from saturnzap import liquidity
    from saturnzap.node import _channel_to_dict

    channels = [_channel_to_dict(c) for c in node.list_channels()]
    warnings = liquidity.post_payment_warnings(channels)
    if warnings:
        result["warnings"] = warnings

    return result


def keysend(pubkey: str, amount_sats: int) -> dict:
    """Send a spontaneous (keysend) payment to *pubkey*."""
    from saturnzap import output

    if amount_sats <= 0:
        output.error("INVALID_ARGS", "amount_sats must be positive.")
    if _use_ipc():
        return _ipc("keysend", pubkey=pubkey, amount_sats=amount_sats)  # type: ignore[return-value]

    node = _require_node()

    # Pre-flight balance check
    bal = node.list_balances()
    available = bal.total_lightning_balance_sats
    if amount_sats > available:
        output.error(
            "INSUFFICIENT_FUNDS",
            f"Keysend requires {amount_sats} sats but Lightning balance "
            f"is {available} sats.",
        )

    amount_msat = amount_sats * 1000
    payment_id = node.spontaneous_payment().send(amount_msat, pubkey, None)
    result = {
        "payment_id": str(payment_id),
        "pubkey": pubkey,
        "amount_sats": amount_sats,
    }

    # Post-payment capacity warnings
    from saturnzap import liquidity
    from saturnzap.node import _channel_to_dict

    channels = [_channel_to_dict(c) for c in node.list_channels()]
    warnings = liquidity.post_payment_warnings(channels)
    if warnings:
        result["warnings"] = warnings

    return result


def list_transactions(limit: int = 20) -> list[dict]:
    """Return recent payment history."""
    if _use_ipc():
        return _ipc("list_transactions", limit=limit)  # type: ignore[return-value]
    node = _require_node()
    payments = node.list_payments()

    # Sort by timestamp descending (most recent first)
    payments.sort(key=lambda p: p.latest_update_timestamp, reverse=True)

    result = []
    for p in payments[:limit]:
        result.append({
            "payment_id": str(p.id),
            "kind": _payment_kind_str(p.kind),
            "direction": _payment_direction_str(p.direction),
            "amount_sats": (
                p.amount_msat // 1000 if p.amount_msat is not None else None
            ),
            "fee_sats": (
                p.fee_paid_msat // 1000
                if p.fee_paid_msat is not None
                else None
            ),
            "status": _payment_status_str(p.status),
            "timestamp": p.latest_update_timestamp,
        })
    return result


def _payment_kind_str(kind) -> str:
    """Convert PaymentKind enum to a string."""
    if kind.is_bolt11():
        return "bolt11"
    if kind.is_bolt11_jit():
        return "bolt11_jit"
    if kind.is_spontaneous():
        return "spontaneous"
    if kind.is_onchain():
        return "onchain"
    if kind.is_bolt12_offer():
        return "bolt12_offer"
    if kind.is_bolt12_refund():
        return "bolt12_refund"
    return "unknown"


def _payment_direction_str(direction) -> str:
    """Convert PaymentDirection enum to a string."""
    s = str(direction)
    if "INBOUND" in s:
        return "inbound"
    return "outbound"


def _payment_status_str(status) -> str:
    """Convert PaymentStatus enum to a string."""
    s = str(status)
    if "SUCCEEDED" in s:
        return "succeeded"
    if "PENDING" in s:
        return "pending"
    if "FAILED" in s:
        return "failed"
    return "unknown"


def wait_for_payment(
    payment_hash: str,
    timeout: int = 3600,
    poll_interval: int = 3,
) -> dict:
    """Poll until a payment matching *payment_hash* is received or timeout.

    Returns dict with 'paid': True/False and timing info.
    """
    if _use_ipc():
        return _ipc(  # type: ignore[return-value]
            "wait_for_payment",
            payment_hash=payment_hash, timeout=timeout, poll_interval=poll_interval,
        )
    import time

    node = _require_node()
    deadline = time.monotonic() + timeout

    while time.monotonic() < deadline:
        for p in node.list_payments():
            if (
                p.payment_hash == payment_hash
                and "INBOUND" in str(p.direction)
                and "SUCCEEDED" in str(p.status)
            ):
                return {
                    "paid": True,
                    "received_sats": p.amount_msat // 1000 if p.amount_msat else None,
                    "waited_seconds": int(timeout - (deadline - time.monotonic())),
                }
        time.sleep(poll_interval)

    return {
        "paid": False,
        "waited_seconds": timeout,
        "message": f"Invoice not paid within {timeout}s.",
    }
