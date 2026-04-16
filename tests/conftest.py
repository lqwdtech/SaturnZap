"""Shared test configuration."""

import os
import re

import pytest

from saturnzap import config as _cfg

# Disable Rich/Typer ANSI colours so --help assertions match plain text.
os.environ.setdefault("NO_COLOR", "1")
# Many tests use short passphrases like "pw" / "testpass". Bypass the
# production minimum-length check for them. Real users never set this.
os.environ.setdefault("SZ_ALLOW_WEAK_PASSPHRASE", "1")

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


@pytest.fixture(autouse=True)
def _reset_module_singletons():
    """Reset node / output / ipc module-level state between tests.

    Prevents a mocked `_node` or stray `_ipc_mode` / `_pretty` flag from one
    test leaking into the next.
    """
    from saturnzap import node as _node
    from saturnzap import output as _output

    _node._node = None  # noqa: SLF001
    _node._ipc_mode = False  # noqa: SLF001
    _output._pretty = False  # noqa: SLF001
    yield
    _node._node = None  # noqa: SLF001
    _node._ipc_mode = False  # noqa: SLF001
    _output._pretty = False  # noqa: SLF001
