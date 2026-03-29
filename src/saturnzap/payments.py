"""Lightning payments — invoice, pay, keysend, transaction history."""

from __future__ import annotations

from ldk_node import Bolt11Invoice, Bolt11InvoiceDescription

from saturnzap.node import _require_node

DEFAULT_INVOICE_EXPIRY_SECS = 3600  # 1 hour


def create_invoice(
    amount_sats: int,
    memo: str = "",
    expiry_secs: int = DEFAULT_INVOICE_EXPIRY_SECS,
) -> dict:
    """Create a BOLT11 invoice for *amount_sats*."""
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

    payment_id = node.bolt11_payment().send(invoice, None)
    return {
        "payment_id": str(payment_id),
        "payment_hash": invoice.payment_hash(),
        "amount_msat": invoice_amount_msat,
    }


def keysend(pubkey: str, amount_sats: int) -> dict:
    """Send a spontaneous (keysend) payment to *pubkey*."""
    node = _require_node()
    amount_msat = amount_sats * 1000
    payment_id = node.spontaneous_payment().send(amount_msat, pubkey, None)
    return {
        "payment_id": str(payment_id),
        "pubkey": pubkey,
        "amount_sats": amount_sats,
    }


def list_transactions(limit: int = 20) -> list[dict]:
    """Return recent payment history."""
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
