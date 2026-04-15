# Configuration

SaturnZap uses three configuration sources, checked in this order:

1. **CLI `--network` flag** — highest priority (overrides everything)
2. **Environment variables**
3. **`.env` file** — loaded automatically from the working directory
4. **Config file** — `config.toml` in the OS config directory

---

## Config File

Location (Linux): `~/.config/saturnzap/config.toml`

The config file is optional. SaturnZap works with sensible defaults out of the box.

### Example `config.toml`

```toml
network = "signet"
esplora_url = "https://mempool.space/signet/api"
```

The `network` field defaults to `"bitcoin"` (mainnet) if omitted. Set it to `"signet"`
for development and testing.

### Fields

| Key | Type | Default | Description |
|---|---|---|---|
| `network` | string | `"bitcoin"` | Bitcoin network: `bitcoin`, `signet`, or `testnet` |
| `esplora_url` | string | `"https://blockstream.info/api"` | Esplora REST API endpoint. Overrides the fallback chain. |

### Liquidity Config

Liquidity thresholds are in the same file:

```toml
[liquidity]
outbound_threshold_percent = 20
inbound_threshold_percent = 20
auto_open_enabled = false
```

| Key | Type | Default | Description |
|---|---|---|---|
| `liquidity.outbound_threshold_percent` | int | `20` | Warn when outbound capacity drops below this percentage |
| `liquidity.inbound_threshold_percent` | int | `20` | Warn when inbound capacity drops below this percentage |
| `liquidity.auto_open_enabled` | bool | `false` | Auto-open channels when thresholds are breached (future) |

---

## Environment Variables

| Variable | Purpose | Default |
|---|---|---|
| `SZ_PASSPHRASE` | Decrypt the seed file. Required for all node operations. | — (prompts if unset) |
| `SZ_NETWORK` | Override the Bitcoin network (`bitcoin`, `signet`, `testnet`). Takes precedence over `config.toml` but not the CLI `--network` flag. | — (uses config or `bitcoin`) |
| `SZ_ESPLORA_URL` | Override the Esplora endpoint. Takes precedence over fallback probing but not `esplora_url` in `config.toml`. | — (auto-probe) |
| `SZ_PRETTY` | Set to `1` for pretty-printed JSON output. | `0` |
| `SZ_REGION` | Force a specific LQWD region (e.g. `JP`, `CA`, `US`). | Auto-detect from timezone |
| `SZ_MCP_MAX_SPEND_SATS` | Global per-request spending cap for MCP `l402_fetch` tool. | No limit |
| `SZ_MAINNET_CONFIRM` | Set to `yes` to skip mainnet safety confirmation prompts. | — (prompts) |
| `XDG_DATA_HOME` | Override the data directory base path. | `~/.local/share` |
| `XDG_CONFIG_HOME` | Override the config directory base path. | `~/.config` |

### `.env` File

SaturnZap loads `.env` from the current directory on startup using `python-dotenv`.
This is convenient for development and agent runtimes:

```bash
# .env
SZ_PASSPHRASE=your-secure-passphrase
SZ_PRETTY=0
SZ_REGION=CA
```

---

## Data Directory

Location (Linux): `~/.local/share/saturnzap/<network>/`

Data directories are **namespaced by network**. Each network gets its own isolated
directory with its own seed, channels, and state:

```
~/.local/share/saturnzap/
├── signet/         # Signet wallet (use --network signet)
│   ├── seed.enc
│   ├── seed.salt
│   ├── ldk/
│   └── node.active
├── bitcoin/        # Mainnet wallet (default)
│   ├── seed.enc
│   ├── seed.salt
│   ├── ldk/
│   └── node.active
└── testnet/        # Testnet wallet
    └── ...
```

Contents per network directory:

| Path | Description |
|---|---|
| `seed.enc` | AES-encrypted BIP39 mnemonic (Fernet) |
| `seed.salt` | PBKDF2 salt for key derivation |
| `ldk/` | LDK Node state (channels, peers, chain data) |
| `l402_tokens/` | Cached L402 authentication tokens |
| `node.active` | Flag file indicating the node should be running |

All files are created automatically on `sz init`.

> **Important:** Switching networks with `--network` creates a completely separate
> wallet. Your signet seed and channels are never shared with mainnet.

### Permissions

`seed.enc` and `seed.salt` are set to `0600` (owner read/write only).

### Lightning Listen Ports

Each network uses a distinct Lightning P2P listen port to avoid bind conflicts when
running multiple networks on the same host:

| Network | Port |
|---|---|
| `signet` | 9735 |
| `testnet` | 9736 |
| `bitcoin` | 9737 |

### Firewall

SaturnZap automatically opens the Lightning port in UFW when starting a daemon
(`sz start --daemon`), running `sz setup --auto`, or installing the systemd service
(`sz service install`). This is required for peers to connect to your node.

If UFW is not active or not installed, no firewall changes are made — the port is
assumed to be open.

To manually open the port:

```bash
sudo ufw allow 9737/tcp comment "SaturnZap Lightning"
```

To verify your node is reachable from the internet:

```bash
sz connect-info --check
```

This detects your external IP and probes the port from an external service. The
`"reachable"` field in the JSON output will be `true`, `false`, or `null` (if the
check service is unavailable).

---

## Esplora Fallback Chain

SaturnZap probes Esplora endpoints in order and uses the first healthy one. This
ensures the node can sync even if one provider is down.

**Default fallback order per network:**

| Network | Endpoints |
|---|---|
| `signet` | `mempool.space/signet/api` → `blockstream.info/signet/api` |
| `testnet` | `mempool.space/testnet/api` → `blockstream.info/testnet/api` |
| `bitcoin` | `blockstream.info/api` → `mempool.space/api` |

**Health check:** `GET /blocks/tip/height` with a 3-second timeout. First HTTP 200 wins.

**Config override:** If you set `esplora_url` in `config.toml`, that URL is used
unconditionally with no probing.

To use your own Esplora server:

```toml
esplora_url = "https://your-esplora.example.com/api"
```

---

## Networks

SaturnZap supports three Bitcoin networks:

| Network | Use Case | Config Value |
|---|---|---|
| **Bitcoin** | Production — mainnet (default) | `"bitcoin"` |
| **Signet** | Development and testing | `"signet"` |
| **Testnet** | Integration testing | `"testnet"` |

### Selecting a Network

Three ways to select a network (highest priority first):

1. **CLI flag:** `sz --network bitcoin status`
2. **Config file:** `network = "bitcoin"` in `config.toml`
3. **Default:** `"bitcoin"` (mainnet) if nothing is set

### Mainnet Safety

When the active network is `bitcoin`, commands that spend funds (`send`, `pay`,
`keysend`, `channels open`) display a confirmation prompt:

```
⚠ MAINNET — This will spend real bitcoin. Continue? [y/N]
```

To skip the prompt (for automation):

- Pass `--yes` / `-y` to the command
- Set `SZ_MAINNET_CONFIRM=yes` in the environment

> **Note:** The default network is `"bitcoin"` (mainnet). Use `--network signet`
> for development and testing with free test coins.

---

## Encryption Details

The BIP39 mnemonic is encrypted at rest using:

- **KDF:** PBKDF2-HMAC-SHA256, 600,000 iterations
- **Cipher:** Fernet (AES-128-CBC + HMAC-SHA256)
- **Salt:** 16 bytes, randomly generated per wallet

The passphrase is never stored on disk. It must be provided via `SZ_PASSPHRASE` or
interactive prompt on every node start.
