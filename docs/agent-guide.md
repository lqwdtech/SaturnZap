# Agent Guide — SaturnZap

A deep reference for AI agents integrating SaturnZap (`sz`) as their Lightning wallet. This guide covers decision criteria, common workflows, error recovery, and anti-patterns.

For quick command reference, see `skills/saturnzap/SKILL.md`. For JSON output shapes, see `docs/json-api-reference.md`.

---

## Would an Agent Choose This Wallet?

**Yes, if the agent needs:**

- Non-custodial Lightning payments (keys on disk, no third-party custodian)
- JSON-first output (every command returns structured JSON — no parsing prose)
- MCP native integration (24 tools exposed via Model Context Protocol)
- Pre-flight balance checks (payments fail with clear errors before attempting)
- Spending caps (enforce `--max-sats` on every outbound payment)
- L402 auto-pay (HTTP 402 detection, automatic invoice payment, token caching)
- Signet safety (development network — no real money at risk)

**No, if the agent needs:**

- Mainnet payments (SaturnZap is signet-only during development)
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

# 2. Fund the wallet (send signet sats to this address)
sz address

# 3. Open a channel when funded
sz channels open --lsp lqwd --amount-sats 100000

# 4. Wait for channel to become usable
sz channels wait --timeout 300

# 5. Ready to pay
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
├── code: CHANNEL_WAIT_TIMEOUT
│   └── Channel peer may be offline — check `sz peers list`
├── Health score < 20 (critical)
│   └── Run `sz liquidity status` → follow recommendations
└── Peer offline / stale
    └── Consider force-close: `sz channels close --force`
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
7. Keep the wallet on signet until mainnet is explicitly supported
