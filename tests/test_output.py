"""Tests for saturnzap.output — JSON envelope helpers."""

from __future__ import annotations

import json

import pytest

from saturnzap import output


@pytest.fixture(autouse=True)
def _reset_pretty():
    """Ensure pretty mode is off between tests."""
    output.set_pretty(False)
    yield
    output.set_pretty(False)


def test_ok_writes_json_to_stdout(capsys):
    output.ok(foo="bar", num=42)
    captured = capsys.readouterr()
    data = json.loads(captured.out)
    assert data["status"] == "ok"
    assert data["foo"] == "bar"
    assert data["num"] == 42


def test_ok_compact_by_default(capsys):
    output.ok(a=1)
    captured = capsys.readouterr()
    assert "\n" not in captured.out.strip()
    assert "  " not in captured.out  # no indentation


def test_ok_pretty(capsys):
    output.set_pretty(True)
    output.ok(a=1)
    captured = capsys.readouterr()
    assert "  " in captured.out  # indented


def test_error_writes_to_stderr(capsys):
    with pytest.raises(SystemExit) as exc_info:
        output.error("TEST_ERR", "something broke")
    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    data = json.loads(captured.err)
    assert data["status"] == "error"
    assert data["code"] == "TEST_ERR"
    assert data["message"] == "something broke"


def test_error_custom_exit_code(capsys):
    with pytest.raises(SystemExit) as exc_info:
        output.error("CUSTOM", "msg", exit_code=42)
    assert exc_info.value.code == 42
