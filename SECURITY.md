# Security Policy

## Supported Versions

SaturnZap is under active development. Security updates apply to the latest
minor release on `main`. Older versions are not patched.

| Version | Supported |
| ------- | --------- |
| 0.1.x   | ✅        |
| < 0.1   | ❌        |

## Reporting a Vulnerability

**Please do not open public GitHub issues for security vulnerabilities.**

Report security issues privately via one of the following channels:

- **GitHub Security Advisory** (preferred): open a draft advisory at
  <https://github.com/ShoneAnstey/SaturnZap/security/advisories/new>
- **Email**: security@saturnzap.dev (PGP key on request)

Include:

- A description of the issue and its impact
- Reproduction steps (minimal proof-of-concept if possible)
- Affected version or commit hash
- Your suggested remediation, if any

### What to expect

- Initial acknowledgement within **72 hours**
- Triage and severity assessment within **7 days**
- Coordinated disclosure — we will agree on a fix window and public
  disclosure date with you before publishing

### Scope

In scope:

- `src/saturnzap/` — wallet core, CLI, MCP server, IPC, keystore, payments
- Build and release tooling (`pyproject.toml`, CI workflows, vendor wheel)
- Systemd service integration (`sz service install`)
- Documented security properties in
  [docs/security-scenarios.md](docs/security-scenarios.md)

Out of scope:

- Third-party dependencies (report upstream; we track via `pip-audit`)
- LDK Node internals (report to
  [lightningdevkit/ldk-node](https://github.com/lightningdevkit/ldk-node))
- Self-inflicted key loss (forgotten passphrase, missing backups)
- Social engineering, phishing, or attacks requiring prior host compromise
- Denial of service via resource exhaustion (SaturnZap is a single-user CLI)

## Acknowledgements

We publicly credit reporters in the release notes unless you request anonymity.

## Threat Model

See [docs/security-scenarios.md](docs/security-scenarios.md) for the 10
scenarios we model, the protections in place, and the remaining gaps.
