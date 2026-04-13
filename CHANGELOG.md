# Changelog

All notable changes to SaturnZap are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [0.1.0] — 2026-04-13

First public release. CLI-first, non-custodial Lightning wallet for AI agents.

### Added

**Core Wallet (Phases 1-2)**
- `sz init` — BIP39 seed generation with Fernet encryption (PBKDF2, 600K iterations)
- `sz start` / `sz stop` / `sz status` — LDK Node lifecycle management
- `sz address` / `sz balance` — on-chain address generation and balance queries
- `sz peers add|remove|list` — Lightning peer management
- `sz channels open|close|list` — channel lifecycle with LQWD LSP support
- `sz pay` / `sz invoice` / `sz keysend` — BOLT11 payments and spontaneous sends
- `sz transactions` — payment history with pagination

**L402 & Liquidity (Phases 3-4)**
- `sz fetch` — HTTP client with automatic L402/LSAT payment and token caching
- `sz liquidity status` — per-channel health scoring (0-100)
- `sz liquidity request-inbound` — inbound liquidity requests via LQWD LSP
- LQWD node directory — 18 nodes across 18 countries, timezone-based auto-select

**MCP Server (Phase 5)**
- `sz mcp` / `sz-mcp` — FastMCP stdio server exposing 20 tools
- Works with Claude Desktop, Cursor, VS Code (GitHub Copilot), and any MCP client
- Async lifespan: starts LDK node on boot, stops on shutdown
- `SZ_MCP_MAX_SPEND_SATS` global spending cap

**Mainnet & IPC (Phase 6)**
- `--network signet|testnet|bitcoin` — full network switching
- Network-namespaced data directories (separate seed, channels, state per network)
- Mainnet safety confirmation prompts (`--yes` or `SZ_MAINNET_CONFIRM=yes` to skip)
- Per-network Lightning listen ports (signet=9735, testnet=9736, bitcoin=9737)
- `sz start --daemon` — Unix Domain Socket IPC daemon
- CLI and MCP auto-detect daemon, route through IPC transparently
- 22 IPC methods, newline-delimited JSON, `threading.Lock` serialization

**Infrastructure**
- Esplora fallback chain — probes multiple endpoints, uses first healthy one
- OpenClaw skill (`skills/saturnzap/SKILL.md`) for agent integration
- `sz service install|uninstall|status` — systemd service generator
- `sz setup --auto` — idempotent first-run setup
- JSON-first output: `output.ok()` / `output.error()` on all commands
- 324 unit tests, 24 live/mainnet tests
- CI pipeline (ruff + pytest + build) on push/PR
- PyPI publish via trusted publisher on version tags
- Security scanning (ruff, bandit, pip-audit, detect-secrets) in pre-commit

### Security

- Seed encrypted at rest: Fernet (AES-128-CBC + HMAC-SHA256), PBKDF2 600K iterations
- File permissions: `0600` on seed, salt, IPC socket, L402 tokens
- Passphrase via `SZ_PASSPHRASE` env var only — never written to disk or logs
- MCP transport: stdio only — no network listener, no open ports
- Spending caps on payments and L402 fetches
