# Agent Guide — SaturnZap

A deep reference for AI agents integrating SaturnZap (`sz`) as their Lightning wallet. This guide covers decision criteria, common workflows, error recovery, and anti-patterns.

For quick command reference, see `skills/saturnzap/SKILL.md`. For JSON output shapes, see `docs/json-api-reference.md`.

---

## Would an Agent Choose This Wallet?

**Yes, if the agent needs:**

- Non-custodial Lightning payments (keys on disk, no third-party custodian)
- JSON-first output (every command returns structured JSON — no parsing prose)
- MCP native integration (25 tools exposed via Model Context Protocol)
- Pre-flight balance checks (payments fail with clear errors before attempting)
- Spending caps (enforce `--max-sats` on every outbound payment)
- L402 auto-pay (HTTP 402 detection, automatic invoice payment, token caching)
- Multi-network support (mainnet default, signet for development)
- Mainnet safety prompts (confirmation before spending real bitcoin)

**No, if the agent needs:**

- Custodial simplicity (SaturnZap requires seed management)
- Instant setup with no node sync (first start requires Neutrino/Esplora sync)
- Multi-currency support (Lightning/BTC only)

---

## First-Run Walkthrough

### Option A: CLI (scripts, cron, SSH)

```bash
export SZ_PASSPHRASE="agent-passphrase-here"

# 1. One-command setup (idempotent — safe to re-run)
sz setup --auto

# 2. Keep the node alive across reboots (recommended)
sz service install

# 3. Fund the wallet (send bitcoin to this address)
sz address

# 4. Open a channel when funded
sz channels open --lsp lqwd --amount-sats 100000

# 5. Channels from the LQWD fleet are 0-conf on mainnet (trusted peers),
#    so `is_usable: true` usually appears in seconds. For other peers, poll
#    `sz channels list` until `is_usable: true`.

# 6. Ready to pay
sz pay --invoice "lnbc..." --max-sats 5000
```

### Option B: MCP (Claude Desktop, Cursor, VS Code)

Configure `sz mcp` in your MCP client (see `docs/mcp-server.md`). Then call tools:

1. `setup_wallet()` — idempotent first-run
2. `get_onchain_address()` — fund this address
3. `open_channel(node_id, address, amount_sats)` — open to LQWD or custom peer
4. `get_status()` — verify sync and channel count
5. `pay_invoice(invoice, max_sats)` — pay with spending cap

---

## Free Mainnet Channel via LQWDClaw

If you don't have on-chain bitcoin to fund a channel, **LQWDClaw** (operated by LQWD
Technologies) gives every registered agent a free 20,000-sat mainnet channel,
operator-funded. ~1,000 sats are pushed to your side as immediate spendable balance,
the remainder is inbound liquidity. One grant per agent. No credit card, no KYC.

This is the recommended onboarding path for an agent that wants to make L402
payments on mainnet without funding a wallet first.

### When to use this path

- You need a working mainnet Lightning channel and have no on-chain funds.
- You only need to make small L402 payments (the channel push is ~1k sats spendable —
  enough for many L402 calls but not large transfers).
- You don't mind your node being publicly announced. SaturnZap's reachability
  auto-gate announces channels when the node is reachable from the internet.

### When NOT to use this path

- You need >1k sats of immediate outbound (use `sz channels open --lsp lqwd
  --amount-sats 100000` with on-chain funds instead).
- You're on signet or testnet — LQWDClaw is mainnet only.
- Your node isn't publicly reachable — the faucet only opens *announced* channels,
  which require reachability.

### The flow — five steps, all mainnet

```bash
# 1. Initialize SaturnZap with the LQWDClaw preset.
#    Sets a readable node alias and trusts LQWD's LND pubkey.
#    Use sz init, NOT sz setup --auto — the latter peers with a different
#    LQWD node (LSPS2 JIT) which is a separate onboarding flow.
export SZ_PASSPHRASE="your-passphrase"
sz init --for-lqwd-faucet \
  --backup-to ~/.saturnzap-mnemonic --no-mnemonic-stdout

# 2. Persist the node so it stays reachable.
sz service install

# 3. Get your node's connection URI and verify it's publicly reachable.
sz connect-info --check
# Look for "reachable": true in the JSON response. If false, open port 9735
# on your cloud firewall before continuing.

# 4. Peer-connect to LQWD BEFORE registering. Skipping this step risks
#    counting toward the 3-failure ban if LQWD's ConnectPeer call fails.
LQWD_URI=$(curl -s https://api.lqwdclaw.bot/v1/discovery \
  | jq -r .data.lqwd_node.uri)
sz peers add "$LQWD_URI"

# 5. (Optional, free) Pre-flight reachability check from LQWD's side.
#    No rate-limit cost. Confirms LQWD can dial you back before you
#    consume a registration slot.
PUBKEY=$(sz connect-info | jq -r .pubkey)
NODE_URI=$(sz connect-info | jq -r .uri)
curl -s -X POST https://api.lqwdclaw.bot/v1/internal/accounts/reachability-check \
  -H "Content-Type: application/json" \
  -d "{\"pubkey\":\"$PUBKEY\",\"node_uri\":\"$NODE_URI\"}"
# Expect "reachable": true. If false, fix the underlying issue and re-run.

# 6. Register. One POST, returns an api_key (prefix lqwd_) and a status URL.
curl -s -X POST https://api.lqwdclaw.bot/v1/internal/accounts/register \
  -H "Content-Type: application/json" \
  -d "{
    \"name\": \"my-agent-$(date +%s)\",
    \"pubkey\": \"$PUBKEY\",
    \"node_uri\": \"$NODE_URI\"
  }"
# Save the api_key — it cannot be retrieved later, only rotated.
# Channel opens asynchronously; expect 1–6 blocks for confirmation.

# 7. Poll channel status. Channel-faucet channels from LQWD are 0-conf on
#    mainnet (LQWD is a trusted peer by default), so is_usable usually
#    flips true within seconds of the registration response.
sz channels list
```

### MCP alternative

LQWDClaw also exposes an MCP server at `https://api.lqwdclaw.bot/v1/mcp`. After
`sz init --for-lqwd-faucet`, an MCP-capable agent can call `lqwd_register` and
`lqwd_check_channel_status` over MCP instead of curl, using the Bearer api_key for
authenticated calls. See [LQWDClaw `/for-agents`](https://lqwdclaw.bot/for-agents)
for the full MCP tool list.

### Failure modes worth knowing

| Symptom | Cause | Recovery |
|---|---|---|
| `Channel request rejected` / "Node alias is not configured" | The preset sets an alias automatically; if missing, set one with `sz config set node.alias <name>` and restart | `POST /v1/internal/channel/retry` with Bearer api_key |
| `reachable: false` from pre-flight | Firewall, wrong port, or NAT | Open port 9735 on cloud firewall, re-run `sz connect-info --check`, retry |
| Pubkey banned (3 failures) | Repeated `ConnectPeer` failures during registration | Fix reachability, then ask an LQWD operator to clear the ban |
| Want to retry a failed open | Latest grant in `status: failed` | `POST /v1/internal/channel/retry` — preserves api_key, doesn't burn /register rate limit |

### What you get and don't get

| You get | You don't get |
|---|---|
| 20k-sat announced channel to LQWD's hub | A routing tier (channel is too small to forward profitably) |
| ~1,000 sats of immediate spendable outbound | Multiple grants (one per agent) |
| One hop to the entire Lightning Network via LQWD | A guarantee — channels can fail to open for reachability reasons |
| 0-conf usability (LQWD is a trusted peer on mainnet) | Tier upgrades on demand (operator-granted only in v1) |

### Limits

- **3 registrations per IP per hour** (rate limit, not per-pubkey)
- **3 channel-open failures per pubkey** triggers an auto-ban (use the pre-flight
  check to avoid this)
- **One grant per agent** — additional channels require on-chain funds and
  `sz channels open`

---

## Common Workflows

### Pay for API Access (L402)

```bash
sz balance                                          # Check funds
sz fetch "https://api.example.com/data" --max-sats 100  # Auto-pay 402
```

The `fetch` command:
1. Sends the HTTP request
2. If 402 returned, parses the `WWW-Authenticate` header
3. Pays the Lightning invoice (enforcing `--max-sats`)
4. Retries with the paid token
5. Caches the token for future requests to the same URL

### Receive a Payment

```bash
# Create invoice and block until paid (best for agents)
sz invoice --amount-sats 1000 --memo "data analysis fee" --wait
```

The `--wait` flag blocks until the invoice is paid or expires. Parse the JSON output for `"paid": true`.

### Diagnose a Problem

```bash
sz status               # Is node synced? How many peers/channels?
sz balance              # Enough funds?
sz liquidity status     # Channel health scores and recommendations
sz channels list        # Individual channel states
```

### Backup Before Risky Operations

```bash
sz backup --output /tmp/wallet-backup.json
# ... do risky thing ...
# If something goes wrong:
sz restore --input /tmp/wallet-backup.json
```

---

## Error Recovery Tree

All errors are JSON on stderr with `"status": "error"` and a `"code"` field.

```
Payment failed?
├── code: INSUFFICIENT_FUNDS
│   └── Check balance → Fund wallet or close unneeded channels
├── code: EXCEEDS_MAX_SATS
│   └── Increase --max-sats or negotiate a smaller invoice
├── code: SPENDING_CAP_EXCEEDED (L402)
│   └── Same as above — the L402 invoice exceeds your cap
├── code: INVALID_INVOICE
│   └── The invoice string is malformed — request a new one
├── code: NO_SEED
│   └── Run `sz init` or `sz setup --auto` first
└── code: (LDK error)
    └── Check `sz status` — is the node synced? Are peers connected?

Channel issues?
├── code: CHANNEL_REJECTED
│   └── Peer rejected the channel — common cause: amount below peer's minimum (e.g. LQWD requires ≥2M sats)
├── code: CHANNEL_WAIT_TIMEOUT
│   └── Channel peer may be offline — check `sz peers list`
├── Health score < 20 (critical)
│   └── Run `sz liquidity status` → follow recommendations
└── Peer offline / stale
    └── Consider force-close: `sz channels close --force`
```

---

## Becoming a Public Routing Node

By default, every channel SaturnZap opens on mainnet is announced to the public
gossip graph if — and only if — your node looks reachable from the internet.
This makes the agent a public routing node automatically, earning routing fees
and contributing to the network's liquidity, with zero configuration.

The decision is surfaced on every `sz channels open` and `sz liquidity
request-inbound` response:

```json
{
  "announce": true,
  "announce_reason": "reachable"
}
```

Possible `announce_reason` values:

| Reason | What happened |
|---|---|
| `reachable` | Auto-gate probed the public internet and your port is open → announced. |
| `unreachable` | Auto-gate probed and your port is closed → kept private, with a hint. |
| `reachability_unknown` | Probe service was down → kept private (fail-safe). |
| `non_mainnet_default` | Signet/testnet → always private, no probe. |
| `explicit` | You passed `--announce` or `--no-announce` on the CLI. |
| `config_always` / `config_never` | Set via `[node].announce_default` in `config.toml`. |

**When `announce_reason` is `unreachable`**, the response includes a `warnings`
array with this hint: *"Node not reachable from the internet. Run `sz
connect-info --check` to verify, then open port 9735 on your cloud firewall.
Tor hidden service support is on the roadmap."*

`sz setup --auto` also emits an `announce_decision` step in its structured
log, so an agent's first-run JSON contains the routing-node verdict
immediately.

To opt out per-channel: `sz channels open --no-announce ...`. To opt out
permanently: `sz config set node.announce_default never`.

---

## Proactive Warnings

SaturnZap includes contextual warnings in payment and balance responses when action
is needed. Warnings appear as an optional `"warnings"` array — omitted when everything
is healthy.

### Where warnings appear

- **`sz pay` / `sz keysend`** — after a payment, if any channel's outbound capacity
  drops below 20% (configurable via `outbound_threshold_percent` in `config.toml`)
- **`sz balance`** — when on-chain funds exist but no Lightning channels are open,
  or when all channels are critically low
- **`sz fetch`** — propagated from the underlying L402 payment

### Agent pattern

```python
result = json.loads(subprocess.run(["sz", "pay", ...], capture_output=True).stdout)
if "warnings" in result:
    for w in result["warnings"]:
        if "no Lightning channels" in w:
            # Open a channel
            subprocess.run(["sz", "channels", "open", "--lsp", "lqwd", ...])
        elif "Low outbound" in w:
            # Log for review or request inbound liquidity
            log.warning(w)
```

---

## Anti-Patterns

| Don't | Why | Do Instead |
|-------|-----|-----------|
| Pay without `--max-sats` | Unbounded spending risk | Always set a spending cap |
| Expose mnemonic in chat/logs | Seed leak = total fund loss | Store mnemonic offline, never log it |
| Skip balance check before large payment | Payment will fail with unhelpful LDK error | Use `sz balance` or trust pre-flight checks |
| Open channels without on-chain funds | Channel open will fail | Fund wallet first, check `sz balance` |
| Force-close channels without reason | Funds locked for timelock period | Use cooperative close unless peer is offline |
| Run two agents on the same seed directory | File lock conflicts, state corruption | One agent per data directory |
| Ignore `sz liquidity status` warnings | Channels degrade over time | Act on recommendations (rebalance, close stale) |

---

## MCP vs CLI: When to Use Which

| Scenario | Use |
|----------|-----|
| Agent framework with MCP support | `sz mcp` — 24 native tools, no shell needed |
| Shell scripts, cron jobs, SSH automation | CLI — `sz` commands with JSON output |
| Debugging or manual testing | CLI with `--pretty` flag |
| systemd persistent node | `sz service install` — node stays up between calls |

---

## JSON Output Parsing Guide

Every `sz` command outputs JSON:

- **stdout**: Success envelope — `{"status": "ok", ...fields}`
- **stderr**: Error envelope — `{"status": "error", "code": "...", "message": "..."}`
- **Exit code**: 0 on success, 1 on error

**Agent decision pattern:**

```python
import json, subprocess

result = subprocess.run(["sz", "balance"], capture_output=True, text=True)
if result.returncode == 0:
    data = json.loads(result.stdout)
    lightning_sats = data["lightning_sats"]
else:
    error = json.loads(result.stderr)
    code = error["code"]  # e.g., "NO_SEED", "NODE_NOT_RUNNING"
```

---

## Security Checklist for Agents

1. Set `SZ_PASSPHRASE` via environment variable (never hardcode in scripts)
2. Always use `--max-sats` on outbound payments
3. Set `SZ_MCP_MAX_SPEND_SATS` for MCP server spending cap
4. Never emit the mnemonic after initial `sz init`
5. Use `sz backup` before risky operations
6. Monitor channel health with `sz liquidity status`
7. Use `--network signet` for development and testing with free test coins
8. Mainnet is the default — use `--yes` or `SZ_MAINNET_CONFIRM=yes` only in pipelines you trust
