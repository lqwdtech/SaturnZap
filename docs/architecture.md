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
│                    ┌────────▼────────┐                          │
│                    │   IPC Client    │ (auto-detect daemon)     │
│                    │   UDS socket    │                          │
│                    └────────┬────────┘                          │
└─────────────────────────────┼───────────────────────────────────┘
                              │ Unix Domain Socket (sz.sock)
┌─────────────────────────────▼───────────────────────────────────┐
│                  Daemon (sz start — foreground, blocks)         │
│                                                                 │
│  ┌──────────────┐  ┌───────────────────────────────────────┐    │
│  │  IPC Server   │  │           Wallet Core                 │    │
│  │  (asyncio     │  │                                       │    │
│  │   UDS server) │──│  node.py     — LDK Node lifecycle     │    │
│  │  23 methods   │  │  payments.py — BOLT11 send/receive    │    │
│  └──────────────┘  │  l402.py     — L402 HTTP interceptor   │    │
│                    │  liquidity.py — channel health          │    │
│                    │  keystore.py  — BIP39 seed encryption   │    │
│                    │  lqwd.py      — LQWD node directory     │    │
│                    │  config.py    — configuration           │    │
│                    │  output.py    — JSON formatting         │    │
│                    │  ipc.py       — IPC protocol/server     │    │
│                    └───────────────────────────────────────┘    │
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

FastMCP server exposing 25 tools over stdio JSON-RPC. Uses an async lifespan context
to start the LDK node once on server boot and stop it on shutdown.

Entry points: `serve()` function, `sz mcp` CLI command, `sz-mcp` standalone binary.

### `node.py` — LDK Node Lifecycle

Manages the LDK Node instance. Key pattern: `_require_node()` auto-starts the node
from the encrypted seed on first call. Subsequent calls within the same process reuse
the cached instance.

When a daemon is running, `_use_ipc()` auto-detects the IPC socket and routes all
public function calls through it. The local LDK node is never touched in IPC mode.

Functions: `build_node()`, `start()`, `stop()`, `get_status()`, `get_connect_info()`,
`_require_node()`, `new_onchain_address()`, `get_balance()`, peer management, channel management.

### `ipc.py` — IPC Layer

Unix Domain Socket IPC layer. The daemon hosts an asyncio UDS server on
`~/.local/share/saturnzap/<network>/sz.sock`. CLI commands and the MCP server
connect as thin clients.

Protocol: newline-delimited JSON. 23 methods covering node lifecycle, payments,
channels, liquidity, L402, and daemon shutdown. Socket permissions: `0600` (owner only).
Thread-safe: a `threading.Lock` serializes LDK calls on the server side.

Classes: `IPCServer`, `IPCError`, `IPCConnectionError`.
Functions: `ipc_call()`, `daemon_is_running()`, `build_dispatcher()`.

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

Static directory of LQWD Lightning nodes: 18 regional nodes plus the agent-focused
`LQWD-AI-Grid` (region code `AI`, LSPS1/LSPS2 JIT-capable). On mainnet, `AI` is the
default selection. `SZ_REGION=NEAREST` opts in to timezone-based selection across
the geographic fleet; `SZ_REGION=<code>` pins a specific region.

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

### Auto-start and IPC Patterns

Each CLI command is a separate process. The `_use_ipc()` function auto-detects whether
a daemon is running by probing the IPC socket. If a daemon exists, all calls route
through Unix Domain Socket IPC (like Docker and lnd). If no daemon is running,
`_require_node()` auto-starts the LDK node from the encrypted seed.

The MCP server uses the same detection: if a daemon is running, it becomes a thin
IPC client. Otherwise, it starts its own node via a lifespan context.

This means CLI, MCP, and OpenClaw can all use the wallet simultaneously — no port
conflicts, no database locks.

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
On mainnet the default is `LQWD-AI-Grid` (LSPS1/LSPS2 JIT-capable), with the 18-region
geographic fleet available via `SZ_REGION=NEAREST` or a specific region code. None of
this is a lock-in — it is a shortcut for first-run setup.

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
| IPC socket | Unix Domain Socket with `0600` permissions, owner-only access |
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
| Testing | pytest | ≥8.0 | 415 tests |
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

415 tests across 24 test files:

| File | Tests | Covers |
|---|---|---|
| `test_cli.py` | CLI smoke tests | Help output, no-seed errors, subcommand registration |
| `test_keystore.py` | Seed encryption | Generate, encrypt, decrypt, wrong passphrase, permissions |
| `test_output.py` | JSON output | ok/error format, pretty mode, TTY detection, CommandError |
| `test_lqwd.py` | Node directory | Region filter, timezone selection, SZ_REGION override |
| `test_payments.py` | Payment helpers | Kind/direction/status string conversion, preimage extraction, post-payment warnings |
| `test_l402.py` | L402 parsing | LSAT/L402 header formats, token caching, preimage auth, warning propagation |
| `test_liquidity.py` | Health scoring | Score calculation, labels, recommendations, balance/payment warnings |
| `test_config.py` | Config & env vars | Config override, probe logic, SZ_NETWORK/SZ_ESPLORA_URL |
| `test_mcp_server.py` | MCP server | Tool registration, tool count, function tests |
| `test_ipc.py` | IPC layer | Echo, errors, CommandError fidelity, shutdown, concurrency |
| `test_node.py` | Node lifecycle | Build, start, stop, IPC routing, channel rejection detection |
| `test_backup.py` | Backup/restore | Export, import, round-trip |
| `test_service.py` | Systemd service | Unit file generation, install, uninstall |
| `integration/` | Multi-command flows | Channel lifecycle, payment flow, error cascades, full lifecycle |
| `security/` | Security hardening | Input validation, seed security, spending guards |
| `reliability/` | Edge cases | Timeout handling, retry logic, concurrent access |
| `ux/` | Agent scenarios | JSON output validity, agent workflow patterns |
| `live/` | Droplet tests | Real mainnet connectivity, peer-to-peer (marked `@live`) |

All tests run without a real LDK node — they mock or test pure logic.
