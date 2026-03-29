# SaturnZap JSON Output Contracts

Every `sz` command writes JSON to stdout on success and stderr on error.
No `--json` flag is needed — JSON is the default output format.

## Envelope Format

### Success

```json
{ "status": "ok", ...fields }
```

### Error

```json
{ "status": "error", "code": "ERROR_CODE", "message": "Human-readable detail" }
```

Error codes: `ALREADY_INITIALIZED`, `CONNECTION_FAILED`, `INSUFFICIENT_FUNDS`,
`INVALID_PUBKEY`, `INVALID_ADDRESS`, `INVALID_INVOICE`, `INVALID_CHANNEL_ID`,
`INVALID_NETWORK`, `PAYMENT_FAILED`, `CHANNEL_CREATION_FAILED`,
`SPENDING_CAP_EXCEEDED`, `INVALID_PEER_ADDRESS`, `INVALID_ARGS`,
`INVALID_HEADER`, `LDK_ERROR`, `INTERNAL_ERROR`.

---

## Node Management

### `sz init`

```json
{
  "status": "ok",
  "mnemonic": "twelve word seed phrase here ...",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b1fe3cc2550d7437afe5df59e50",
  "seed_path": "/root/.config/saturnzap/seed.enc",
  "message": "Wallet initialized. WRITE DOWN YOUR MNEMONIC AND STORE IT SAFELY."
}
```

### `sz start`

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b1fe3cc2550d7437afe5df59e50",
  "message": "Node started."
}
```

### `sz stop`

```json
{
  "status": "ok",
  "message": "Node stopped."
}
```

### `sz status`

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b1fe3cc2550d7437afe5df59e50",
  "listening_addresses": ["0.0.0.0:9735"],
  "is_running": true
}
```

---

## Wallet

### `sz address`

```json
{
  "status": "ok",
  "address": "tb1qxxxx...",
  "network": "signet"
}
```

### `sz balance`

```json
{
  "status": "ok",
  "onchain_sats": 50000,
  "spendable_onchain_sats": 49000,
  "lightning_sats": 99000,
  "anchor_reserve_sats": 1000,
  "channels": [
    {
      "channel_id": "abc123...",
      "counterparty_node_id": "03992d76...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 99000000,
      "inbound_capacity_msat": 1000000,
      "is_channel_ready": true,
      "is_usable": true,
      "is_outbound": true,
      "is_announced": false,
      "confirmations": 6,
      "funding_txo": "e23d2889...:0"
    }
  ]
}
```

---

## Payments

### `sz invoice --amount-sats 1000 --memo "test"`

```json
{
  "status": "ok",
  "invoice": "lnbc1000n1pjxyz...",
  "amount_sats": 1000,
  "memo": "test",
  "expiry_secs": 3600,
  "payment_hash": "def456..."
}
```

### `sz invoice --amount-sats 0` (variable-amount)

```json
{
  "status": "ok",
  "invoice": "lnbc1pjxyz...",
  "amount_sats": null,
  "memo": "",
  "expiry_secs": 3600,
  "payment_hash": "def456..."
}
```

### `sz pay --invoice "lnbc..."`

```json
{
  "status": "ok",
  "payment_hash": "def456...",
  "amount_sats": 1000,
  "fee_sats": 1,
  "duration_ms": 342,
  "message": "Payment sent."
}
```

### `sz keysend --pubkey "03abc..." --amount-sats 500`

```json
{
  "status": "ok",
  "payment_hash": "abc789...",
  "amount_sats": 500,
  "duration_ms": 280,
  "message": "Keysend sent."
}
```

### `sz transactions --limit 5`

```json
{
  "status": "ok",
  "transactions": [
    {
      "payment_hash": "def456...",
      "direction": "outbound",
      "amount_sats": 1000,
      "fee_sats": 1,
      "status": "succeeded",
      "timestamp": 1711700000
    }
  ],
  "count": 1
}
```

---

## L402 (HTTP 402 Auto-Pay)

### `sz fetch "https://api.example.com/data" --max-sats 100`

Success (no 402):

```json
{
  "status": "ok",
  "url": "https://api.example.com/data",
  "http_status": 200,
  "duration_ms": 150,
  "body": { "result": "data here" }
}
```

Success (402 auto-paid):

```json
{
  "status": "ok",
  "url": "https://api.example.com/data",
  "http_status": 200,
  "payment_hash": "abc123...",
  "amount_sats": 50,
  "fee_sats": 0,
  "duration_ms": 1200,
  "body": { "result": "premium data" }
}
```

The `body` field is parsed as JSON when possible, otherwise a raw string.

---

## Peers

### `sz peers list`

```json
{
  "status": "ok",
  "peers": [
    {
      "node_id": "03992d76...",
      "address": "24.199.102.209:9735",
      "is_connected": true
    }
  ]
}
```

### `sz peers add "03abc...@1.2.3.4:9735"`

```json
{
  "status": "ok",
  "node_id": "03abc...",
  "address": "1.2.3.4:9735",
  "message": "Peer added."
}
```

### `sz peers remove "03abc..."`

```json
{
  "status": "ok",
  "node_id": "03abc...",
  "message": "Peer removed."
}
```

---

## Channels

### `sz channels list`

```json
{
  "status": "ok",
  "channels": [
    {
      "channel_id": "abc123...",
      "counterparty_node_id": "03992d76...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 99000000,
      "inbound_capacity_msat": 1000000,
      "is_channel_ready": true,
      "is_usable": true,
      "is_outbound": true,
      "is_announced": false,
      "confirmations": 6,
      "funding_txo": "e23d2889...:0"
    }
  ]
}
```

### `sz channels open --peer "03abc...@1.2.3.4:9735" --amount-sats 100000`

```json
{
  "status": "ok",
  "user_channel_id": 1,
  "counterparty": "03abc...",
  "amount_sats": 100000,
  "message": "Channel open initiated."
}
```

### `sz channels close --channel-id "abc123" --counterparty "03abc..."`

```json
{
  "status": "ok",
  "channel_id": "abc123",
  "message": "Cooperative close initiated."
}
```

### `sz channels close --channel-id "abc123" --counterparty "03abc..." --force`

```json
{
  "status": "ok",
  "channel_id": "abc123",
  "message": "Force-close initiated."
}
```

---

## Liquidity

### `sz liquidity status`

```json
{
  "status": "ok",
  "channel_count": 1,
  "total_capacity_sats": 100000,
  "total_outbound_msat": 99000000,
  "total_inbound_msat": 1000000,
  "average_health_score": 2,
  "channels": [
    {
      "channel_id": "abc123...",
      "counterparty_node_id": "03992d76...",
      "channel_value_sats": 100000,
      "outbound_capacity_msat": 99000000,
      "inbound_capacity_msat": 1000000,
      "health_score": 2,
      "health_label": "critical"
    }
  ],
  "recommendations": [
    "Channel abc123... has low inbound capacity (critical). Request inbound liquidity."
  ]
}
```

### `sz liquidity request-inbound --amount-sats 100000`

```json
{
  "status": "ok",
  "region": "CA",
  "node_id": "03abc...",
  "amount_sats": 100000,
  "message": "Inbound liquidity request initiated."
}
```
