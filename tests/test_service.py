"""Tests for saturnzap.service — systemd service generator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from saturnzap import service


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Clean env vars that affect unit generation."""
    monkeypatch.delenv("SZ_REGION", raising=False)
    monkeypatch.delenv("SZ_ESPLORA_URL", raising=False)
    monkeypatch.delenv("SZ_MCP_MAX_SPEND_SATS", raising=False)


# ── generate_unit ────────────────────────────────────────────────


def test_generate_unit_contains_exec_start(monkeypatch):
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")
    content = service.generate_unit()
    assert "ExecStart=" in content
    assert "start" in content


def test_generate_unit_contains_restart():
    content = service.generate_unit()
    assert "Restart=on-failure" in content
    assert "RestartSec=10" in content


def test_generate_unit_does_not_embed_passphrase(monkeypatch):
    """Unit file must never contain the passphrase."""
    monkeypatch.setenv("SZ_PASSPHRASE", "secret123")
    content = service.generate_unit()
    assert "secret123" not in content
    assert "SZ_PASSPHRASE=" not in content
    # Must reference the EnvironmentFile instead
    assert "EnvironmentFile=" in content


def test_render_env_file_includes_passphrase():
    content = service._render_env_file("secret123")
    assert "SZ_PASSPHRASE=secret123" in content


def test_render_env_file_includes_extra_env(monkeypatch):
    monkeypatch.setenv("SZ_REGION", "CA")
    monkeypatch.setenv("SZ_ESPLORA_URL", "https://esplora.test")
    content = service._render_env_file("pw")
    assert "SZ_REGION=CA" in content
    assert "SZ_ESPLORA_URL=https://esplora.test" in content


def test_generate_unit_is_valid_ini():
    """Unit file should have [Unit], [Service], [Install] sections."""
    content = service.generate_unit()
    assert "[Unit]" in content
    assert "[Service]" in content
    assert "[Install]" in content


def test_generate_unit_sets_user(monkeypatch):
    monkeypatch.setenv("USER", "testuser")
    content = service.generate_unit()
    assert "User=testuser" in content


# ── install ──────────────────────────────────────────────────────


def test_install_calls_systemctl(monkeypatch, tmp_path):
    monkeypatch.setenv("SZ_PASSPHRASE", "pw")
    mock_unit_path = tmp_path / "saturnzap.service"
    mock_env_dir = tmp_path / "etc"
    mock_env_path = mock_env_dir / "saturnzap.env"

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch.object(service, "_ENV_DIR", mock_env_dir),
        patch.object(service, "_ENV_PATH", mock_env_path),
        patch("subprocess.run") as mock_run,
        patch("saturnzap.node.open_firewall_port", return_value="not_linux"),
    ):
        result = service.install()

    assert mock_unit_path.exists()
    assert result["unit_name"] == "saturnzap.service"
    # Should call daemon-reload, enable, start
    assert mock_run.call_count == 3
    calls = [c.args[0] for c in mock_run.call_args_list]
    assert ["systemctl", "daemon-reload"] in calls
    assert ["systemctl", "enable", "saturnzap.service"] in calls
    assert ["systemctl", "start", "saturnzap.service"] in calls


def test_install_writes_env_file_with_0600(monkeypatch, tmp_path):
    """The EnvironmentFile must be 0o600 (owner-only) — passphrase is secret."""
    monkeypatch.setenv("SZ_PASSPHRASE", "secret")
    mock_unit_path = tmp_path / "saturnzap.service"
    mock_env_dir = tmp_path / "etc"
    mock_env_path = mock_env_dir / "saturnzap.env"

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch.object(service, "_ENV_DIR", mock_env_dir),
        patch.object(service, "_ENV_PATH", mock_env_path),
        patch("subprocess.run"),
        patch("saturnzap.node.open_firewall_port", return_value="not_linux"),
    ):
        service.install()

    assert mock_env_path.exists()
    assert oct(mock_env_path.stat().st_mode)[-3:] == "600"
    # Env file contains the passphrase
    assert "SZ_PASSPHRASE=secret" in mock_env_path.read_text()
    # Unit file does NOT contain the passphrase
    assert "secret" not in mock_unit_path.read_text()


# ── uninstall ────────────────────────────────────────────────────


def test_uninstall_removes_unit(tmp_path):
    mock_unit_path = tmp_path / "saturnzap.service"
    mock_unit_path.write_text("[Unit]\n")
    mock_env_path = tmp_path / "saturnzap.env"
    mock_env_path.write_text("SZ_PASSPHRASE=pw\n")

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch.object(service, "_ENV_PATH", mock_env_path),
        patch("subprocess.run") as mock_run,
    ):
        result = service.uninstall()

    assert not mock_unit_path.exists()
    assert not mock_env_path.exists()
    assert result["message"] == "Service removed."
    # stop, disable, daemon-reload
    assert mock_run.call_count == 3


def test_uninstall_missing_unit(tmp_path):
    """uninstall should not crash if unit file doesn't exist."""
    mock_unit_path = tmp_path / "saturnzap.service"

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch("subprocess.run"),
    ):
        result = service.uninstall()

    assert result["unit_name"] == "saturnzap.service"


# ── status ───────────────────────────────────────────────────────


def test_status_active_enabled(tmp_path):
    mock_unit_path = tmp_path / "saturnzap.service"
    mock_unit_path.write_text("[Unit]\n")

    active_result = MagicMock(stdout="active\n")
    enabled_result = MagicMock(stdout="enabled\n")

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch("subprocess.run", side_effect=[active_result, enabled_result]),
    ):
        result = service.status()

    assert result["is_active"] is True
    assert result["is_enabled"] is True
    assert result["installed"] is True


def test_status_inactive(tmp_path):
    mock_unit_path = tmp_path / "saturnzap.service"

    inactive_result = MagicMock(stdout="inactive\n")
    disabled_result = MagicMock(stdout="disabled\n")

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch("subprocess.run", side_effect=[inactive_result, disabled_result]),
    ):
        result = service.status()

    assert result["is_active"] is False
    assert result["is_enabled"] is False
    assert result["installed"] is False


# ── generate_unit — new fields ───────────────────────────────────


def test_generate_unit_contains_exec_start_pre(monkeypatch):
    monkeypatch.setenv("SZ_PASSPHRASE", "testpass")
    content = service.generate_unit()
    assert "ExecStartPre=" in content
    assert "seed.enc" in content


def test_generate_unit_contains_environment_file():
    """Unit file must reference EnvironmentFile — not inline passphrase."""
    content = service.generate_unit()
    assert "EnvironmentFile=" in content
    assert "/etc/saturnzap/" in content


def test_generate_unit_contains_mainnet_confirm():
    content = service.generate_unit()
    assert "SZ_MAINNET_CONFIRM=yes" in content


def test_generate_unit_contains_journal_output():
    content = service.generate_unit()
    assert "StandardOutput=journal" in content
    assert "StandardError=journal" in content


# ── install — passphrase validation ──────────────────────────────


def test_install_requires_passphrase(monkeypatch, tmp_path):
    """install() should error when SZ_PASSPHRASE is empty."""
    monkeypatch.delenv("SZ_PASSPHRASE", raising=False)
    mock_unit_path = tmp_path / "saturnzap.service"

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        pytest.raises(SystemExit),
    ):
        service.install()


def test_install_includes_firewall(monkeypatch, tmp_path):
    monkeypatch.setenv("SZ_PASSPHRASE", "pw")
    mock_unit_path = tmp_path / "saturnzap.service"
    mock_env_dir = tmp_path / "etc"
    mock_env_path = mock_env_dir / "saturnzap.env"

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch.object(service, "_ENV_DIR", mock_env_dir),
        patch.object(service, "_ENV_PATH", mock_env_path),
        patch("subprocess.run") as mock_run,
        patch("saturnzap.node.open_firewall_port", return_value="opened"),
    ):
        result = service.install()

    assert result["firewall"] == "opened"
    assert mock_run.call_count == 3


# ── status — port fields ────────────────────────────────────────


def test_status_includes_port(tmp_path):
    mock_unit_path = tmp_path / "saturnzap.service"

    active_result = MagicMock(stdout="active\n")
    enabled_result = MagicMock(stdout="enabled\n")

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch("subprocess.run", side_effect=[active_result, enabled_result]),
        patch("saturnzap.service._is_port_listening", return_value=True),
    ):
        result = service.status()

    assert "port" in result
    assert result["port_listening"] is True


def test_status_port_not_listening(tmp_path):
    mock_unit_path = tmp_path / "saturnzap.service"

    active_result = MagicMock(stdout="inactive\n")
    enabled_result = MagicMock(stdout="disabled\n")

    with (
        patch.object(service, "_UNIT_PATH", mock_unit_path),
        patch("subprocess.run", side_effect=[active_result, enabled_result]),
        patch("saturnzap.service._is_port_listening", return_value=False),
    ):
        result = service.status()

    assert result["port_listening"] is False


# ── _is_port_listening ───────────────────────────────────────────


def test_is_port_listening_false():
    """Port that's not listening should return False."""
    # Use a random high port that's almost certainly not in use
    assert service._is_port_listening(59123) is False
