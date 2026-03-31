# Security Scenarios — SaturnZap

10 adversarial scenarios with attack vectors, current protections, and remaining gaps.

---

## 1. Agent Exposes Mnemonic in Chat

**Attack vector:** Agent copies the mnemonic from `sz init` output into a chat message, log file, or tool call response.

**Current protection:**
- `sz init` outputs the mnemonic exactly once in the JSON response
- SKILL.md warns: "Never expose the mnemonic"
- `output.error()` never includes the mnemonic (verified by automated test)
- Only `cli.py` init/setup emit mnemonic in `output.ok()` (verified by code scan test)

**Gap:** No programmatic way to prevent an agent from re-emitting the mnemonic. The MCP `init_wallet` and `setup_wallet` tools return the mnemonic in their response — the calling agent could log it.

**Mitigation:** Document clearly in agent-guide.md. Consider a `--no-mnemonic` flag for MCP responses in a future version.

---

## 2. Malicious L402 Server Returns Inflated Invoice

**Attack vector:** An L402 endpoint returns a 402 with a WWW-Authenticate header containing a 1M sat invoice for a request that should cost 10 sats.

**Current protection:**
- `--max-sats` spending cap on `sz fetch` and `sz pay`
- `SZ_MCP_MAX_SPEND_SATS` env var for MCP server-level cap
- Pre-flight balance check prevents payment if funds are insufficient
- `SPENDING_CAP_EXCEEDED` and `EXCEEDS_MAX_SATS` error codes returned

**Gap:** If the agent calls `sz fetch` without `--max-sats`, there is no default cap. The agent must be configured to always use spending caps.

**Mitigation:** SKILL.md strongly recommends always using `--max-sats`. Agent-guide.md lists this as an anti-pattern.

---

## 3. Compromised SZ_PASSPHRASE Env Var

**Attack vector:** Attacker reads the environment variable (e.g., via `/proc/PID/environ`, shell history, or a compromised process) and decrypts the seed file.

**Current protection:**
- PBKDF2 with 600,000 iterations makes brute-force slow (~0.1s per attempt)
- seed.enc and seed.salt have 0o600 permissions (owner-only read/write)
- Passphrase is read from env or interactive prompt (never logged to stdout)

**Gap:** If the passphrase is weak (e.g., "password"), PBKDF2 won't help against a targeted dictionary attack. No passphrase strength enforcement exists.

**Mitigation:** Document minimum passphrase requirements. Consider adding entropy check on `sz init`.

---

## 4. Two Agents Share the Same Seed File

**Attack vector:** Two processes run `sz` commands concurrently against the same data directory, causing file lock conflicts or state corruption.

**Current protection:**
- LDK Node internally manages its database locks
- The seed file is read-only after creation (no concurrent writes)

**Gap:** No explicit file locking at the SaturnZap Python level. Two `sz start` calls could race, though LDK's internal locking would likely catch this.

**Mitigation:** Document one-agent-per-directory requirement. Anti-pattern table in agent-guide.md covers this.

---

## 5. Agent Opens Channel to Malicious Node (Sybil Attack)

**Attack vector:** Attacker runs many fake Lightning nodes and tricks the agent into opening channels to them, then force-closes to steal HTLC funds or lock the agent's capital.

**Current protection:**
- LQWD LSP is the default channel partner (well-known, reputable)
- `sz channels open --lsp lqwd` routes through vetted infrastructure
- Cooperative close is the default (force-close requires `--force`)

**Gap:** Custom `--peer` allows opening channels to arbitrary nodes. No node reputation check or blacklist mechanism exists.

**Mitigation:** Recommend LQWD for all automated channel opens. Add warnings for custom peer connections in a future version.

---

## 6. MCP Server Receives Crafted Tool Call (Prompt Injection)

**Attack vector:** A compromised prompt or malicious document tricks the agent into calling MCP tools with adversarial parameters (e.g., `pay_invoice` with an attacker's invoice, or `send_onchain` to an attacker's address).

**Current protection:**
- `SZ_MCP_MAX_SPEND_SATS` caps per-payment spending via MCP
- Pre-flight balance checks prevent over-spending
- All MCP tool inputs are passed directly to LDK (no SQL, no eval, no shell)

**Gap:** No per-session spending total. An attacker could make many small payments that individually pass the cap but collectively drain the wallet.

**Mitigation:** Consider adding a session or daily spending limit in a future version.

---

## 7. Stale Token Replay on L402 Endpoints

**Attack vector:** Attacker intercepts a cached L402 token and replays it on the same endpoint to access paid content without paying.

**Current protection:**
- L402 tokens are cached locally with 0o600 permissions
- Cache filenames are SHA256 hashes (no URL leakage in filenames)
- Stale token detection: if a cached token gets 402, the cache is bypassed and a fresh payment is made

**Gap:** Tokens are stored in plain text on disk. An attacker with filesystem access can read and reuse them. L402 tokens typically don't expire (per protocol), so a stolen token is valid indefinitely.

**Mitigation:** Tokens are lower-value credentials (bounded by the original payment amount). The real risk is the seed file, not cached tokens.

---

## 8. Agent Runs `sz send` to Attacker-Controlled Address

**Attack vector:** Attacker includes a Bitcoin address in a prompt, document, or API response, and the agent sends funds to it via `sz send`.

**Current protection:**
- The agent must explicitly call `sz send` with an address and amount
- Pre-flight balance check limits the damage to current balance
- Mainnet confirmation prompt requires `--yes` or `SZ_MAINNET_CONFIRM=yes` before spending real bitcoin
- Network-namespaced data directories isolate signet and mainnet wallets

**Gap:** No address verification, allowlist, or per-session spending total. If the agent decides to send and confirms, it sends.

**Mitigation:** Use address allowlists, mandatory `--max-sats` for all sends, and per-session spending limits in a future version.

---

## 9. Disk Forensics Recovers seed.enc + salt (Offline Brute-Force)

**Attack vector:** Attacker gains access to the disk (physically or via backup), copies seed.enc and seed.salt, and brute-forces the passphrase offline.

**Current protection:**
- PBKDF2 with 600,000 iterations (~0.1s per attempt)
- Fernet encryption (AES-128-CBC + HMAC-SHA256)
- File permissions 0o600

**Gap:** 600k iterations resists casual brute-force but a dedicated attacker with GPUs could test millions of weak passphrases. No full-disk encryption requirement enforced.

**Mitigation:** Document passphrase strength requirements. Recommend full-disk encryption for production deployments. Consider Argon2id as a future upgrade to PBKDF2.

---

## 10. Supply Chain: Compromised ldk-node Wheel

**Attack vector:** The vendored `ldk_node-0.7.0-py3-none-any.whl` in `vendor/` is replaced with a malicious version that exfiltrates keys.

**Current protection:**
- Wheel is vendored locally (not downloaded from PyPI at install time)
- Git history tracks changes to the wheel file
- The wheel is built from the official LDK Node Python bindings repo

**Gap:** No checksum verification at install time. No signature verification. Anyone with repo write access could swap the wheel.

**Mitigation:** Add SHA256 checksum verification in pyproject.toml or a verification script. Pin the expected hash in CI.
