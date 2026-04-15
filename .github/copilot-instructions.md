# SaturnZap — Copilot Instructions

CLI-first, non-custodial Lightning Network wallet for AI agents. Python 3.12, LDK Node, mainnet default.

## Build & Test

```bash
uv sync                              # Install deps (never pip)
uv run ruff check src/ tests/        # Lint
uv run pytest tests/ -v              # Unit tests (-m "not live" to skip droplet tests)
uv build                             # Build wheel
```

After code changes, run `uv sync` to reinstall the package before testing.

## Architecture

All source lives in `src/saturnzap/`. Key modules:

| Module | Role |
|--------|------|
| `cli.py` | Typer CLI entry point (`sz`). Each command → JSON output |
| `node.py` | LDK Node lifecycle. `_require_node()` lazy-starts; `_use_ipc()` auto-detects daemon |
| `output.py` | `ok(**fields)` → stdout JSON, `error(code, msg)` → stderr JSON + exit |
| `config.py` | TOML config + Esplora fallback resolver (3s probe timeout) |
| `keystore.py` | BIP39 seed + Fernet encryption (PBKDF2, 600K iterations, 16-byte salt) |
| `ipc.py` | Unix Domain Socket daemon. Newline-delimited JSON, 23 methods, `threading.Lock` |
| `payments.py` | BOLT11 invoices, keysend, spending caps, history |
| `l402.py` | HTTP 402 interceptor, token cache (SHA256-hashed URL) |
| `liquidity.py` | Channel health scoring (0–100), recommendations |
| `lqwd.py` | LQWD peer directory — 18 regions, timezone-based auto-select |
| `mcp_server.py` | FastMCP stdio server, 20 tools |
| `service.py` | Systemd service generator |

See [docs/architecture.md](../docs/architecture.md) for diagrams and IPC protocol details.

## Conventions

- **Output is always JSON**: `{"status": "ok", ...}` or `{"status": "error", "code": "...", "message": "..."}`. Never print plain text. Use `output.ok()` / `output.error()`.
- **IPC routing**: CLI commands check `_use_ipc()` first. If daemon is running, route through UDS; otherwise start ephemeral node.
- **Network-namespaced paths**: `~/.local/share/saturnzap/<network>/` — each network (signet, bitcoin) has separate seed, socket, config.
- **Passphrase**: `SZ_PASSPHRASE` env var or interactive prompt. No caching.
- **Module-level singletons**: `_node`, `_ipc_mode`, `_active_network`, `_pretty` — use `global` with `# noqa: PLW0603`.
- **Mainnet safety**: `_confirm_mainnet(yes)` gate on any command touching bitcoin network.
- **LDK Node v0.7.0**: Vendored wheel at `vendor/`. API: `builder.set_entropy_bip39_mnemonic(mnemonic, None)`, `generate_entropy_mnemonic(None)`.
- **Commit messages**: Plain English, no conventional-commit prefixes (`feat:`, `fix:`, `chore:`). Lead with the outcome. Avoid alarm words (`fix`, `bug`, `warning`, `error`, `vulnerability`). Examples: `Add smart health alerts for payments and balances`, `Security hardening — payment proofs, graceful shutdown, and integrity checks`. Bodies may include technical detail.

## Test Patterns

- `typer.testing.CliRunner` for CLI, `unittest.mock.MagicMock` for LDK Node.
- Autouse fixtures in `conftest.py` reset XDG paths, output mode, and node singletons between tests.
- `NO_COLOR=1` in test env; `strip_ansi()` helper for assertion stability.
- `@pytest.mark.live` for tests requiring running droplet nodes — deselected by default in CI.
- File permission checks (`0o600`) are tested for seed/socket files.

## Common Pitfalls

- Forgetting `uv sync` after code changes — the `sz` entrypoint runs the installed package, not source directly.
- IPC state leakage in tests — the autouse fixtures handle this, but new test files must import `conftest`.
- Pre-commit hook blocks pushes if `src/` changes lack matching `docs/` updates.
- Esplora fallback returns first URL on total probe failure — errors may surface later at LDK level.
- PBKDF2 600K iterations is intentionally slow (~100ms); don't reduce for convenience.

## Documentation

Detailed docs live in `docs/`. Link to them rather than duplicating:

- [getting-started.md](../docs/getting-started.md) — installation, quick start
- [configuration.md](../docs/configuration.md) — env vars, TOML config, data dirs
- [json-api-reference.md](../docs/json-api-reference.md) — command response shapes
- [mcp-server.md](../docs/mcp-server.md) — MCP server setup for Claude/Cursor/VS Code
- [agent-guide.md](../docs/agent-guide.md) — agent integration patterns, error recovery
- [security-scenarios.md](../docs/security-scenarios.md) — threat model
