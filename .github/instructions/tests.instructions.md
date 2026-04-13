---
applyTo: "tests/**"
description: "Use when writing, editing, or debugging SaturnZap tests. Covers fixtures, mocking patterns, CLI runner usage, and live test markers."
---

# Test Conventions

## Fixtures (autouse)

`conftest.py` provides three autouse fixtures that reset state between tests:

- `_clean_data_dir` — redirects `XDG_DATA_HOME` to `tmp_path` (no real seed touched)
- `_reset_pretty` — resets `output._pretty` to `False`
- `_reset_node` — resets `node._node` and `node._ipc_mode` singletons

New test files automatically pick these up. If a test needs the real data dir, override `_clean_data_dir` locally.

## CLI Testing

```python
from typer.testing import CliRunner
from saturnzap.cli import app

runner = CliRunner()
result = runner.invoke(app, ["balance"])
data = json.loads(result.output)
assert data["status"] == "ok"
```

## Mocking LDK Node

Use `unittest.mock.MagicMock` with `types.SimpleNamespace` for nested return values:

```python
n = MagicMock()
n.node_id.return_value = "02abc"
n.list_balances.return_value = SimpleNamespace(
    total_onchain_balance_sats=100_000,
    spendable_onchain_balance_sats=90_000,
    total_lightning_balance_sats=50_000,
    total_anchor_channels_reserve_sats=0,
)
```

Patch at the consumer: `@patch("saturnzap.node.Builder")`, not the ldk_node import.

## ANSI Stripping

`NO_COLOR=1` is set in conftest. For extra safety, use `strip_ansi()`:

```python
from tests.conftest import strip_ansi
assert "init" in strip_ansi(result.output)
```

## Markers

- `@pytest.mark.live` — requires running droplet nodes. Deselected in CI with `-m "not live"`.
- No marker needed for unit tests (default).

## Assertions

- Parse JSON output: `json.loads(result.output)` or `json.loads(capsys.readouterr().out)`
- Check error output on stderr: `json.loads(capsys.readouterr().err)`
- File permissions: `assert (path.stat().st_mode & 0o777) == 0o600`

## Don'ts

- Don't create a new `conftest.py` — extend the root one
- Don't mock at the `ldk_node` package level — mock at `saturnzap.node` or `saturnzap.cli`
- Don't skip the `_clean_data_dir` fixture unless testing real filesystem behavior
