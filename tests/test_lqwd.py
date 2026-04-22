"""Tests for saturnzap.lqwd — LQWD node directory."""

from __future__ import annotations

from unittest.mock import patch

from saturnzap import lqwd

# Geographic regions — signet fleet and the non-AI subset of mainnet.
EXPECTED_REGIONS = {"CA", "US", "BR", "GB", "IE", "FR", "DE", "IT", "SE",
                    "ZA", "BH", "IN", "SG", "HK", "ID", "KR", "JP", "AU"}

# Mainnet also includes the agent-focused AI-Grid node.
EXPECTED_MAINNET_REGIONS = EXPECTED_REGIONS | {"AI"}


def test_list_nodes_returns_all():
    nodes = lqwd.list_nodes()
    # Mainnet is the default: 18 geographic + 1 agent-focused AI-Grid node.
    assert len(nodes) == 19


def test_all_18_regions_present():
    regions = {n["region"] for n in lqwd.NODES}
    assert regions == EXPECTED_REGIONS


def test_list_nodes_filter_by_region():
    ca = lqwd.list_nodes("CA")
    assert len(ca) == 1
    assert ca[0]["region"] == "CA"


def test_list_nodes_filter_case_insensitive():
    jp = lqwd.list_nodes("jp")
    assert len(jp) == 1
    assert jp[0]["region"] == "JP"


def test_list_nodes_unknown_region():
    assert lqwd.list_nodes("XX") == []


def test_get_nearest_returns_dict():
    node = lqwd.get_nearest()
    assert "pubkey" in node
    assert "address" in node
    assert "region" in node
    assert "utc_offset" in node


def test_get_nearest_timezone_positive():
    """System at UTC+9 should pick JP or KR (offset 9)."""
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=9.0), \
         patch.dict("os.environ", {"SZ_REGION": "NEAREST"}, clear=False):
        node = lqwd.get_nearest()
    assert node["region"] in ("JP", "KR")


def test_get_nearest_timezone_negative():
    """System at UTC-5 should pick CA (offset -5)."""
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=-5.0), \
         patch.dict("os.environ", {"SZ_REGION": "NEAREST"}, clear=False):
        node = lqwd.get_nearest()
    assert node["region"] == "CA"


def test_get_nearest_timezone_zero():
    """System at UTC+0 should pick GB or IE (offset 0)."""
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=0.0), \
         patch.dict("os.environ", {"SZ_REGION": "NEAREST"}, clear=False):
        node = lqwd.get_nearest()
    assert node["region"] in ("GB", "IE")


def test_get_nearest_sz_region_override(monkeypatch):
    """SZ_REGION env var should override timezone selection."""
    monkeypatch.setenv("SZ_REGION", "AU")
    node = lqwd.get_nearest()
    assert node["region"] == "AU"


def test_get_nearest_sz_region_case_insensitive(monkeypatch):
    monkeypatch.setenv("SZ_REGION", "au")
    node = lqwd.get_nearest()
    assert node["region"] == "AU"


def test_get_nearest_sz_region_invalid_falls_through(monkeypatch):
    """Invalid SZ_REGION should fall through to the default behaviour:
    AI-Grid on mainnet (the default network), timezone selection on signet."""
    import saturnzap.config as cfg
    monkeypatch.setenv("SZ_REGION", "XX")
    old = cfg._active_network
    try:
        # Signet has no AI entry, so falls through to timezone selection.
        cfg.set_network("signet")
        with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=1.0):
            node = lqwd.get_nearest()
        assert node["region"] in ("FR", "DE", "IT", "SE")
    finally:
        cfg._active_network = old


def test_each_node_has_required_fields():
    for n in lqwd.NODES:
        assert "region" in n
        assert "alias" in n
        assert "pubkey" in n
        assert "address" in n
        assert "utc_offset" in n


# ── Mainnet node directory ───────────────────────────────────────


def test_mainnet_nodes_have_19_entries():
    # 18 geographic + 1 agent-focused AI-Grid node.
    assert len(lqwd.MAINNET_NODES) == 19


def test_mainnet_nodes_have_real_pubkeys():
    for n in lqwd.MAINNET_NODES:
        assert len(n["pubkey"]) == 66
        assert n["pubkey"] != "0" * 66


def test_mainnet_nodes_have_real_addresses():
    for n in lqwd.MAINNET_NODES:
        assert "placeholder" not in n["address"]
        assert ":" in n["address"]


def test_mainnet_all_regions():
    regions = {n["region"] for n in lqwd.MAINNET_NODES}
    assert regions == EXPECTED_MAINNET_REGIONS


def test_mainnet_has_ai_grid():
    ai = [n for n in lqwd.MAINNET_NODES if n["region"] == "AI"]
    assert len(ai) == 1
    assert ai[0]["alias"] == "LQWD-AI-Grid"
    assert ai[0]["address"].endswith(":26000")


def test_mainnet_default_prefers_ai_grid(monkeypatch):
    """On mainnet with SZ_REGION unset, get_nearest returns AI-Grid."""
    import saturnzap.config as cfg
    monkeypatch.delenv("SZ_REGION", raising=False)
    old = cfg._active_network
    try:
        cfg.set_network("bitcoin")
        node = lqwd.get_nearest()
        assert node["region"] == "AI"
        assert node["alias"] == "LQWD-AI-Grid"
    finally:
        cfg._active_network = old


def test_mainnet_nearest_opt_in_skips_ai_grid(monkeypatch):
    """SZ_REGION=NEAREST on mainnet falls back to timezone selection and skips AI."""
    import saturnzap.config as cfg
    monkeypatch.setenv("SZ_REGION", "NEAREST")
    old = cfg._active_network
    try:
        cfg.set_network("bitcoin")
        with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=9.0):
            node = lqwd.get_nearest()
        assert node["region"] != "AI"
        assert node["region"] in ("JP", "KR")
    finally:
        cfg._active_network = old


def test_mainnet_region_ai_pins_ai_grid(monkeypatch):
    """SZ_REGION=AI explicitly pins the AI-Grid node."""
    import saturnzap.config as cfg
    monkeypatch.setenv("SZ_REGION", "AI")
    old = cfg._active_network
    try:
        cfg.set_network("bitcoin")
        node = lqwd.get_nearest()
        assert node["region"] == "AI"
    finally:
        cfg._active_network = old


def test_ai_grid_in_mainnet_trusted_pubkeys():
    """AI-Grid pubkey must be included in the trusted-peer list."""
    trusted = lqwd.mainnet_trusted_pubkeys()
    ai_node = next(n for n in lqwd.MAINNET_NODES if n["region"] == "AI")
    assert ai_node["pubkey"] in trusted


def test_list_nodes_uses_mainnet_when_bitcoin():
    import saturnzap.config as cfg
    old = cfg._active_network
    try:
        cfg.set_network("bitcoin")
        nodes = lqwd.list_nodes()
        assert nodes[0]["pubkey"] != "0" * 64 + "01"
        assert len(nodes[0]["pubkey"]) == 66
    finally:
        cfg._active_network = old


def test_list_nodes_uses_mainnet_by_default():
    import saturnzap.config as cfg
    old = cfg._active_network
    try:
        cfg._active_network = None
        nodes = lqwd.list_nodes()
        # Mainnet nodes have real addresses (not placeholders)
        assert len(nodes) > 0
        assert "placeholder" not in nodes[0]["address"]
    finally:
        cfg._active_network = old
