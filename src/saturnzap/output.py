"""JSON output helpers for sz CLI.

Every command writes structured JSON to stdout.  Errors go to stderr.
Pass ``--pretty`` (or set ``SZ_PRETTY=1``) for indented, human-friendly output.
"""

from __future__ import annotations

import json
import sys
from typing import Any

_pretty: bool = False


def set_pretty(value: bool) -> None:
    """Enable or disable pretty-printed JSON output."""
    global _pretty  # noqa: PLW0603
    _pretty = value


def _is_tty() -> bool:
    return hasattr(sys.stdout, "isatty") and sys.stdout.isatty()


def _dump(data: dict[str, Any]) -> str:
    if _pretty:
        return json.dumps(data, indent=2, default=str)
    return json.dumps(data, separators=(",", ":"), default=str)


def ok(**fields: Any) -> None:
    """Write a success JSON envelope to stdout and exit 0."""
    payload = {"status": "ok", **fields}
    sys.stdout.write(_dump(payload) + "\n")
    sys.stdout.flush()


def error(code: str, message: str, *, exit_code: int = 1) -> None:
    """Write an error JSON envelope to stderr and exit with *exit_code*."""
    payload = {"status": "error", "code": code, "message": message}
    sys.stderr.write(_dump(payload) + "\n")
    sys.stderr.flush()
    raise SystemExit(exit_code)
