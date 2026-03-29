"""Smoke tests for the sz CLI."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    """Point data dir to a temp directory so no seed/node exists."""
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


def test_help_shows_commands():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "init" in result.output
    assert "start" in result.output
    assert "stop" in result.output
    assert "status" in result.output
    assert "address" in result.output
    assert "balance" in result.output
    assert "peers" in result.output
    assert "channels" in result.output


def test_status_fails_no_seed():
    result = runner.invoke(app, ["status"])
    assert result.exit_code != 0


def test_stop_succeeds_when_no_node():
    result = runner.invoke(app, ["stop"])
    assert result.exit_code == 0


def test_address_fails_no_seed():
    result = runner.invoke(app, ["address"])
    assert result.exit_code != 0


def test_balance_fails_no_seed():
    result = runner.invoke(app, ["balance"])
    assert result.exit_code != 0


def test_peers_help():
    result = runner.invoke(app, ["peers", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "add" in result.output
    assert "remove" in result.output


def test_channels_help():
    result = runner.invoke(app, ["channels", "--help"])
    assert result.exit_code == 0
    assert "list" in result.output
    assert "open" in result.output
    assert "close" in result.output


def test_peers_list_fails_no_seed():
    result = runner.invoke(app, ["peers", "list"])
    assert result.exit_code != 0


def test_channels_list_fails_no_seed():
    result = runner.invoke(app, ["channels", "list"])
    assert result.exit_code != 0


def test_channels_open_requires_peer_or_lsp():
    result = runner.invoke(app, ["channels", "open"])
    assert result.exit_code != 0
