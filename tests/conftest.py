"""Shared test configuration."""

import os
import re

# Disable Rich/Typer ANSI colours so --help assertions match plain text.
os.environ.setdefault("NO_COLOR", "1")

_ANSI_RE = re.compile(r"\x1b\[[^m]*m")


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)
