"""Tests for saturnzap.payments — invoice, pay, keysend, transactions."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from saturnzap.cli import app

runner = CliRunner()


@pytest.fixture(autouse=True)
def _clean_data_dir(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))


def test_invoice_help():
    result = runner.invoke(app, ["invoice", "--help"])
    assert result.exit_code == 0
    assert "--amount-sats" in result.output
    assert "--memo" in result.output
    assert "--expiry" in result.output


def test_pay_help():
    result = runner.invoke(app, ["pay", "--help"])
    assert result.exit_code == 0
    assert "--invoice" in result.output
    assert "--max-sats" in result.output


def test_keysend_help():
    result = runner.invoke(app, ["keysend", "--help"])
    assert result.exit_code == 0
    assert "--pubkey" in result.output
    assert "--amount-sats" in result.output


def test_transactions_help():
    result = runner.invoke(app, ["transactions", "--help"])
    assert result.exit_code == 0
    assert "--limit" in result.output


def test_invoice_fails_no_seed():
    result = runner.invoke(app, ["invoice", "--amount-sats", "1000"])
    assert result.exit_code != 0


def test_pay_requires_invoice():
    result = runner.invoke(app, ["pay"])
    assert result.exit_code != 0


def test_keysend_requires_options():
    result = runner.invoke(app, ["keysend"])
    assert result.exit_code != 0


def test_transactions_fails_no_seed():
    result = runner.invoke(app, ["transactions"])
    assert result.exit_code != 0
