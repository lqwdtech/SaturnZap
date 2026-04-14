# MCP Server

SaturnZap includes a built-in [Model Context Protocol](https://modelcontextprotocol.io/)
(MCP) server that exposes its full functionality as tools for AI agents. Any
MCP-compatible client — Claude Desktop, Cursor, VS Code, or custom agents — can connect
and manage a Lightning wallet directly.

---

## How It Works

The MCP server runs locally over **stdio** (standard input/output). No network ports,
no HTTP, no authentication tokens. The agent process spawns `sz mcp` as a child process
and communicates via JSON-RPC over stdin/stdout.

On startup, the server automatically:

1. Loads the encrypted seed using `SZ_PASSPHRASE`
2. Starts the LDK Lightning node
3. Syncs wallet state via Esplora
4. Exposes 20 tools for the agent to call

On shutdown, the node is stopped gracefully.

---

## Setup

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "saturnzap": {
      "command": "sz",
      "args": ["mcp"],
      "env": {
        "SZ_PASSPHRASE": "your-passphrase"
      }
    }
  }
}
```

### Cursor

Add to Cursor's MCP settings:

```json
{
  "mcpServers": {
    "saturnzap": {
      "command": "sz",
      "args": ["mcp"],
      "env": {
        "SZ_PASSPHRASE": "your-passphrase"
      }
    }
  }
}
```

### VS Code (GitHub Copilot)

Add to `.vscode/mcp.json` in your workspace:

```json
{
  "servers": {
    "saturnzap": {
      "command": "sz",
      "args": ["mcp"],
      "env": {
        "SZ_PASSPHRASE": "your-passphrase"
      }
    }
  }
}
```

### Custom / Programmatic

Use the standalone entry point:

```bash
sz-mcp
```

Or from Python:

```python
from saturnzap.mcp_server import serve
serve()  # blocks, communicates over stdio
```

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `SZ_PASSPHRASE` | **Required.** Decrypts the seed file. | — |
| `SZ_MCP_MAX_SPEND_SATS` | Global per-request spending cap for `l402_fetch`. | No limit |
| `SZ_PRETTY` | Set to `1` for pretty-printed JSON (rarely needed for MCP). | `0` |
| `SZ_REGION` | Force a specific LQWD region (e.g. `JP`, `CA`). | Auto-detect |

---

## Tool Reference

### Lifecycle

| Tool | Description |
|---|---|
| `is_initialized` | Check if the wallet has been initialized. |
| `init_wallet` | Generate a new BIP39 seed and start the node. Call once only. |
| `get_status` | Node pubkey, sync state, block height, timestamps. |
| `get_connect_info` | Connection URI (`pubkey@host:port`) for sharing with other wallets. |
| `stop_node` | Stop the Lightning node gracefully. |

### Wallet

| Tool | Description |
|---|---|
| `new_onchain_address` | Generate a new on-chain receive address. |
| `get_balance` | On-chain + Lightning balances with per-channel breakdown. |

### Peers

| Tool | Parameters | Description |
|---|---|---|
| `connect_peer` | `node_id`, `address` | Connect to a Lightning peer. |
| `disconnect_peer` | `node_id` | Disconnect a peer. |
| `list_peers` | — | List all connected/persisted peers. |

### Channels

| Tool | Parameters | Description |
|---|---|---|
| `list_channels` | — | List all channels with capacity info. |
| `open_channel` | `node_id`, `address`, `amount_sats`, `announce` | Open a channel. |
| `close_channel` | `channel_id`, `counterparty_node_id`, `force` | Close a channel. |

### Payments

| Tool | Parameters | Description |
|---|---|---|
| `create_invoice` | `amount_sats`, `memo`, `expiry_secs` | Create a BOLT11 invoice. `amount_sats=0` for variable amount. |
| `pay_invoice` | `invoice`, `max_sats` | Pay a BOLT11 invoice with optional spending cap. |
| `keysend` | `pubkey`, `amount_sats` | Send a spontaneous payment. |
| `list_transactions` | `limit` | List recent payment history. |

### L402

| Tool | Parameters | Description |
|---|---|---|
| `l402_fetch` | `url`, `method`, `body`, `max_sats` | Fetch a URL with L402 auto-pay. If HTTP 402, pays invoice and retries. |

### Liquidity

| Tool | Parameters | Description |
|---|---|---|
| `liquidity_status` | — | Channel health scores and recommendations. |
| `request_inbound` | `amount_sats`, `region` | Request inbound liquidity from LQWD. |
| `list_lqwd_nodes` | `region` | List available LQWD nodes (18 regions). |

---

## Spending Controls

### Per-request caps

The `pay_invoice` and `l402_fetch` tools accept a `max_sats` parameter. If the invoice
amount exceeds this cap, the payment is rejected.

### Global cap

Set `SZ_MCP_MAX_SPEND_SATS` to enforce a maximum on all `l402_fetch` calls. This acts
as a safety net — the agent cannot overspend on any single L402 request even if the
agent doesn't pass `max_sats` explicitly.

```json
{
  "mcpServers": {
    "saturnzap": {
      "command": "sz",
      "args": ["mcp"],
      "env": {
        "SZ_PASSPHRASE": "your-passphrase",
        "SZ_MCP_MAX_SPEND_SATS": "1000"
      }
    }
  }
}
```

---

## Security Model

- **Local only** — stdio transport, no network listener, no open ports.
- **Non-custodial** — keys never leave the machine.
- **Passphrase in env** — the seed passphrase is passed via `SZ_PASSPHRASE`, never
  through MCP tool parameters. The `init_wallet` tool returns the mnemonic once; it is
  never exposed again after initialization.
- **No shell access** — the MCP server only exposes defined tool functions. There is no
  `exec` or arbitrary command execution.

---

## Troubleshooting

### "Wallet not initialized"

Run `sz init` first (or call the `init_wallet` MCP tool) to generate a seed.

### "Incorrect passphrase"

Ensure `SZ_PASSPHRASE` matches the passphrase used during `sz init`.

### Node won't sync

Check that Esplora endpoints are reachable. SaturnZap probes mempool.space and
blockstream.info automatically. See [Configuration](configuration.md) for custom
Esplora URLs.

### Tools not appearing

Ensure `sz mcp` is in your PATH. Test with:

```bash
echo '{"jsonrpc":"2.0","method":"tools/list","id":1}' | sz mcp
```
