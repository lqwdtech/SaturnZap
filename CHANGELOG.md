# Changelog

All notable changes to SaturnZap are documented in this file.

Format follows [Keep a Changelog](https://keepachangelog.com/).

---

## [Unreleased]

---

## [1.1.0] — 2026-04-22

LQWD faucet integration polish. Default behaviours now match real-world LSP workflows: long-running node, standard Lightning port, zero-conf channels from trusted peers, and opinionated defaults for alias and anchor reserves.

### Changed

- **`sz start` now runs as a foreground daemon by default** and blocks until SIGTERM/SIGINT. The previous "print and exit" behaviour moves behind `--foreground`. This makes the command drop into systemd units, Docker containers, and supervisors without any wrapping.
- **Default mainnet listen port is now `9735`** (the canonical Lightning port). Signet stays on `9736`, testnet on `9737`. Existing configs with an explicit `node.listen_port` are unaffected.
- **Default node alias** is populated at node build time. Priority: `SZ_ALIAS` env → `[node].alias` in `config.toml` → deterministic `saturnzap-<sha256(mnemonic)[:6]>`. Previously the alias was blank, which many LSP dashboards display as "unknown node".
- **External reachability probe** (`sz connect-info --check`) now uses [check-host.net](https://check-host.net) multi-node TCP probes instead of `portchecker.io` + `whatismyip` fallback. More reliable, returns faster, and distinguishes "closed" from "service unavailable".
- **Mainnet Esplora primary** is now `esplora.lqwd.ai` (LQWD-operated) ahead of `blockstream.info` and `mempool.space`. This landed in 1.0.2 and remains the default.

### Added

- **LQWD fleet auto-trust on mainnet.** The 18-region LQWD CLN fleet plus the LQWD LND primary are registered as `trusted_peers_no_reserve` and `trusted_peers_0conf` at node build time. Zero-balance wallets can accept their first inbound channel from LQWD without an on-chain reserve, and channels from LQWD become usable in seconds instead of waiting ~60 minutes for six confirmations.
- **`sz peers trust <pubkey>` / `sz peers untrust <pubkey>` / `sz peers trusted-list`.** Manage additional trusted peers beyond the LQWD fleet. Changes persist in `config.toml` and apply on next node start.
- **`sz config` command group** — `sz config get`, `sz config set`, `sz config unset`, `sz config list`. Edits `config.toml` programmatically, with type coercion for ints, bools, and JSON values. Agents no longer need to hand-edit TOML.
- **`sz init --for-lqwd-faucet`** preset. Sets a readable alias (`saturnzap-lqwdclaw`) on mainnet so LQWDClaw recognises the node on first contact. The no-reserve and 0-conf waivers are already on by default for LQWD pubkeys.
- **`[node]` section in `config.toml`** with fields `alias`, `listen_port`, `min_confirms`, `trusted_peers_no_reserve`.
- **`SZ_ALIAS`** and **`SZ_TRUSTED_PEERS_NO_RESERVE`** environment variables.

### Fixed

- **`sz setup --auto` no longer errors on a zero-balance wallet.** Added an explicit pre-check before calling `request_inbound`: if the on-chain balance is below a minimum-viable threshold (push fee + reserve), the step is reported as `skipped: true` with a clear reason, and `setup` exits 0. LDK exceptions from `request_inbound` are also caught and converted into skip entries instead of propagating as errors.

### Deprecated

- **`sz start --daemon`** is hidden and now a no-op (daemon is the default). `--foreground` is the escape hatch for the old behaviour. The flag will be removed in a future release.

### Agent / LSP Impact

Teams integrating SaturnZap with an LSP (LQWDClaw, Boltz, etc.) should notice:

1. First channel from the LSP becomes usable almost immediately (0-conf from trusted peers).
2. Zero-balance wallets can accept their first inbound channel (no anchor reserve required from LQWD peers).
3. Node appears with a readable alias in LSP dashboards instead of `<unknown>`.
4. `sz start` slots straight into `systemd` without `sz service install` ceremony (though `sz service install` remains the recommended persistent path).

---

## [1.0.2] — 2026-04-20

Public release polish. Metadata, badges, and installation clarity for PyPI and GitHub visibility.

### Fixed

- `sz --version` now works without requiring a subcommand (`invoke_without_command=True` on the top-level Typer app).
- `saturnzap.__version__` is now derived from installed package metadata, so it always matches the actual release rather than a hard-coded string.
- Mainnet Esplora fallback chain promotes `esplora.lqwd.ai` to the primary endpoint; `blockstream.info` and `mempool.space` remain as fallbacks.
- Input validation at the wallet boundary: `create_invoice`, `keysend`, `send_onchain`, and `open_channel` now reject non-positive amounts with `INVALID_ARGS` before contacting the node.
- `daemon_is_running()` no longer double-closes its probe socket.
- README now reports the correct MCP tool count (25).

### Changed

- `ldk-node` dependency pinned to `==0.7.0` to match the vendored wheel.
- `Development Status` classifier advanced from Alpha to Beta.
- Added PyPI, Python-versions, and License badges to the README.
- Added `Documentation`, `Changelog`, and `Security` project URLs to `pyproject.toml`.
- Added `CODE_OF_CONDUCT.md` (Contributor Covenant 2.1).
- Publish workflow now supports `workflow_dispatch` for TestPyPI dry-runs before a real release.
- `SECURITY.md` supported-versions table updated to 1.0.x.

---

## [1.0.1] — 2026-04-16

Security hardening, audit remediation, and public-repo readiness.

### Security

- **systemd secrets:** `sz service install` now writes the passphrase to `/etc/saturnzap/saturnzap.env` (mode `0600`) and references it from the unit file via `EnvironmentFile=`. The unit file itself no longer contains secrets.
- **Mainnet confirmation gate on `sz fetch`:** L402 payments on mainnet now require `--yes` or `SZ_MAINNET_CONFIRM=yes`, matching `sz pay`, `sz keysend`, and `sz send`.
- **Default spending cap on `sz fetch`:** `SZ_CLI_MAX_SPEND_SATS` environment variable caps every L402 payment when `--max-sats` is not supplied.
- **Passphrase minimum length:** `sz init` enforces a 12-character minimum. Bypass (testing only) with `SZ_ALLOW_WEAK_PASSPHRASE=1`.
- **Backup integrity validation:** `sz restore` validates payload schema — mnemonic word count (12/15/18/21/24), `format_version` type, and overall structure — before touching the keystore.

### Reliability

- **MCP error handling:** all 25 MCP tools are now wrapped in a decorator that converts `CommandError`, `SystemExit`, and unexpected exceptions into structured JSON error responses. The MCP server no longer terminates on tool errors.
- **Channel open resilience:** replaced the fixed 3-second sleep after `open_channel` with a 250 ms polling loop (up to 3 s), and made peer-rejection log parsing exception-safe.
- **Test isolation:** autouse fixture resets `node._node`, `node._ipc_mode`, and `output._pretty` between tests to eliminate state leakage.

### CLI

- Added `sz --version` flag.
- Added `--yes` / `-y` flag to `sz fetch`.

### Documentation & Release

- Added `SECURITY.md` with private disclosure policy.
- Aligned tool counts, test counts, and project status across README, CHANGELOG, CLAUDE.md, copilot-instructions, and all `docs/` files (**25 MCP tools, 23 IPC methods, 415 tests**).
- Replaced private droplet IPs in docs with RFC 5737 example addresses.
- Live-test droplet hosts now configurable via `SZ_LIVE_MAIN_HOST` and `SZ_LIVE_PEER_HOST`; live tests skip cleanly when unset.
- Added Dependabot configuration and CodeQL workflow.

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
- `sz mcp` / `sz-mcp` — FastMCP stdio server exposing 25 tools
- Works with Claude Desktop, Cursor, VS Code (GitHub Copilot), and any MCP client
- Async lifespan: starts LDK node on boot, stops on shutdown
- `SZ_MCP_MAX_SPEND_SATS` global spending cap
- Tools include: `setup_wallet`, `send_onchain`, `backup_wallet`, `restore_wallet`,
  `list_lqwd_nodes`, plus full lifecycle, wallet, peers, channels, payments, L402,
  and liquidity coverage

**Mainnet & IPC (Phase 6)**
- `--network signet|testnet|bitcoin` — full network switching
- Network-namespaced data directories (separate seed, channels, state per network)
- Mainnet safety confirmation prompts (`--yes` or `SZ_MAINNET_CONFIRM=yes` to skip)
- Per-network Lightning listen ports (signet=9735, testnet=9736, bitcoin=9737)
- `sz start --daemon` — Unix Domain Socket IPC daemon
- CLI and MCP auto-detect daemon, route through IPC transparently
- 23 IPC methods, newline-delimited JSON, `threading.Lock` serialization

**Infrastructure**
- Esplora fallback chain — probes multiple endpoints, uses first healthy one
- OpenClaw skill (`skills/saturnzap/SKILL.md`) for agent integration
- `sz service install|uninstall|status` — systemd service generator
- `sz setup --auto` — idempotent first-run setup
- JSON-first output: `output.ok()` / `output.error()` on all commands
- 415 tests (389 unit + 26 live/mainnet)
- CI pipeline (ruff + pytest + build) on push/PR
- PyPI publish via trusted publisher on version tags
- Security scanning (ruff, bandit, pip-audit, detect-secrets) in pre-commit

### Security

- Seed encrypted at rest: Fernet (AES-128-CBC + HMAC-SHA256), PBKDF2 600K iterations
- File permissions: `0600` on seed, salt, IPC socket, L402 tokens
- Passphrase via `SZ_PASSPHRASE` env var only — never written to disk or logs
- MCP transport: stdio only — no network listener, no open ports
- Spending caps on payments and L402 fetches
