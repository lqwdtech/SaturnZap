"""Shared test configuration."""

import os

# Disable Rich/Typer ANSI colours so --help assertions match plain text.
os.environ.setdefault("NO_COLOR", "1")
