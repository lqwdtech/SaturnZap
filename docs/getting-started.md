# Getting Started

This guide walks you through installing SaturnZap, initializing your Lightning node,
funding it, and making your first payment.

---

## TL;DR — One-Click Install

For an experienced operator on Ubuntu 22.04+:

```bash
# 1. Install uv (skip if you already have it)
curl -LsSf https://astral.sh/uv/install.sh | sh
source $HOME/.local/bin/env

# 2. Install SaturnZap globally (pulls the vendored ldk-node wheel from GitHub Releases)
uv tool install saturnzap \
  --find-links https://github.com/lqwdtech/SaturnZap/releases/latest/download/

# 3. Set a strong passphrase (encrypts the seed at rest)
export SZ_PASSPHRASE="your-secure-passphrase"

# 4. Generate seed, start node, pick nearest LQWD peer, open firewall port
sz setup --auto

# 5. Keep the node running across reboots
sz service install

# 6. Share this URI with peers or LSPs
sz connect-info --check
```

Back up the 24-word mnemonic printed by step 4. It is the only recovery path.

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
git clone https://github.com/lqwdtech/SaturnZap.git
cd SaturnZap
uv venv
source .venv/bin/activate
uv sync

# Verify
sz --version
sz --help
```

### From PyPI

```bash
# ldk-node is not yet on PyPI — use --find-links for the vendored wheel
pip install saturnzap \
  --find-links https://github.com/lqwdtech/SaturnZap/releases/latest/download/

# Or with uv
uv pip install saturnzap \
  --find-links https://github.com/lqwdtech/SaturnZap/releases/latest/download/
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
- Peers with **LQWD-AI-Grid** on mainnet — the agent-focused LSP node that supports
  LSPS1 and LSPS2 (JIT channels) and auto-opens a channel back on first contact, so
  the wallet starts receiving inbound liquidity without requiring on-chain funds first.
  Override with `SZ_REGION=NEAREST` to use the geographic fleet, or `SZ_REGION=<code>`
  (e.g. `JP`, `CA`) to pin a region.
- Attempts to open an outbound channel to LQWD (skipped if the wallet is unfunded —
  you'll see `{"step": "inbound", "skipped": true, "reason": "wallet unfunded..."}`
  rather than an error)

> **Important:** Back up your 24-word mnemonic from the output. It is the only way
> to recover your funds if the seed file is lost.

### 2a. (Recommended) Persist the node via systemd

```bash
sz service install
```

This installs a user systemd unit that keeps the node running across reboots.
Every subsequent `sz` command routes through the daemon's IPC socket — no
per-command startup cost. Skip this step if you're just experimenting.

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

> **Minimum channel size:** LQWD nodes require at least **2,000,000 sats** per channel.
> If the amount is too low, `sz` returns a `CHANNEL_REJECTED` error with the peer's
> reason (e.g. "below min chan size"). Other Lightning nodes may have different minimums.

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

### 6. Make a payment

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

### 7. Fetch an L402 resource

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

SaturnZap is designed for non-interactive use. Set `SZ_PASSPHRASE` in the environment
and all read and setup commands run without prompts.

On **mainnet**, spending commands (`send`, `pay`, `keysend`, `channels open`) show a
confirmation prompt. Pass `--yes` or set `SZ_MAINNET_CONFIRM=yes` in the environment
to skip it. Signet and testnet never prompt.

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

### Handy Follow-Up Commands

```bash
# Manage config without hand-editing TOML
sz config list
sz config set node.alias "my-agent-node"

# Manage trusted peers (anchor-reserve waiver + 0-conf)
sz peers trusted-list            # LQWD fleet is trusted on mainnet by default
sz peers trust <pubkey>

# Purpose-built init preset for the LQWDClaw faucet
sz init --for-lqwd-faucet        # Mainnet only
```
