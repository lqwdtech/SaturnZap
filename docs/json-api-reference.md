# JSON API Reference

Every `sz` command writes structured JSON to stdout. Errors go to stderr.
All responses include a `"status"` field: `"ok"` on success, `"error"` on failure.

---

## Envelope Format

### Success

```json
{
  "status": "ok",
  "network": "bitcoin",
  ...fields
}
```

Every success response includes a `"network"` field indicating the active Bitcoin
network (`"bitcoin"`, `"signet"`, or `"testnet"`).

### Error

```json
{
  "status": "error",
  "code": "ERROR_CODE",
  "message": "Human-readable description."
}
```

Errors are written to **stderr** and the process exits with a non-zero code.

---

## Node Commands

### `sz init`

```json
{
  "status": "ok",
  "network": "bitcoin",
  "mnemonic": "abandon ability able about above absent absorb ... (24 words)",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b1fe3cc2550d7437afe5df59e50",
  "seed_path": "/home/user/.local/share/saturnzap/seed.enc",
  "message": "Wallet initialized. WRITE DOWN YOUR MNEMONIC AND STORE IT SAFELY."
}
```

### `sz start`

```json
{
  "status": "ok",
  "network": "bitcoin",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b1fe3cc2550d7437afe5df59e50",
  "firewall": "opened",
  "message": "Node started."
}
```

The `firewall` field is present when running as a daemon (the default). Values:
`"opened"`, `"already_open"`, `"ufw_inactive"`, `"ufw_not_found"`, `"not_linux"`,
`"permission_denied"`, `"error"`. Omitted when `--foreground` is used.

`sz start` blocks as a foreground daemon until SIGTERM/SIGINT by default.
Pass `--foreground` for the legacy "print and exit" behaviour.

### `sz stop`

```json
{
  "status": "ok",
  "network": "bitcoin",
  "message": "Node stopped."
}
```

### `sz status`

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b...",
  "is_running": true,
  "network": "bitcoin",
  "block_height": 297000,
  "block_hash": "0000014b62b53d2550c310208af9d792ab7a4a...",
  "latest_wallet_sync": 1743260000,
  "latest_lightning_sync": 1743260000
}
```

### `sz connect-info`

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b...",
  "host": "203.0.113.10",
  "port": 9735,
  "uri": "0234b0c302e8c201e0ffd31580bf9106b625505b...@203.0.113.10:9735",
  "network": "bitcoin"
}
```

With `--check` flag:

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b...",
  "host": "203.0.113.10",
  "port": 9735,
  "uri": "0234b0c302e8c201e0ffd31580bf9106b625505b...@203.0.113.10:9735",
  "network": "bitcoin",
  "reachable": true
}
```

The `uri` field is the full connection string another wallet needs to connect or open
a channel to your node. Share this with peers or LSPs. The `host` field is auto-detected
via an external IP service; it is `null` if detection fails.

The `reachable` field is only present when `--check` is passed. It will be `true`,
`false`, or `null` (if the external check service is unavailable).

---

## Wallet Commands

### `sz address`

```json
{
  "status": "ok",
  "address": "bc1qxyz...",
  "network": "bitcoin"
}
```

### `sz balance`

```json
{
  "status": "ok",
  "onchain_sats": 150000,
  "spendable_onchain_sats": 149800,
  "lightning_sats": 45000,
  "anchor_reserve_sats": 0,
  "channels": [
    {
      "channel_id": "abc123def456...",
      "counterparty_node_id": "03992d76a7ea...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 45000000,
      "inbound_capacity_msat": 54000000,
      "is_channel_ready": true,
      "is_usable": true,
      "is_outbound": true,
      "is_announced": false,
      "confirmations": 6,
      "funding_txo": "e23d2889bb8c9581..."
    }
  ],
  "warnings": ["On-chain funds available but no Lightning channels. Use 'sz channels open --lsp lqwd' to start sending payments."]
}
```

The `warnings` field is an optional array. It is present only when there are
actionable issues — for example, no Lightning channels when on-chain funds exist,
or all channels critically low. Omitted when everything is healthy.

### `sz transactions --limit 20`

```json
{
  "status": "ok",
  "transactions": [
    {
      "payment_id": "pay_abc123...",
      "kind": "bolt11",
      "direction": "outbound",
      "amount_sats": 1000,
      "fee_sats": 1,
      "status": "succeeded",
      "timestamp": 1743260000
    }
  ],
  "count": 1
}
```

**Payment kinds:** `bolt11`, `bolt11_jit`, `spontaneous`, `onchain`

**Directions:** `inbound`, `outbound`

**Statuses:** `pending`, `succeeded`, `failed`

---

## Peer Commands

### `sz peers list`

```json
{
  "status": "ok",
  "peers": [
    {
      "node_id": "03992d76a7ea4e17...",
      "address": "198.51.100.10:9735",
      "is_connected": true,
      "is_persisted": true
    }
  ]
}
```

### `sz peers add <pubkey>@<host>:<port>`

```json
{
  "status": "ok",
  "node_id": "03992d76a7ea4e17...",
  "address": "198.51.100.10:9735",
  "message": "Peer added."
}
```

### `sz peers remove <pubkey>`

```json
{
  "status": "ok",
  "node_id": "03992d76a7ea4e17...",
  "message": "Peer removed."
}
```

---

## Channel Commands

### `sz channels list`

```json
{
  "status": "ok",
  "channels": [
    {
      "channel_id": "abc123def456...",
      "counterparty_node_id": "03992d76a7ea...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 45000000,
      "inbound_capacity_msat": 54000000,
      "is_channel_ready": true,
      "is_usable": true,
      "is_outbound": true,
      "is_announced": false,
      "confirmations": 6,
      "funding_txo": "e23d2889bb8c9581..."
    }
  ]
}
```

### `sz channels open`

```json
{
  "status": "ok",
  "user_channel_id": "ucid_abc123...",
  "counterparty": "03992d76a7ea...",
  "amount_sats": 100000,
  "message": "Channel open initiated."
}
```

### `sz channels close`

```json
{
  "status": "ok",
  "channel_id": "abc123def456...",
  "message": "Cooperative close initiated."
}
```

Force close:

```json
{
  "status": "ok",
  "channel_id": "abc123def456...",
  "message": "Force-close initiated."
}
```

---

## Payment Commands

### `sz invoice --amount-sats 1000 --memo "for data"`

```json
{
  "status": "ok",
  "invoice": "lnbc10u1p...",
  "amount_sats": 1000,
  "payment_hash": "abc123...",
  "expiry_secs": 3600
}
```

Variable-amount invoice (`--amount-sats 0`):

```json
{
  "status": "ok",
  "invoice": "lnbc1p...",
  "amount_sats": null,
  "payment_hash": "def456...",
  "expiry_secs": 3600
}
```

### `sz pay --invoice lnbc1...`

```json
{
  "status": "ok",
  "payment_id": "pay_abc123...",
  "payment_hash": "abc123...",
  "amount_msat": 1000000,
  "preimage": "deadbeef01234567...",
  "message": "Payment sent.",
  "warnings": ["Low outbound (15%) on channel with 03992d76a7ea… — consider opening a new channel or receiving payments."]
}
```

The `preimage` field is the proof-of-payment. It is `null` if LDK has not yet
resolved the preimage (rare — typically available immediately after payment).

The `warnings` field is an optional array, present only when outbound channel
capacity drops below the configured threshold (default: 20%) after the payment.

### `sz keysend --pubkey <pubkey> --amount-sats 100`

```json
{
  "status": "ok",
  "payment_id": "pay_def456...",
  "pubkey": "03992d76a7ea...",
  "amount_sats": 100,
  "message": "Keysend sent.",
  "warnings": ["Low outbound (15%) on channel with 03992d76a7ea… — consider opening a new channel or receiving payments."]
}
```

The `warnings` field behavior is the same as `sz pay` — present only when
channel capacity is low after the payment.

---

## L402 Commands

### `sz fetch <url>`

No payment required (non-402 response):

```json
{
  "status": "ok",
  "url": "https://api.example.com/data",
  "http_status": 200,
  "duration_ms": 150,
  "body": {"key": "value"}
}
```

With L402 payment (402 → pay → retry):

```json
{
  "status": "ok",
  "url": "https://api.example.com/paid-data",
  "http_status": 200,
  "payment_hash": "ghi789...",
  "amount_sats": 10,
  "fee_sats": 1,
  "duration_ms": 850,
  "body": {"premium": "content"},
  "warnings": ["Low outbound (15%) on channel with 03992d76a7ea… — consider opening a new channel or receiving payments."]
}
```

The `body` field is parsed as JSON if possible, otherwise returned as a raw string.

The `warnings` field propagates from the underlying payment — present only when
channel capacity is low after the L402 invoice payment.

---

## Liquidity Commands

### `sz liquidity status`

```json
{
  "status": "ok",
  "channels": [
    {
      "channel_id": "abc123...",
      "counterparty_node_id": "03992d76a7ea...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 45000000,
      "inbound_capacity_msat": 54000000,
      "is_usable": true,
      "health_score": 90,
      "health_label": "healthy"
    }
  ],
  "total_channels": 1,
  "usable_channels": 1,
  "onchain_sats": 150000,
  "lightning_sats": 45000,
  "recommendations": []
}
```

**Health scores:** 0–100 (peaks at 50% outbound balance).

**Health labels:** `healthy` (≥40), `warning` (≥20), `critical` (<20).

### `sz liquidity request-inbound --amount-sats 500000`

```json
{
  "status": "ok",
  "user_channel_id": "ucid_xyz...",
  "lqwd_node": "LQWD-Canada",
  "lqwd_region": "CA",
  "channel_capacity_sats": 505000,
  "inbound_sats": 500000,
  "fee_sats": 5000,
  "message": "Inbound liquidity request sent to LQWD-Canada. ..."
}
```

---

## Warnings

Some responses include an optional `"warnings"` array with actionable messages.
Warnings are **omitted** (not an empty array) when everything is healthy. This
ensures backward compatibility — existing agents that don't check for `"warnings"`
are unaffected.

### When warnings appear

| Command | Trigger |
|---|---|
| `sz balance` | No channels but has on-chain funds; no channels and no funds; all channels critically low |
| `sz pay` | Outbound capacity below threshold after payment |
| `sz keysend` | Outbound capacity below threshold after payment |
| `sz fetch` | Propagated from the underlying L402 invoice payment |

### Thresholds

The outbound capacity threshold defaults to **20%** and is configurable in
`config.toml`:

```toml
[liquidity]
outbound_threshold_percent = 20
```

### Agent handling

Check for the `"warnings"` key after each payment or balance call:

```python
result = json.loads(subprocess.run(["sz", "pay", ...], capture_output=True).stdout)
if "warnings" in result:
    for w in result["warnings"]:
        # Decide: open a channel, request inbound, or log for review
        print(w)
```

---

## Error Codes

| Code | Description |
|---|---|
| `ALREADY_INITIALIZED` | Wallet already initialized — seed exists |
| `NO_SEED` | No seed found — run `sz init` first |
| `BAD_PASSPHRASE` | Incorrect passphrase |
| `CONNECTION_FAILED` | Peer connection failed |
| `INSUFFICIENT_FUNDS` | Not enough funds for the operation |
| `INVALID_PUBKEY` | Invalid public key format |
| `INVALID_ADDRESS` | Invalid Bitcoin address |
| `INVALID_INVOICE` | Invalid BOLT11 invoice |
| `INVALID_CHANNEL_ID` | Channel ID not found |
| `INVALID_NETWORK` | Unknown network name |
| `PAYMENT_FAILED` | Lightning payment failed |
| `CHANNEL_CREATION_FAILED` | Channel open failed |
| `CHANNEL_REJECTED` | Peer rejected the channel (e.g. below minimum size) |
| `EXCEEDS_MAX_SATS` | Invoice amount exceeds spending cap |
| `L402_PARSE_FAILED` | Could not parse L402/LSAT challenge |
| `L402_NO_CHALLENGE` | HTTP 402 but no WWW-Authenticate header |
| `UNKNOWN_LSP` | Unknown LSP name (only `lqwd` supported) |
| `UNKNOWN_REGION` | LQWD region code not found |
| `INVALID_ARGS` | Invalid command arguments |
| `INVALID_PEER_ADDRESS` | Peer address not in `<pubkey>@<host>:<port>` format |
| `INVALID_HEADER` | HTTP header not in `key: value` format |
| `LDK_ERROR` | Unclassified LDK node error |
| `INTERNAL_ERROR` | Unexpected internal error |

---

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error (see error JSON for details) |
