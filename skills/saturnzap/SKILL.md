---
name: saturnzap
description: "Non-custodial Lightning wallet for AI agents via `sz` CLI: send/receive sats, pay invoices, auto-pay HTTP 402 (L402), manage channels and liquidity. Use when: (1) paying for API access with Lightning, (2) creating or paying BOLT11 invoices, (3) checking wallet balance or channel health, (4) managing peers and channels. NOT for: on-chain-only Bitcoin transactions, custodial Lightning services, or mainnet (signet only during development)."
homepage: https://github.com/ShoneAnstey/SaturnZap
metadata:
  { "openclaw": { "emoji": "⚡", "os": ["linux"], "requires": { "bins": ["sz"], "env": ["SZ_PASSPHRASE"] }, "primaryEnv": "SZ_PASSPHRASE", "install": [{ "id": "uv", "kind": "uv", "package": "saturnzap", "bins": ["sz"], "label": "Install SaturnZap (uv)" }] } }
---

# SaturnZap Lightning Wallet

Non-custodial Lightning Network wallet for autonomous AI agents. All output is JSON by default — no `--json` flag needed. Parse stdout for success (`"status": "ok"`) and stderr for errors (`"status": "error"`).

See `{baseDir}/references/json-contracts.md` for full JSON output shapes.

## When to Use

✅ **USE this skill when:**

- Paying for API access via Lightning (L402 / HTTP 402 auto-pay)
- Creating BOLT11 invoices to receive payments
- Paying BOLT11 invoices or sending keysend payments
- Checking wallet balance (on-chain + Lightning)
- Opening, closing, or listing Lightning channels
- Connecting to or managing Lightning peers
- Monitoring channel liquidity health
- Requesting inbound liquidity from an LSP

## When NOT to Use

❌ **DON'T use this skill when:**

- On-chain-only Bitcoin transactions (use a Bitcoin wallet CLI)
- Custodial Lightning services (use hosted APIs like Strike, LNBits)
- Non-Lightning crypto payments (ETH, stablecoins, etc.)
- Mainnet Lightning — SaturnZap is signet-only during development (test sats, no real value)

## Setup

```bash
# Install (one-time)
uv tool install saturnzap

# Set passphrase (required — encrypts the seed on disk)
export SZ_PASSPHRASE="your-secure-passphrase"

# Initialize wallet (first time only — generates BIP39 seed, starts node)
sz init

# Verify node is running
sz status
```

Configure in `openclaw.json` to inject the passphrase automatically:

```json
{
  "skills": {
    "entries": {
      "saturnzap": {
        "enabled": true,
        "env": { "SZ_PASSPHRASE": "your-secure-passphrase" }
      }
    }
  }
}
```

## Node Management

```bash
# Initialize wallet (first time — writes seed, starts node)
sz init

# Start node (auto-starts from encrypted seed)
sz start

# Stop node
sz stop

# Check node status (pubkey, sync state)
sz status
```

The node auto-starts when needed. Most commands call `sz start` internally if the node isn't running.

## Wallet

```bash
# Get a new on-chain address (for receiving signet faucet deposits)
sz address

# Check balances (on-chain + lightning + per-channel breakdown)
sz balance
```

## Payments

```bash
# Create invoice to receive 1000 sats
sz invoice --amount-sats 1000 --memo "payment for data"

# Create variable-amount invoice (payer chooses amount)
sz invoice --amount-sats 0 --memo "tips welcome"

# Pay a BOLT11 invoice (with optional spending cap)
sz pay --invoice "lnbc..." --max-sats 5000

# Send spontaneous keysend payment
sz keysend --pubkey "03abc..." --amount-sats 500

# View payment history
sz transactions --limit 10
```

### Spending Caps

Always use `--max-sats` when paying invoices on behalf of a user to enforce a spending limit. If the invoice exceeds the cap, the payment is rejected with a `SPENDING_CAP_EXCEEDED` error.

## L402 (HTTP 402 Auto-Pay)

Fetch a URL and automatically pay the Lightning invoice if the server returns HTTP 402:

```bash
# Basic L402 fetch
sz fetch "https://api.example.com/premium-data"

# With spending cap (recommended for agent use)
sz fetch "https://api.example.com/data" --max-sats 100

# POST with headers and body
sz fetch "https://api.example.com/submit" \
  -X POST \
  -H "Content-Type: application/json" \
  -d '{"query": "analysis"}' \
  --max-sats 500

# Custom timeout
sz fetch "https://api.example.com/slow" --timeout 60
```

The response includes the HTTP status, body (parsed as JSON if possible), and payment details if a 402 was paid.

## Channels

```bash
# List all channels
sz channels list

# Open a channel to a specific peer
sz channels open --peer "03abc...@1.2.3.4:9735" --amount-sats 100000

# Open a channel via LQWD LSP (auto-selects nearest region)
sz channels open --lsp lqwd --amount-sats 100000

# Open a channel via LQWD in a specific region
sz channels open --lsp lqwd --region JP --amount-sats 200000

# Close a channel cooperatively
sz channels close --channel-id "abc123" --counterparty "03abc..."

# Force-close a channel
sz channels close --channel-id "abc123" --counterparty "03abc..." --force
```

## Peers

```bash
# List connected peers
sz peers list

# Connect to a peer
sz peers add "03abc...@1.2.3.4:9735"

# Disconnect a peer
sz peers remove "03abc..."
```

## Liquidity

```bash
# Channel health report (scores, labels, recommendations)
sz liquidity status

# Request inbound liquidity from LQWD (auto-selects nearest region)
sz liquidity request-inbound --amount-sats 100000

# Request inbound from a specific region
sz liquidity request-inbound --amount-sats 100000 --region CA
```

Health scores range 0–100. Labels: `healthy` (40+), `warning` (20–40), `critical` (0–20).

## Guardrails

- **Always use `--max-sats`** on `sz pay` and `sz fetch` to enforce spending caps. Never pay unbounded invoices autonomously.
- **Never expose the mnemonic** — the seed phrase from `sz init` must never appear in chat, logs, or tool output after initial display.
- **Check balance first** — run `sz balance` before large payments to confirm sufficient funds.
- **Parse JSON output** — all `sz` commands output JSON to stdout on success, stderr on error. Use the `status` field to branch logic.
- **Signet only** — current network is Bitcoin signet (test sats). No real monetary value. Do not promise users real payments.
- **Passphrase security** — `SZ_PASSPHRASE` encrypts the seed on disk. Keep it out of chat and logs.

## Workflow Templates

### Pay for API Access (L402)

```bash
# Check balance first
sz balance

# Fetch a paid endpoint with a spending cap
sz fetch "https://api.example.com/premium" --max-sats 100
```

### Receive a Payment

```bash
# Create an invoice
sz invoice --amount-sats 1000 --memo "service fee"

# Share the `invoice` field from the JSON output with the payer
# Then check payment arrived
sz transactions --limit 1
```

### Check Channel Health

```bash
# Overall health report with recommendations
sz liquidity status

# Detailed balance breakdown
sz balance
```

### Open a Channel and Send Payment

```bash
# Open a channel
sz channels open --lsp lqwd --amount-sats 100000

# Wait for on-chain confirmation (check channel list for is_channel_ready)
sz channels list

# Pay an invoice once the channel is ready
sz pay --invoice "lnbc..." --max-sats 5000
```

## Notes

- All output is JSON. Use `--pretty` or `SZ_PRETTY=1` for human-readable formatting.
- The node auto-starts from the encrypted seed when any command needs it. Explicit `sz start` is rarely needed.
- LQWD region codes: CA, US, SE, FR, GB, IE, IT, DE, BH, JP, AU, SG, HK, KR, ID, IN, BR, ZA.
- `sz fetch` caches L402 tokens — repeated requests to the same endpoint reuse the token without re-paying.
