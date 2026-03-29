# Architecture

SaturnZap is a modular Python application with a clear separation between the CLI
interface, the wallet core, and the Lightning node runtime.

---

## Component Map

```
┌─────────────────────────────────────────────────────────────────┐
│                     Integration Layer                           │
│                                                                 │
│  ┌─────────────┐  ┌──────────────────┐  ┌───────────────────┐  │
│  │   sz CLI     │  │   MCP Server     │  │  OpenClaw Skill   │  │
│  │  (typer)     │  │  (FastMCP/stdio) │  │  (gateway)        │  │
│  └──────┬───────┘  └────────┬─────────┘  └────────┬──────────┘  │
│         │                   │                      │            │
│         └───────────────────┼──────────────────────┘            │
│                             │                                   │
└─────────────────────────────┼───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                       Wallet Core                               │
│                                                                 │
│  node.py        — LDK Node lifecycle, channels, peers           │
│  payments.py    — BOLT11 send/receive, keysend, history         │
│  l402.py        — HTTP 402 intercept → pay invoice → retry      │
│  liquidity.py   — channel health scoring, recommendations       │
│  keystore.py    — BIP39 seed, PBKDF2 + Fernet encryption       │
│  lqwd.py        — LQWD 18-region node directory                 │
│  config.py      — config paths, Esplora fallback resolver       │
│  output.py      — JSON envelope formatting, TTY detection       │
│                                                                 │
└─────────────────────────────┬───────────────────────────────────┘
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│                       LDK Node Runtime                          │
│                                                                 │
│  - Full Lightning protocol (BOLT 1-11)                          │
│  - Esplora chain sync (REST API, no full node)                  │
│  - BIP39 entropy + key derivation                               │
│  - Peer connections and channel state machine                   │
│  - Gossip (P2P graph sync)                                      │
│  - Pathfinding and payment routing                              │
│                                                                 │
└──────────────┬────────────────────────┬─────────────────────────┘
               │                        │
┌──────────────▼──────────┐  ┌──────────▼──────────────────┐
│   LQWD Global Nodes     │  │   Any Lightning Node        │
│   (18 nodes, 18         │  │   (agent peers with any     │
│   countries, deep       │  │   public node on the        │
│   liquidity)            │  │   Lightning Network)        │
└─────────────────────────┘  └─────────────────────────────┘
```

---

## Module Reference

### `cli.py` — Command Interface

The Typer-based CLI. Defines all `sz` subcommands. Each command delegates to the
wallet core and writes JSON via `output.ok()` / `output.error()`.

Entry point: `main_cli()` — wraps the Typer app with ldk-node import checking and
a structured error handler that maps LDK exceptions to JSON error codes.

### `mcp_server.py` — MCP Server

FastMCP server exposing 20 tools over stdio JSON-RPC. Uses an async lifespan context
to start the LDK node once on server boot and stop it on shutdown.

Entry points: `serve()` function, `sz mcp` CLI command, `sz-mcp` standalone binary.

### `node.py` — LDK Node Lifecycle

Manages the LDK Node instance. Key pattern: `_require_node()` auto-starts the node
from the encrypted seed on first call. Subsequent calls within the same process reuse
the cached instance.

Functions: `build_node()`, `start()`, `stop()`, `get_status()`, `_require_node()`,
`new_onchain_address()`, `get_balance()`, peer management, channel management.

### `payments.py` — Lightning Payments

BOLT11 invoice creation (fixed and variable amount), payment sending with optional
spending caps, keysend (spontaneous payments), and transaction history with pagination.

### `l402.py` — L402 HTTP Interceptor

Makes HTTP requests. On HTTP 402, extracts the LSAT/L402 challenge from the
`WWW-Authenticate` header, pays the embedded Lightning invoice, caches the token,
and retries the request with the authorization header.

Token cache: SHA256-hashed URL → token file in `~/.local/share/saturnzap/l402_tokens/`.

### `liquidity.py` — Liquidity Intelligence

Computes per-channel health scores (0–100, peaks at 50% outbound ratio). Generates
actionable recommendations: low outbound warnings, low inbound alerts, pending channel
notifications. Supports inbound liquidity requests via LQWD.

### `keystore.py` — Seed Encryption

BIP39 mnemonic generation via LDK Node's built-in entropy. Encrypted at rest with
Fernet (AES-128-CBC + HMAC-SHA256). Key derivation: PBKDF2-HMAC-SHA256 with 600,000
iterations and a random 16-byte salt.

### `lqwd.py` — LQWD Node Directory

Static directory of 18 LQWD Lightning nodes across 18 regions. Timezone-based
auto-selection picks the nearest node. Override with `SZ_REGION` env var.

### `config.py` — Configuration

TOML config loader with OS-appropriate paths (via `platformdirs`). Esplora fallback
resolver probes multiple endpoints per network and picks the first healthy one.

### `output.py` — JSON Output

All output goes through two functions: `ok(**fields)` writes success JSON to stdout,
`error(code, message)` writes error JSON to stderr and raises `SystemExit`.

---

## Design Decisions

### Esplora over Neutrino

LDK Node supports both Neutrino (compact block filters) and Esplora (REST API) for
chain data. SaturnZap uses Esplora because:

- No peer discovery needed — just an HTTP endpoint
- Public Esplora servers are widely available (mempool.space, blockstream.info)
- Fallback chain provides resilience: probe multiple servers, use first healthy one
- Self-hosted Esplora is simple to run (Bitcoin Core + electrs behind Cloudflare)

### Auto-start Pattern

Each CLI command is a separate process. Instead of requiring a long-running daemon,
SaturnZap uses `_require_node()` to auto-start the LDK node on first access within
each process. The MCP server uses a lifespan context to keep the node running for
the full session.

### JSON-first Output

Every command writes a JSON object to stdout with `"status": "ok"` or `"error"`. This
makes SaturnZap trivially parseable by any programming language. Error details go to
stderr with structured codes, not just exit codes.

### Non-custodial by Design

The BIP39 seed is generated locally, encrypted locally, and never transmitted anywhere.
The passphrase is an environment variable — it never appears in config files, logs, or
MCP tool parameters (after initialization).

### LQWD as Default, Not Requirement

LQWD node pubkeys are embedded for convenience. Agents can peer with any Lightning node.
The timezone-based auto-selector is a shortcut — not a lock-in mechanism.

### Spending Caps

Both the CLI (`--max-sats`) and MCP server (`max_sats` parameter, `SZ_MCP_MAX_SPEND_SATS`
env var) support spending caps. For autonomous agents, this is a critical safety boundary.

---

## Security Model

| Layer | Mechanism |
|---|---|
| Seed at rest | Fernet encryption (AES-128-CBC + HMAC-SHA256), PBKDF2 600K iterations |
| Seed permissions | `0600` on `seed.enc` and `seed.salt` |
| Passphrase | Environment variable only — never written to disk, never in MCP I/O |
| MCP transport | stdio only — no network listener, no open ports |
| L402 tokens | Per-URL cache files with `0600` permissions |
| Dependencies | pip-audit in pre-commit hook, accepted risks documented |
| Static analysis | ruff + bandit in pre-commit hook |
| Secret scanning | detect-secrets in pre-commit hook |

---

## Technology Stack

| Component | Library | Version | Notes |
|---|---|---|---|
| Language | Python | 3.12 | Type hints throughout |
| Lightning | ldk-node | 0.7.0 | Built from Rust source, vendored wheel |
| CLI | typer | ≥0.15 | Auto-generated help, clean API |
| MCP | mcp (FastMCP) | ≥1.26 | stdio JSON-RPC, async lifespan |
| HTTP | httpx | ≥0.28 | L402 interceptor, Esplora probing |
| Config | platformdirs | ≥4.3 | OS-appropriate paths |
| Encryption | cryptography | ≥44.0 | Fernet + PBKDF2 |
| BIP39 | mnemonic | ≥0.21 | Seed phrase generation |
| Env | python-dotenv | ≥1.2 | `.env` file loading |
| Build | hatchling | — | PEP 517 build backend |
| Testing | pytest | ≥8.0 | 95 tests |
| Linting | ruff | ≥0.9 | Lint + format |
| Security | bandit + pip-audit + detect-secrets | — | Pre-commit security scan |

---

## CI/CD

### `ci.yml` — Continuous Integration

Runs on every push and pull request to `main`:

1. Install Python 3.12 + uv
2. `uv sync` — install dependencies
3. `ruff check` — lint
4. `pytest` — run test suite
5. `hatch build` — verify the package builds

### `publish.yml` — PyPI Release

Triggered on version tags (`v*`):

1. Build sdist + wheel
2. Upload ldk-node vendored wheel to GitHub Release
3. Publish to PyPI via trusted publisher

---

## Testing

95 tests across 9 test files:

| File | Tests | Covers |
|---|---|---|
| `test_cli.py` | CLI smoke tests | Help output, no-seed errors, subcommand registration |
| `test_keystore.py` | Seed encryption | Generate, encrypt, decrypt, wrong passphrase, permissions |
| `test_output.py` | JSON output | ok/error format, pretty mode, TTY detection |
| `test_lqwd.py` | Node directory | Region filter, timezone selection, SZ_REGION override |
| `test_payments.py` | Payment helpers | Kind/direction/status string conversion |
| `test_l402.py` | L402 parsing | LSAT/L402 header formats, token caching |
| `test_liquidity.py` | Health scoring | Score calculation, labels, recommendations |
| `test_config.py` | Esplora fallback | Config override, probe logic, timeout, all-fail |
| `test_mcp_server.py` | MCP server | Tool registration, tool count, function tests |

All tests run without a real LDK node — they mock or test pure logic.
