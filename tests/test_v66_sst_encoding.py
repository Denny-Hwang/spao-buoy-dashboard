"""Tests for the V6.6 SST encoding switch (milli-°C → centi-°C).

V6.5 and V6.6 share the 45B/49B byte layout; they differ only in how the
SST field is scaled. The decoder picks the scale either from the packet
timestamp (>= ``V6_6_DEPLOY_DATE`` → ÷100) or from an explicit
``force_version``.
"""

from utils.decoders import (
    SAMPLE_DATA,
    V6_6_DEPLOY_DATE,
    auto_detect_and_decode,
)


V65_HEX_45B = SAMPLE_DATA["FY26(v6.5) 45B"]
V66_HEX_45B = SAMPLE_DATA["FY26(v6.6) 45B"]
V66_HEX_49B = SAMPLE_DATA["FY26(v6.6)+EC 49B"]


def _sst(result: dict) -> dict:
    return next(f for f in result["fields"] if f["name"] == "SST")


def test_v66_sample_45b_decodes_to_centi_c():
    r = auto_detect_and_decode(V66_HEX_45B, force_version="FY26(v6.6)")
    assert r["crc_ok"], "V6.6 sample CRC must validate"
    assert r["version"] == "FY26(v6.6)"
    sst = _sst(r)
    assert sst["raw"] == 0x04E2 == 1250
    assert sst["value"] == 12.50


def test_v66_sample_49b_decodes_to_centi_c():
    r = auto_detect_and_decode(V66_HEX_49B, force_version="FY26(v6.6)+EC")
    assert r["crc_ok"]
    assert r["version"] == "FY26(v6.6)+EC"
    assert _sst(r)["value"] == 12.50


def test_v65_force_version_uses_milli_c():
    r = auto_detect_and_decode(V65_HEX_45B, force_version="FY26(v6.5)")
    assert r["crc_ok"]
    assert r["version"] == "FY26(v6.5)"
    sst = _sst(r)
    assert sst["raw"] == 0x30D4 == 12500
    assert sst["value"] == 12.500


def test_v64_legacy_alias_still_milli_c():
    """Older callers using the FY26(v6.4) name keep the old ÷1000 scale."""
    r = auto_detect_and_decode(V65_HEX_45B, force_version="FY26(v6.4)")
    assert r["crc_ok"]
    assert _sst(r)["value"] == 12.500


def test_auto_detect_pre_cutoff_timestamp_uses_milli_c():
    r = auto_detect_and_decode(V65_HEX_45B, packet_timestamp="2026-04-01T00:00:00Z")
    assert r["version"] == "FY26(v6.5)"
    assert _sst(r)["value"] == 12.500


def test_auto_detect_post_cutoff_timestamp_uses_centi_c():
    r = auto_detect_and_decode(V66_HEX_45B, packet_timestamp="2026-05-10T12:00:00Z")
    assert r["version"] == "FY26(v6.6)"
    assert _sst(r)["value"] == 12.50


def test_auto_detect_at_cutoff_boundary_uses_centi_c():
    r = auto_detect_and_decode(V66_HEX_45B, packet_timestamp=V6_6_DEPLOY_DATE)
    assert r["version"] == "FY26(v6.6)"
    assert _sst(r)["value"] == 12.50


def test_auto_detect_no_timestamp_defaults_to_v66():
    r = auto_detect_and_decode(V66_HEX_45B)
    assert r["version"] == "FY26(v6.6)"
    assert _sst(r)["value"] == 12.50


def test_naive_timestamp_treated_as_utc():
    """Sheets often returns naive strings — must not crash and must use UTC."""
    r = auto_detect_and_decode(V65_HEX_45B, packet_timestamp="2026-04-15 06:30:00")
    assert r["version"] == "FY26(v6.5)"
    assert _sst(r)["value"] == 12.500
