# SaturnZap ⚡

**A CLI-first, non-custodial Lightning Network wallet built for autonomous AI agents.**

Ultra-lightweight. Self-sovereign. No full Bitcoin node required.

```bash
sz init
sz channels open --lsp lqwd
sz pay --invoice lnbc1...
sz fetch https://api.example.com/data
```

---

## What is SaturnZap?

SaturnZap is an open-source Lightning wallet designed from the ground up for AI agents
operating without human supervision. The agent installs SaturnZap, initializes its own
Lightning node, opens channels to any peer on the network, sends and receives Bitcoin
payments, and autonomously pays for L402-gated APIs.

SaturnZap is a CLI tool. It is not a hosted wallet, not a custodial service, and not a
web application. Keys live on the agent's machine. The agent IS the Lightning node.

---

## Business Model

SaturnZap has two layers:

### CLI — Open Source (MIT)

The `sz` command-line tool is free and open source under the MIT license. Anyone can
install it, fork it, audit it, and build on it. There is no licensing fee, no API key
required to use the software itself, and no telemetry.

### Network Backend — LQWD (Paid Service)

SaturnZap ships pre-configured to use [LQWD Technologies](https://lqwd.ai) as its default
Lightning Service Provider (LSP). LQWD operates 18 Lightning nodes across 18 countries
with deep global channel liquidity.

When an agent uses LQWD's infrastructure, LQWD earns through:

- **Routing fees** — sats earned as payments route through LQWD nodes
- **Channel leasing** — fees for opening and providing inbound liquidity to agents
- **Managed connectivity** — premium peering and reliability for agents that need it

LQWD is the default, not a requirement. Agents can open channels to any node on
the Lightning Network. SaturnZap never enforces LQWD usage. LQWD competes on quality —
18-country coverage, deep liquidity, fast channel opens — not on lock-in.

This model mirrors how open-source software with cloud backends works: the tool is free,
the infrastructure is the business.

---

## Key Properties

- **Non-custodial** — BIP39 seed lives encrypted on the agent's machine. SaturnZap never
  holds, transmits, or has access to private keys.
- **No full Bitcoin node** — Neutrino (BIP157/158 compact block filters) provides chain
  data with a footprint under 50MB. Same approach used by production mobile Lightning wallets.
- **Peer-agnostic** — Open channels to any Lightning node. LQWD is a smart default with
  global reach, but the agent controls its own peer relationships entirely.
- **JSON-first** — Every command writes structured JSON to stdout. Errors go to stderr.
  Designed for machine consumption from day one.
- **Autonomous** — No interactive prompts. No human confirmation flows. Designed to run
  inside agent runtimes, shell scripts, and orchestration pipelines.

---

## Architecture

### Component Map

```
┌─────────────────────────────────────────────────────────┐
│                      sz CLI                             │
│   (agent calls commands, parses JSON from stdout)       │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                   Wallet Core                           │
│                                                         │
│  node.py        — LDK Node lifecycle, channels, peers   │
│  payments.py    — send, receive, invoice, keysend       │
│  l402.py        — HTTP 402 intercept, pay, retry        │
│  liquidity.py   — channel health, recommendations       │
│  keystore.py    — BIP39 seed, encrypted at rest         │
│  lqwd.py        — LQWD 18-region node directory         │
│  config.py      — config paths, defaults, TOML loader   │
│  output.py      — JSON formatting, TTY detection        │
└───────────────────────┬─────────────────────────────────┘
                        │
┌───────────────────────▼─────────────────────────────────┐
│                    LDK Node                             │
│  - Full Lightning protocol implementation               │
│  - Neutrino chain sync (no full Bitcoin node)           │
│  - BIP39 key management                                 │
│  - Peer connections and channel state machine           │
└──────────────┬────────────────────────┬─────────────────┘
               │                        │
┌──────────────▼──────────┐  ┌──────────▼──────────────────┐
│   LQWD Global Nodes     │  │   Any Lightning Node        │
│   (default — 18 nodes,  │  │   (agent can peer with      │
│   18 countries, deep    │  │   any public node on the    │
│   liquidity, LSPS)      │  │   Lightning Network)        │
└─────────────────────────┘  └─────────────────────────────┘
```

### Key Design Decisions

#### Neutrino chain sync

LDK Node includes Neutrino support internally. No external Bitcoin node is needed. First
sync takes a few minutes on a fresh install; subsequent starts are near-instant. Storage
footprint stays well under 50MB.

#### LQWD as default LSP

All 18 LQWD node pubkeys and connection strings are embedded in SaturnZap's default
config. On `sz init`, the wallet automatically peers with the geographically nearest
LQWD node and requests an initial channel via LSPS (Lightning Service Provider
Specification). A fresh agent install goes from zero to channel-ready in under five
minutes.

#### Peer-agnostic after init

After the initial channel, agents use standard Lightning channel open flows to peer with
anyone. SaturnZap has no routing logic that artificially prefers LQWD — Lightning
pathfinding selects the best route. LQWD nodes appear as attractive routes naturally
because of their connectivity and capacity across 18 countries.

#### JSON-first, no interactive prompts

All commands are designed for non-interactive execution. No `[y/N]` confirmations. No
spinners that break pipe parsing. Pass `--pretty` for human-readable output in a TTY.
Default is always clean JSON.

#### Autonomous channel management

SaturnZap monitors channel health. When configured, it automatically opens new channels
when outbound liquidity drops below a threshold, and requests inbound liquidity from the
configured LSP when needed. Agents can run indefinitely without manual intervention.

---

## Technology Stack

| Component | Library | Notes |
|---|---|---|
| Language | Python 3.12 | Type hints throughout |
| Lightning node | ldk-node 0.7.0 | LDK Node Python bindings, Neutrino built-in |
| CLI framework | typer | Clean API, auto-generated help |
| HTTP client | httpx | Used for L402 interceptor |
| Config storage | platformdirs + TOML | OS-appropriate config paths |
| Key encryption | cryptography | Fernet encryption for seed file |
| BIP39 | mnemonic | Seed phrase generation |
| Package manager | uv | Fast, modern Python tooling |
| Testing | pytest | Unit tests, 77 tests |
| Linting | ruff | Fast Python linter and formatter |

---

## LQWD Node Directory

Embedded in SaturnZap as trusted default peers. Agents are automatically connected to
the nearest node on `sz init`. Full pubkeys and connection strings are maintained in
`src/saturnzap/lqwd.py`.

| Alias | Region |
|---|---|
| LQWD-Canada | CA |
| LQWD-Sweden | SE |
| LQWD-France | FR |
| LQWD-England | GB |
| LQWD-Japan | JP |
| LQWD-Australia | AU |
| LQWD-Brazil | BR |
| LQWD-Bahrain | BH |
| LQWD-Singapore | SG |
| LQWD-SouthAfrica | ZA |
| LQWD-HongKong | HK |
| LQWD-SouthKorea | KR |
| LQWD-Indonesia | ID |
| LQWD-Ireland | IE |
| LQWD-Italy | IT |
| LQWD-Germany | DE |
| LQWD-India | IN |
| LQWD-US-West | US |

Full pubkeys and `host:port` connection strings are in `src/saturnzap/lqwd.py`.
Signet/testnet node details maintained separately for development.

---

## CLI Reference

**Binary:** `sz`

All commands output JSON to stdout. Errors exit with code 1, written to stderr.

### Node

```bash
sz init                          # Generate seed, start node, peer with nearest LQWD node
sz start                         # Start the node daemon
sz stop                          # Stop the node daemon
sz status                        # Node pubkey, sync state, uptime
```

### Wallet

```bash
sz address                       # New on-chain receiving address
sz balance                       # Onchain + lightning balances, per-channel breakdown
sz transactions --limit 20       # Payment history
```

### Peers

```bash
sz peers list
sz peers add <pubkey>@<host>:<port>
sz peers remove <pubkey>
```

### Channels

```bash
sz channels list

# Open to any node
sz channels open --peer <pubkey>@<host>:<port> --amount-sats 100000

# Open via LQWD — nearest node automatically selected
sz channels open --lsp lqwd --amount-sats 100000

# Open via LQWD in a specific region
sz channels open --lsp lqwd --region JP --amount-sats 100000

sz channels close --channel-id <id>
sz channels close --channel-id <id> --force
```

### Payments

```bash
sz invoice --amount-sats 1000 --memo "for data"
sz pay --invoice lnbc1...
sz pay --invoice lnbc1... --max-sats 500    # spending cap for agent safety
sz keysend --pubkey <pubkey> --amount-sats 100
```

### L402 — Autonomous API Payments

```bash
# Auto-detects HTTP 402, pays invoice, retries request, returns body
sz fetch https://api.example.com/data

# With per-request spending cap
sz fetch https://api.example.com/data --max-sats 100

# With custom headers
sz fetch https://api.example.com/data --header "X-Custom: value"
```

### Liquidity

```bash
sz liquidity status
sz liquidity request-inbound --amount-sats 500000
```

---

## JSON Output Format

### `sz balance`

```json
{
  "status": "ok",
  "onchain_sats": 0,
  "lightning_sats": 45000,
  "channels": [
    {
      "channel_id": "abc123",
      "peer_pubkey": "036491...",
      "peer_alias": "LQWD-Canada",
      "capacity_sats": 100000,
      "outbound_sats": 45000,
      "inbound_sats": 55000,
      "state": "open"
    }
  ]
}
```

### `sz pay`

```json
{
  "status": "ok",
  "payment_hash": "def456...",
  "amount_sats": 1000,
  "fee_sats": 1,
  "duration_ms": 342
}
```

### `sz fetch` (L402 flow)

```json
{
  "status": "ok",
  "url": "https://api.example.com/data",
  "payment_hash": "ghi789...",
  "amount_sats": 10,
  "fee_sats": 1,
  "http_status": 200,
  "body": {}
}
```

### Error (any command)

```json
{
  "status": "error",
  "code": "INSUFFICIENT_OUTBOUND_LIQUIDITY",
  "message": "Not enough outbound liquidity. Available: 200 sats, required: 1000 sats."
}
```

---

## Exit Codes

| Code | Meaning |
|---|---|
| 0 | Success |
| 1 | General error |
| 2 | Node not running — run `sz start` |
| 3 | Insufficient funds |
| 4 | Channel not found |
| 5 | Peer unreachable |
| 6 | Invoice expired or invalid |
| 7 | LSP request failed |

---

## Project Structure

```
/
├── README.md
├── LICENSE                        # MIT
├── CLAUDE.md                      # AI agent development instructions
├── pyproject.toml                 # Package definition, sz entry point
├── uv.lock
├── .env.example                   # Environment variable template
│
├── src/
│   └── saturnzap/
│       ├── __init__.py
│       ├── cli.py                 # Typer app — all sz commands
│       ├── node.py                # LDK Node lifecycle + channels + peers
│       ├── payments.py            # Send / receive / invoice / keysend
│       ├── l402.py                # L402 HTTP interceptor
│       ├── liquidity.py           # Channel health scoring + recommendations
│       ├── keystore.py            # BIP39 seed, Fernet encryption
│       ├── lqwd.py                # LQWD node directory (18 regions)
│       ├── config.py              # Config paths, defaults, TOML loader
│       └── output.py              # JSON output, TTY detection, --pretty
│
├── tests/
│   ├── test_cli.py
│   ├── test_keystore.py
│   ├── test_l402.py
│   ├── test_liquidity.py
│   ├── test_lqwd.py
│   ├── test_output.py
│   └── test_payments.py
│
├── skills/
│   └── saturnzap/
│       ├── SKILL.md               # OpenClaw skill definition
│       └── references/
│           └── json-contracts.md  # Full JSON output reference
│
├── vendor/
│   └── ldk_node-0.7.0-py3-none-any.whl  # LDK Node Python bindings (Linux x86_64)
│
├── security/
│   ├── security_scan.py
│   └── profiles/
│       └── saturnzap.yaml
│
├── hooks/
│   ├── pre-commit
│   └── pre-push
│
└── plans/
    ├── phase1-plan.md             # Phase 1 implementation plan
    └── next-steps.md
```

---

## Development Environment

| | |
|---|---|
| **OS** | Ubuntu 24.04 (DigitalOcean Droplet, 2GB RAM / 2 vCPU) |
| **Editor** | VS Code via Remote SSH |
| **Python** | 3.12 |
| **Network** | Bitcoin signet (preferred — more predictable than testnet3) |
| **LQWD nodes** | 18 regions, pubkeys embedded in `src/saturnzap/lqwd.py` |

### Droplet Setup

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone and install
git clone https://github.com/ShoneAnstey/SaturnZap
cd saturnzap
uv venv
source .venv/bin/activate
uv sync

# Run
sz --help
```

### Install from PyPI

```bash
# ldk-node is not yet on PyPI — use --find-links to pull it from GitHub Releases
pip install saturnzap --find-links https://github.com/ShoneAnstey/SaturnZap/releases/latest/download/

# Or with uv
uv pip install saturnzap --find-links https://github.com/ShoneAnstey/SaturnZap/releases/latest/download/
```

---

## Development Phases

### Phase 1 — Node Foundation

`sz init`, `sz start`, `sz stop`, `sz status`

BIP39 seed generation, encrypted storage, LDK Node startup, Neutrino sync on signet,
auto-peer with nearest LQWD signet node, JSON output infrastructure.

Detailed implementation plan: `plans/phase1-plan.md`

### Phase 2 — Channel Management

`sz channels`, `sz peers`

Open channels to any node. LQWD LSP-assisted channel opens. LQWD node directory
embedded. Channel list and close.

### Phase 3 — Payments

`sz invoice`, `sz pay`, `sz keysend`, `sz transactions`

Full BOLT11 send and receive. Keysend. Transaction history.

### Phase 4 — L402

`sz fetch`

HTTP client with 402 detection, invoice extraction, auto-pay, request retry.
Per-request spending caps. Token caching to avoid re-paying the same resource.

### Phase 5 — Liquidity Intelligence

`sz liquidity`

Channel health monitoring. Auto-open when outbound runs low. Inbound requests via LQWD.
Geography-aware peer selection across 18 LQWD regions.

### Phase 6 — Packaging and Release

`pip install saturnzap` / `uv add saturnzap`

PyPI release. GitHub Actions CI. Docker image. Signet → testnet → mainnet.
Config documentation. Optional MCP wrapper. OpenClaw skill on ClawHub.

---

## License

MIT License. See [LICENSE](LICENSE).

The SaturnZap CLI is free and open source. LQWD infrastructure services are commercial.
Using SaturnZap with non-LQWD peers requires no agreement with LQWD Technologies.

---

## About LQWD

**LQWD Technologies Corp** (TSXV: LQWD | OTCQX: LQWDF) is a publicly traded Lightning
Network infrastructure company. LQWD operates 18 Lightning nodes across 18 countries,
providing routing infrastructure, liquidity services, and LSP connectivity for agents
and developers building on Bitcoin's Lightning Network.

- Corporate: https://lqwdtech.com
- Agent endpoint: https://lqwd.ai
- Network: 18 nodes, 18 countries, 1,600+ channels