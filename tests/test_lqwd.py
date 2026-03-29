"""Tests for saturnzap.lqwd — LQWD node directory."""

from __future__ import annotations

from unittest.mock import patch

from saturnzap import lqwd

EXPECTED_REGIONS = {"CA", "US", "BR", "GB", "IE", "FR", "DE", "IT", "SE",
                    "ZA", "BH", "IN", "SG", "HK", "ID", "KR", "JP", "AU"}


def test_list_nodes_returns_all():
    nodes = lqwd.list_nodes()
    assert len(nodes) == 18


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
         patch.dict("os.environ", {}, clear=False):
        # remove SZ_REGION if set
        import os
        os.environ.pop("SZ_REGION", None)
        node = lqwd.get_nearest()
    assert node["region"] in ("JP", "KR")


def test_get_nearest_timezone_negative():
    """System at UTC-5 should pick CA (offset -5)."""
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=-5.0), \
         patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("SZ_REGION", None)
        node = lqwd.get_nearest()
    assert node["region"] == "CA"


def test_get_nearest_timezone_zero():
    """System at UTC+0 should pick GB or IE (offset 0)."""
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=0.0), \
         patch.dict("os.environ", {}, clear=False):
        import os
        os.environ.pop("SZ_REGION", None)
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
    """Invalid SZ_REGION should fall through to timezone selection."""
    monkeypatch.setenv("SZ_REGION", "XX")
    with patch("saturnzap.lqwd._system_utc_offset_hours", return_value=1.0):
        node = lqwd.get_nearest()
    # Should get a European node at UTC+1
    assert node["region"] in ("FR", "DE", "IT", "SE")


def test_each_node_has_required_fields():
    for n in lqwd.NODES:
        assert "region" in n
        assert "alias" in n
        assert "pubkey" in n
        assert "address" in n
        assert "utc_offset" in n
