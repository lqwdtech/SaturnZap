---
description: "Scaffold a new sz CLI command with IPC routing, JSON output, mainnet safety, and test skeleton"
agent: "agent"
argument-hint: "Command name and description, e.g. 'export - export wallet data as JSON backup'"
tools: [read, edit, search, execute]
---

Add a new `sz` CLI command to SaturnZap. Follow the existing patterns exactly.

## Requirements from user

{{input}}

## Steps

### 1. Add the CLI command in `src/saturnzap/cli.py`

Follow this pattern:

```python
@app.command()
def command_name(
    # Options as Annotated[type, typer.Option(...)]
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Skip mainnet confirmation.")] = False,
) -> None:
    """One-line docstring."""
    _confirm_mainnet(yes)  # Only if the command spends funds
    # Implementation here
    output.ok(field1="value1", field2="value2")
```

### 2. Add node.py function with IPC routing (if needed)

If the command needs LDK Node access, add a function in `src/saturnzap/node.py`:

```python
def new_function(**params) -> ReturnType:
    if _use_ipc():
        return _ipc("new_function", **params)
    node = _require_node()
    # LDK Node calls here
    return result
```

### 3. Register IPC method (if IPC routing added)

Add the method to `build_dispatcher()` in `src/saturnzap/ipc.py`.

### 4. Add MCP tool (if appropriate)

Add a tool function in `src/saturnzap/mcp_server.py` following the existing pattern.

### 5. Add tests in `tests/test_cli.py`

```python
def test_command_name(mock_node):
    with patch("saturnzap.node._node", mock_node):
        result = runner.invoke(app, ["command-name"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["status"] == "ok"
```

### 6. Document the JSON response shape

Add the response shape to `docs/json-api-reference.md`.

### 7. Verify

Run `uv sync && uv run ruff check src/ tests/ && uv run pytest tests/ -v`.
