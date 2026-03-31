"""Tests for saturnzap.config — Esplora fallback resolver and config helpers."""

from unittest.mock import MagicMock, patch

import httpx

from saturnzap.config import ESPLORA_FALLBACKS, resolve_esplora


class TestResolveEsplora:
    """resolve_esplora() probe-and-fallback logic."""

    def test_config_override_skips_probing(self):
        """When user sets esplora_url in config.toml, use it directly."""
        with patch("saturnzap.config.httpx.get") as mock_get:
            result = resolve_esplora("signet", "https://my-custom.server/api")
            mock_get.assert_not_called()
            assert result == "https://my-custom.server/api"

    def test_first_healthy_url_wins(self):
        """Returns the first URL that responds HTTP 200."""
        ok = MagicMock()
        ok.status_code = 200

        with patch("saturnzap.config.httpx.get", return_value=ok) as mock_get:
            result = resolve_esplora("signet")
            assert result == ESPLORA_FALLBACKS["signet"][0]
            mock_get.assert_called_once()

    def test_skips_unhealthy_url(self):
        """If the first URL fails, tries the next."""
        bad = MagicMock()
        bad.status_code = 503
        ok = MagicMock()
        ok.status_code = 200

        with patch("saturnzap.config.httpx.get", side_effect=[bad, ok]):
            result = resolve_esplora("signet")
            assert result == ESPLORA_FALLBACKS["signet"][1]

    def test_skips_timeout(self):
        """If a URL times out, tries the next."""
        ok = MagicMock()
        ok.status_code = 200

        with patch(
            "saturnzap.config.httpx.get",
            side_effect=[httpx.ConnectTimeout("timeout"), ok],
        ):
            result = resolve_esplora("signet")
            assert result == ESPLORA_FALLBACKS["signet"][1]

    def test_all_fail_returns_first(self):
        """When every URL is unreachable, return the first one anyway."""
        with patch(
            "saturnzap.config.httpx.get",
            side_effect=httpx.ConnectError("down"),
        ):
            result = resolve_esplora("signet")
            assert result == ESPLORA_FALLBACKS["signet"][0]

    def test_unknown_network_falls_back_to_signet(self):
        """Unknown network name defaults to signet list."""
        ok = MagicMock()
        ok.status_code = 200

        with patch("saturnzap.config.httpx.get", return_value=ok):
            result = resolve_esplora("regtest")
            assert result == ESPLORA_FALLBACKS["signet"][0]

    def test_bitcoin_network_uses_mainnet_urls(self):
        """The 'bitcoin' key maps to mainnet URLs."""
        ok = MagicMock()
        ok.status_code = 200

        with patch("saturnzap.config.httpx.get", return_value=ok):
            result = resolve_esplora("bitcoin")
            assert result == ESPLORA_FALLBACKS["bitcoin"][0]


# ── data_dir / config_dir / load_config ──────────────────────────


class TestPaths:
    def test_data_dir_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        from saturnzap.config import data_dir
        d = data_dir()
        assert d.is_dir()
        assert "saturnzap" in str(d)

    def test_config_dir_creates_directory(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from saturnzap.config import config_dir
        d = config_dir()
        assert d.is_dir()
        assert "saturnzap" in str(d)


class TestLoadConfig:
    def test_load_config_defaults(self, tmp_path, monkeypatch):
        """Without a config file, defaults should be returned."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from saturnzap.config import load_config
        cfg = load_config()
        assert cfg["network"] == "signet"

    def test_load_config_from_toml(self, tmp_path, monkeypatch):
        """A valid config.toml should be loaded."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from saturnzap.config import config_path
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('[default]\nnetwork = "testnet"\n')

        from saturnzap.config import load_config
        cfg = load_config()
        assert "default" in cfg  # TOML section loaded

    def test_load_liquidity_config_defaults(self, tmp_path, monkeypatch):
        """Liquidity config should have sane defaults without a config file."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from saturnzap.config import load_liquidity_config
        cfg = load_liquidity_config()
        assert cfg["outbound_threshold_percent"] == 20
        assert cfg["inbound_threshold_percent"] == 20
        assert cfg["auto_open_enabled"] is False

    def test_load_liquidity_config_override(self, tmp_path, monkeypatch):
        """Liquidity section in TOML should override defaults."""
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        from saturnzap.config import config_path
        path = config_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("[liquidity]\noutbound_threshold_percent = 30\n")

        from saturnzap.config import load_liquidity_config
        cfg = load_liquidity_config()
        assert cfg["outbound_threshold_percent"] == 30
        assert cfg["inbound_threshold_percent"] == 20  # default preserved


# ── Network switching ────────────────────────────────────────────


class TestNetworkSwitching:
    def test_set_network_changes_get_network(self):
        import saturnzap.config as cfg
        old = cfg._active_network
        try:
            cfg.set_network("bitcoin")
            assert cfg.get_network() == "bitcoin"
            cfg.set_network("signet")
            assert cfg.get_network() == "signet"
        finally:
            cfg._active_network = old

    def test_set_network_invalid_raises(self):
        import pytest

        import saturnzap.config as cfg
        with pytest.raises(ValueError, match="Invalid network"):
            cfg.set_network("regtest")

    def test_data_dir_namespaced_by_network(self, tmp_path, monkeypatch):
        import saturnzap.config as cfg
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
        old = cfg._active_network
        try:
            cfg.set_network("signet")
            d = cfg.data_dir()
            assert d.name == "signet"
            assert d.parent.name == "saturnzap"

            cfg.set_network("bitcoin")
            d = cfg.data_dir()
            assert d.name == "bitcoin"
        finally:
            cfg._active_network = old

    def test_get_network_reads_config_toml(self, tmp_path, monkeypatch):
        import saturnzap.config as cfg
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        old = cfg._active_network
        try:
            cfg._active_network = None
            path = cfg.config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('network = "testnet"\n')
            assert cfg.get_network() == "testnet"
        finally:
            cfg._active_network = old

    def test_cli_override_beats_config(self, tmp_path, monkeypatch):
        import saturnzap.config as cfg
        monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
        old = cfg._active_network
        try:
            path = cfg.config_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('network = "testnet"\n')
            cfg.set_network("bitcoin")
            assert cfg.get_network() == "bitcoin"
        finally:
            cfg._active_network = old

    def test_valid_networks_constant(self):
        from saturnzap.config import VALID_NETWORKS
        assert "signet" in VALID_NETWORKS
        assert "testnet" in VALID_NETWORKS
        assert "bitcoin" in VALID_NETWORKS
