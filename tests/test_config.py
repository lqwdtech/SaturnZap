"""Tests for saturnzap.config — Esplora fallback resolver."""

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
