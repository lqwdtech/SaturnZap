"""Shared test configuration."""

import os
import re

import pytest

from saturnzap import config as _cfg

# Disable Rich/Typer ANSI colours so --help assertions match plain text.
os.environ.setdefault("NO_COLOR", "1")

_ANSI_RE = re.compile(r"\x1b\[[^m]*m")


def strip_ansi(text: str) -> str:
    """Remove all ANSI escape sequences from *text*."""
    return _ANSI_RE.sub("", text)


@pytest.fixture(autouse=True)
def _reset_active_network():
    """Reset config._active_network between tests to avoid ordering leaks."""
    _cfg._active_network = None  # noqa: SLF001
    yield
    _cfg._active_network = None  # noqa: SLF001
