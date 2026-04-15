# Getting Started

This guide walks you through installing SaturnZap, initializing your Lightning node,
funding it, and making your first payment.

---

## Prerequisites

- **OS**: Linux (Ubuntu 22.04+ recommended)
- **Python**: 3.12 or later
- **Package manager**: [uv](https://docs.astral.sh/uv/) (recommended) or pip

---

## Installation

### From source (recommended during development)

```bash
# Install uv
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# Clone and install
git clone https://github.com/ShoneAnstey/SaturnZap.git
cd SaturnZap
uv venv
source .venv/bin/activate
uv sync

# Verify
sz --help
```

### From PyPI

```bash
# ldk-node is not yet on PyPI — use --find-links for the vendored wheel
pip install saturnzap \
  --find-links https://github.com/ShoneAnstey/SaturnZap/releases/latest/download/

# Or with uv
uv pip install saturnzap \
  --find-links https://github.com/ShoneAnstey/SaturnZap/releases/latest/download/
```

---

## Quick Start

> **Default network:** SaturnZap defaults to **mainnet** (real bitcoin). To use
> signet for testing, add `--network signet` before the subcommand:
> `sz --network signet init`. See [Configuration](configuration.md#networks) for details.

### 1. Set your passphrase

The passphrase encrypts your seed on disk. Set it as an environment variable so
SaturnZap doesn't prompt interactively (important for agent use):

```bash
export SZ_PASSPHRASE="your-secure-passphrase"
```

Or add it to a `.env` file in your working directory:

```
SZ_PASSPHRASE=your-secure-passphrase
```

### 2. Run setup

For the fastest path to a working node, use `--auto`:

```bash
sz setup --auto
```

This does everything in one command:
- Generates a BIP39 seed and encrypts it
- Starts the Lightning node
- Opens the firewall port (if UFW is active)
- Generates a receive address
- Detects your external IP and builds a connection URI
- Attempts to open a channel to LQWD (skipped if wallet is unfunded)

> **Important:** Back up your 24-word mnemonic from the output. It is the only way
> to recover your funds if the seed file is lost.

### 3. Fund the wallet

Send bitcoin to the address shown in the setup output. Check your balance:

```bash
sz balance
```

> **Testing with signet?** Use `sz --network signet setup --auto` and a faucet like
> [signetfaucet.com](https://signetfaucet.com) or
> [alt.signetfaucet.com](https://alt.signetfaucet.com) to get free test coins.

### 4. Complete setup

After funding arrives, run setup again to open a channel:

```bash
sz setup --auto
```

This time it skips initialization (already done) and opens a channel to the nearest
LQWD node with your on-chain funds.

### 5. Verify connectivity

Check that peers can reach your node:

```bash
sz connect-info --check
```

This returns your connection URI and tests if the Lightning port is open from the
internet.

```bash
sz channels open --lsp lqwd --amount-sats 100000
```

### 5. Make a payment

Pay a BOLT11 invoice:

```bash
sz pay --invoice lnbc1...
```

With a spending cap for safety:

```bash
sz pay --invoice lnbc1... --max-sats 500
```

On mainnet, spending commands require confirmation (or `--yes` to skip):

```bash
sz pay --invoice lnbc1... --yes
```

### 6. Fetch an L402 resource

SaturnZap auto-detects HTTP 402 responses, pays the embedded Lightning invoice, and
retries the request:

```bash
sz fetch https://api.example.com/paid-data --max-sats 100
```

---

## Check Node Status

```bash
sz status
```

```json
{
  "status": "ok",
  "pubkey": "0234b0c302e8c201e0ffd31580bf9106b625505b...",
  "is_running": true,
  "network": "bitcoin",
  "block_height": 297000,
  "block_hash": "00000000..."
}
```

---

## Stop the Node

```bash
sz stop
```

The node will restart automatically on the next command that requires it.

---

## For AI Agent Runtimes

SaturnZap requires no interactive input. Set `SZ_PASSPHRASE` in the environment and
all commands work non-interactively.

For **MCP-compatible agents** (Claude Desktop, Cursor, VS Code), see the
[MCP Server Guide](mcp-server.md) — no CLI wrapping needed.

For **OpenClaw agents**, the `saturnzap` skill is available. See `skills/saturnzap/SKILL.md`.

---

## Pretty Output

For human-readable JSON in a terminal:

```bash
sz --pretty balance
```

Or set the environment variable:

```bash
export SZ_PRETTY=1
```

---

## Next Steps

- [Configuration Reference](configuration.md) — config file, environment variables, networks
- [MCP Server Guide](mcp-server.md) — connect AI agents via Model Context Protocol
- [JSON API Reference](json-api-reference.md) — full output shapes for all commands
- [Architecture](architecture.md) — design decisions and component overview
