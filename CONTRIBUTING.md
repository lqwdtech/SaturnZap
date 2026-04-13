# Contributing to SaturnZap

Thanks for your interest in contributing! SaturnZap is an open-source Lightning wallet
for AI agents, and contributions are welcome.

---

## Development Setup

```bash
# Prerequisites: Python 3.12+, uv (https://docs.astral.sh/uv/)
git clone https://github.com/ShoneAnstey/SaturnZap.git
cd SaturnZap
uv venv
source .venv/bin/activate
uv sync
```

Verify the install:

```bash
sz --help
uv run ruff check src/ tests/
uv run pytest tests/ -v
```

> **Important:** After code changes, run `uv sync` to reinstall the package before
> testing. The `sz` entry point runs the installed package, not source directly.

---

## Running Tests

```bash
# All unit tests (324 tests, no network required)
uv run pytest tests/ -v

# Skip live tests (require running droplets)
uv run pytest tests/ -m "not live and not mainnet" -v

# Single test file
uv run pytest tests/test_cli.py -v

# With coverage
uv run pytest tests/ --cov=saturnzap
```

Tests mock the LDK Node — no real Lightning node is needed for unit tests.

---

## Code Style

- **Linter/formatter:** ruff (runs automatically in pre-commit)
- **Target:** Python 3.12 — use modern syntax (type hints, `|` unions, f-strings)
- **Output:** All CLI output must go through `output.ok()` or `output.error()` — never `print()`
- **JSON only:** Commands produce `{"status": "ok", ...}` on stdout or `{"status": "error", ...}` on stderr

Run the linter:

```bash
uv run ruff check src/ tests/
uv run ruff format --check src/ tests/
```

---

## Project Structure

```
src/saturnzap/
├── cli.py          # Typer CLI entry point (sz)
├── node.py         # LDK Node lifecycle
├── output.py       # JSON output helpers (ok/error)
├── config.py       # TOML config + Esplora fallback
├── keystore.py     # BIP39 seed + Fernet encryption
├── ipc.py          # Unix Domain Socket IPC daemon
├── payments.py     # BOLT11 invoices, keysend, history
├── l402.py         # HTTP 402 interceptor, token cache
├── liquidity.py    # Channel health scoring
├── lqwd.py         # LQWD peer directory
├── mcp_server.py   # FastMCP stdio server (20 tools)
├── service.py      # Systemd service generator
└── backup.py       # Wallet backup/restore

tests/
├── conftest.py     # Autouse fixtures (reset XDG, output, node)
├── test_*.py       # Unit tests (mock LDK Node)
├── live/           # Live droplet tests (pytest -m live)
└── ...
```

---

## Making Changes

1. **Fork and branch** — create a feature branch from `main`
2. **Write tests** — new features need tests; bug fixes need regression tests
3. **Run checks** — `uv run ruff check src/ tests/` and `uv run pytest tests/`
4. **Update docs** — the pre-commit hook blocks commits to `src/` without matching `docs/` changes
5. **Submit a PR** — describe what changed and why

### Pre-commit Hooks

The repo has pre-commit hooks that run automatically:

- **Security scan** — ruff, bandit, pip-audit, detect-secrets on staged `src/` files
- **Doc gate** — blocks commits to `src/` without `docs/` or `README.md` changes

### Commit Messages

Follow conventional commits:

```
feat: add channel rebalancing command
fix: handle expired invoice in L402 retry
docs: update MCP server setup for Cursor
chore: bump cryptography to 46.0.7
```

---

## Architecture Guidelines

- **JSON output** — every command uses `output.ok()` / `output.error()`, never plain text
- **IPC routing** — CLI commands check `_use_ipc()` first; if daemon is running, route through UDS
- **Network namespacing** — all paths are under `~/.local/share/saturnzap/<network>/`
- **No interactive prompts** — except mainnet confirmation (suppressible with `--yes`)
- **Spending caps** — always support `--max-sats` on payment commands

See [docs/architecture.md](docs/architecture.md) for the full design.

---

## Questions?

Open an issue at [github.com/ShoneAnstey/SaturnZap/issues](https://github.com/ShoneAnstey/SaturnZap/issues).
