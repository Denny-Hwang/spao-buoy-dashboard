"""
SPAO Buoy packet decoders for FY25, FY26(v3), FY26, and FY26+EC telemetry formats.
"""

import struct
from typing import Optional


def calculate_crc8(data: bytes) -> int:
    """CRC-8 with polynomial 0x8C, LSB-first."""
    crc = 0
    for byte in data:
        extract = byte
        for _ in range(8):
            s = (crc ^ extract) & 0x01
            crc >>= 1
            if s:
                crc ^= 0x8C
            extract >>= 1
    return crc


def _field(name: str, hex_bytes: str, raw, value, unit: str) -> dict:
    return {
        "name": name,
        "hex": hex_bytes,
        "raw": raw,
        "value": value,
        "unit": unit,
    }


def _hex_slice(data: bytes, start: int, length: int) -> str:
    return data[start : start + length].hex()


def _uint16(data: bytes, offset: int) -> int:
    return struct.unpack(">H", data[offset : offset + 2])[0]


def _int16(data: bytes, offset: int) -> int:
    return struct.unpack(">h", data[offset : offset + 2])[0]


def _int32(data: bytes, offset: int) -> int:
    return struct.unpack(">i", data[offset : offset + 4])[0]


def decode_fy25(data: bytes) -> dict:
    """Decode FY25 38-byte packet.

    Previous Session layout (bytes 2-14, 13 bytes) — mirrors FY26(v3) structure:
      2-3:   Prev 1st RB Time  (uint16, ×100ms, /10→s)
      4-5:   Prev 2nd RB Time  (uint16, ×100ms, /10→s)
      6-7:   Prev GPS Time     (uint16, ×100ms, /10→s)
      8-9:   Prev TENG Current (uint16, µA, /1000→mA)
      10-11: Prev TENG Max     (uint16, µA, /1000→mA)
      12-13: Prev Battery      (uint16, mV, /1000→V)
      14:    Prev End Marker   (uint8)
    """
    fields = []

    # TENG Current Avg (0-1)
    # FY25: TENG current is stored as mA × 1000 (µA), divide to get mA
    raw = _uint16(data, 0)
    fields.append(_field("TENG Current Avg", _hex_slice(data, 0, 2), raw, round(raw / 1000.0, 3), "mA"))

    # --- Previous Session (bytes 2-14, 13 bytes) ---

    # Prev 1st RB Time (2-3) — satellite TX time for first RockBLOCK attempt
    raw = _uint16(data, 2)
    fields.append(_field("Prev 1st RB Time", _hex_slice(data, 2, 2), raw, round(raw / 10, 1), "s"))

    # Prev 2nd RB Time (4-5) — satellite TX time for second RockBLOCK attempt
    raw = _uint16(data, 4)
    fields.append(_field("Prev 2nd RB Time", _hex_slice(data, 4, 2), raw, round(raw / 10, 1), "s"))

    # Prev GPS Time (6-7) — GPS acquisition time from previous session
    raw = _uint16(data, 6)
    fields.append(_field("Prev GPS Time", _hex_slice(data, 6, 2), raw, round(raw / 10, 1), "s"))

    # Prev TENG Current (8-9) — FY25 uses µA encoding (÷1000→mA)
    raw = _uint16(data, 8)
    fields.append(_field("Prev TENG Current", _hex_slice(data, 8, 2), raw, round(raw / 1000.0, 3), "mA"))

    # Prev TENG Max (10-11) — peak TENG current, same µA encoding (÷1000→mA)
    raw = _uint16(data, 10)
    fields.append(_field("Prev TENG Max", _hex_slice(data, 10, 2), raw, round(raw / 1000.0, 3), "mA"))

    # Prev Battery (12-13) — previous session battery voltage in mV (÷1000→V)
    raw = _uint16(data, 12)
    fields.append(_field("Prev Battery", _hex_slice(data, 12, 2), raw, round(raw / 1000, 3), "V"))

    # Prev End Marker (14) — 1 byte in FY25
    raw = data[14]
    fields.append(_field("Prev End Marker", _hex_slice(data, 14, 1), raw, raw, ""))

    # --- Current Session ---

    # Battery (15-16)
    raw = _uint16(data, 15)
    fields.append(_field("Battery", _hex_slice(data, 15, 2), raw, round(raw / 1000, 3), "V"))

    # GPS Latitude (17-20)
    raw = _int32(data, 17)
    fields.append(_field("GPS Latitude", _hex_slice(data, 17, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Longitude (21-24)
    raw = _int32(data, 21)
    fields.append(_field("GPS Longitude", _hex_slice(data, 21, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Acq Time (25-26)
    raw = _uint16(data, 25)
    fields.append(_field("GPS Acq Time", _hex_slice(data, 25, 2), raw, round(raw * 100 / 1000, 1), "s"))

    # Pressure (27-28)
    raw = _uint16(data, 27)
    fields.append(_field("Pressure", _hex_slice(data, 27, 2), raw, round(raw / 1000, 3), "psi"))

    # Internal Temp (29-30)
    raw = _int16(data, 29)
    fields.append(_field("Internal Temp", _hex_slice(data, 29, 2), raw, round(raw / 100, 2), "°C"))

    # Humidity (31-32)
    raw = _uint16(data, 31)
    fields.append(_field("Humidity", _hex_slice(data, 31, 2), raw, round(raw / 10, 1), "%RH"))

    # SST (33-34)
    raw = _int16(data, 33)
    fields.append(_field("SST", _hex_slice(data, 33, 2), raw, round(raw / 1000, 3), "°C"))

    # SuperCap Voltage (35-36)
    raw = _uint16(data, 35)
    fields.append(_field("SuperCap Voltage", _hex_slice(data, 35, 2), raw, round(raw / 1000, 3), "V"))

    # CRC (37)
    crc_byte = data[37]
    crc_calc = calculate_crc8(data[:37])
    # FY25 early firmware padded CRC to 0x00, accept both
    crc_ok = (crc_byte == crc_calc) or (crc_byte == 0x00)

    return {
        "version": "FY25",
        "byte_len": 38,
        "crc_ok": crc_ok,
        "fields": fields,
    }


def decode_fy26_v3(data: bytes) -> dict:
    """Decode FY26(v3) 37-byte packet (no Prev TENG Time)."""
    fields = []

    # TENG Current Avg (0-1)
    raw = _uint16(data, 0)
    fields.append(_field("TENG Current Avg", _hex_slice(data, 0, 2), raw, raw, "mA"))

    # Prev 1st RB Time (2-3)
    raw = _uint16(data, 2)
    fields.append(_field("Prev 1st RB Time", _hex_slice(data, 2, 2), raw, round(raw / 10, 1), "s"))

    # Prev 2nd RB Time (4-5)
    raw = _uint16(data, 4)
    fields.append(_field("Prev 2nd RB Time", _hex_slice(data, 4, 2), raw, round(raw / 10, 1), "s"))

    # Prev GPS Time (6-7)
    raw = _uint16(data, 6)
    fields.append(_field("Prev GPS Time", _hex_slice(data, 6, 2), raw, round(raw / 10, 1), "s"))

    # Prev TENG Avg (8-9)
    raw = _uint16(data, 8)
    fields.append(_field("Prev TENG Avg", _hex_slice(data, 8, 2), raw, raw, "mA"))

    # Prev TENG Max (10-11)
    raw = _uint16(data, 10)
    fields.append(_field("Prev TENG Max", _hex_slice(data, 10, 2), raw, raw, "mA"))

    # Prev Battery (12-13)
    raw = _uint16(data, 12)
    fields.append(_field("Prev Battery", _hex_slice(data, 12, 2), raw, round(raw / 1000, 3), "V"))

    # Prev End Marker (14-15)
    raw = _uint16(data, 14)
    fields.append(_field("Prev End Marker", _hex_slice(data, 14, 2), raw, raw, ""))

    # Battery (16-17)
    raw = _uint16(data, 16)
    fields.append(_field("Battery", _hex_slice(data, 16, 2), raw, round(raw / 1000, 3), "V"))

    # GPS Latitude (18-21)
    raw = _int32(data, 18)
    fields.append(_field("GPS Latitude", _hex_slice(data, 18, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Longitude (22-25)
    raw = _int32(data, 22)
    fields.append(_field("GPS Longitude", _hex_slice(data, 22, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Acq Time (26-27)
    raw = _uint16(data, 26)
    fields.append(_field("GPS Acq Time", _hex_slice(data, 26, 2), raw, round(raw / 10, 1), "s"))

    # Pressure (28-29)
    raw = _uint16(data, 28)
    fields.append(_field("Pressure", _hex_slice(data, 28, 2), raw, round(raw / 1000, 3), "psi"))

    # Internal Temp (30-31)
    raw = _int16(data, 30)
    fields.append(_field("Internal Temp", _hex_slice(data, 30, 2), raw, round(raw / 100, 2), "°C"))

    # Humidity (32-33)
    raw = _uint16(data, 32)
    fields.append(_field("Humidity", _hex_slice(data, 32, 2), raw, round(raw / 10, 1), "%RH"))

    # SST (34-35)
    raw = _int16(data, 34)
    fields.append(_field("SST", _hex_slice(data, 34, 2), raw, round(raw / 1000, 3), "°C"))

    # CRC (36)
    crc_byte = data[36]
    crc_calc = calculate_crc8(data[:36])
    crc_ok = crc_byte == crc_calc

    return {
        "version": "FY26(v3)",
        "byte_len": 37,
        "crc_ok": crc_ok,
        "fields": fields,
    }


def decode_fy26(data: bytes) -> dict:
    """Decode FY26 43-byte packet (v3 + 6-byte Prev TENG Time)."""
    fields = []

    # TENG Current Avg (0-1)
    raw = _uint16(data, 0)
    fields.append(_field("TENG Current Avg", _hex_slice(data, 0, 2), raw, raw, "mA"))

    # Prev 1st RB Time (2-3)
    raw = _uint16(data, 2)
    fields.append(_field("Prev 1st RB Time", _hex_slice(data, 2, 2), raw, round(raw / 10, 1), "s"))

    # Prev 2nd RB Time (4-5)
    raw = _uint16(data, 4)
    fields.append(_field("Prev 2nd RB Time", _hex_slice(data, 4, 2), raw, round(raw / 10, 1), "s"))

    # Prev GPS Time (6-7)
    raw = _uint16(data, 6)
    fields.append(_field("Prev GPS Time", _hex_slice(data, 6, 2), raw, round(raw / 10, 1), "s"))

    # Prev TENG Avg (8-9)
    raw = _uint16(data, 8)
    fields.append(_field("Prev TENG Avg", _hex_slice(data, 8, 2), raw, raw, "mA"))

    # Prev TENG Max (10-11)
    raw = _uint16(data, 10)
    fields.append(_field("Prev TENG Max", _hex_slice(data, 10, 2), raw, raw, "mA"))

    # Prev TENG Time (12-17) — YY,MM,DD,HH,mm,SS
    ts_bytes = data[12:18]
    ts_str = f"20{ts_bytes[0]:02d}-{ts_bytes[1]:02d}-{ts_bytes[2]:02d} {ts_bytes[3]:02d}:{ts_bytes[4]:02d}:{ts_bytes[5]:02d}"
    fields.append(_field("Prev TENG Time", _hex_slice(data, 12, 6), list(ts_bytes), ts_str, ""))

    # Prev Battery (18-19)
    raw = _uint16(data, 18)
    fields.append(_field("Prev Battery", _hex_slice(data, 18, 2), raw, round(raw / 1000, 3), "V"))

    # Prev End Marker (20-21)
    raw = _uint16(data, 20)
    fields.append(_field("Prev End Marker", _hex_slice(data, 20, 2), raw, raw, ""))

    # Battery (22-23)
    raw = _uint16(data, 22)
    fields.append(_field("Battery", _hex_slice(data, 22, 2), raw, round(raw / 1000, 3), "V"))

    # GPS Latitude (24-27)
    raw = _int32(data, 24)
    fields.append(_field("GPS Latitude", _hex_slice(data, 24, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Longitude (28-31)
    raw = _int32(data, 28)
    fields.append(_field("GPS Longitude", _hex_slice(data, 28, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Acq Time (32-33)
    raw = _uint16(data, 32)
    fields.append(_field("GPS Acq Time", _hex_slice(data, 32, 2), raw, round(raw / 10, 1), "s"))

    # Pressure (34-35)
    raw = _uint16(data, 34)
    fields.append(_field("Pressure", _hex_slice(data, 34, 2), raw, round(raw / 1000, 3), "psi"))

    # Internal Temp (36-37)
    raw = _int16(data, 36)
    fields.append(_field("Internal Temp", _hex_slice(data, 36, 2), raw, round(raw / 100, 2), "°C"))

    # Humidity (38-39)
    raw = _uint16(data, 38)
    fields.append(_field("Humidity", _hex_slice(data, 38, 2), raw, round(raw / 10, 1), "%RH"))

    # SST (40-41)
    raw = _int16(data, 40)
    fields.append(_field("SST", _hex_slice(data, 40, 2), raw, round(raw / 1000, 3), "°C"))

    # CRC (42)
    crc_byte = data[42]
    crc_calc = calculate_crc8(data[:42])
    crc_ok = crc_byte == crc_calc

    return {
        "version": "FY26",
        "byte_len": 43,
        "crc_ok": crc_ok,
        "fields": fields,
    }


def decode_fy26_ec(data: bytes) -> dict:
    """Decode FY26+EC 47-byte packet (FY26 43-byte + conductivity/salinity)."""
    # Decode the first 42 bytes as FY26 (without CRC)
    result = decode_fy26(data[:43])
    # Remove the CRC check from the FY26 decode (it checked byte 42 which is now EC data)
    # Re-decode properly

    fields = []

    # TENG Current Avg (0-1)
    raw = _uint16(data, 0)
    fields.append(_field("TENG Current Avg", _hex_slice(data, 0, 2), raw, raw, "mA"))

    # Prev 1st RB Time (2-3)
    raw = _uint16(data, 2)
    fields.append(_field("Prev 1st RB Time", _hex_slice(data, 2, 2), raw, round(raw / 10, 1), "s"))

    # Prev 2nd RB Time (4-5)
    raw = _uint16(data, 4)
    fields.append(_field("Prev 2nd RB Time", _hex_slice(data, 4, 2), raw, round(raw / 10, 1), "s"))

    # Prev GPS Time (6-7)
    raw = _uint16(data, 6)
    fields.append(_field("Prev GPS Time", _hex_slice(data, 6, 2), raw, round(raw / 10, 1), "s"))

    # Prev TENG Avg (8-9)
    raw = _uint16(data, 8)
    fields.append(_field("Prev TENG Avg", _hex_slice(data, 8, 2), raw, raw, "mA"))

    # Prev TENG Max (10-11)
    raw = _uint16(data, 10)
    fields.append(_field("Prev TENG Max", _hex_slice(data, 10, 2), raw, raw, "mA"))

    # Prev TENG Time (12-17)
    ts_bytes = data[12:18]
    ts_str = f"20{ts_bytes[0]:02d}-{ts_bytes[1]:02d}-{ts_bytes[2]:02d} {ts_bytes[3]:02d}:{ts_bytes[4]:02d}:{ts_bytes[5]:02d}"
    fields.append(_field("Prev TENG Time", _hex_slice(data, 12, 6), list(ts_bytes), ts_str, ""))

    # Prev Battery (18-19)
    raw = _uint16(data, 18)
    fields.append(_field("Prev Battery", _hex_slice(data, 18, 2), raw, round(raw / 1000, 3), "V"))

    # Prev End Marker (20-21)
    raw = _uint16(data, 20)
    fields.append(_field("Prev End Marker", _hex_slice(data, 20, 2), raw, raw, ""))

    # Battery (22-23)
    raw = _uint16(data, 22)
    fields.append(_field("Battery", _hex_slice(data, 22, 2), raw, round(raw / 1000, 3), "V"))

    # GPS Latitude (24-27)
    raw = _int32(data, 24)
    fields.append(_field("GPS Latitude", _hex_slice(data, 24, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Longitude (28-31)
    raw = _int32(data, 28)
    fields.append(_field("GPS Longitude", _hex_slice(data, 28, 4), raw, round(raw / 1e7, 7), "°"))

    # GPS Acq Time (32-33)
    raw = _uint16(data, 32)
    fields.append(_field("GPS Acq Time", _hex_slice(data, 32, 2), raw, round(raw / 10, 1), "s"))

    # Pressure (34-35)
    raw = _uint16(data, 34)
    fields.append(_field("Pressure", _hex_slice(data, 34, 2), raw, round(raw / 1000, 3), "psi"))

    # Internal Temp (36-37)
    raw = _int16(data, 36)
    fields.append(_field("Internal Temp", _hex_slice(data, 36, 2), raw, round(raw / 100, 2), "°C"))

    # Humidity (38-39)
    raw = _uint16(data, 38)
    fields.append(_field("Humidity", _hex_slice(data, 38, 2), raw, round(raw / 10, 1), "%RH"))

    # SST (40-41)
    raw = _int16(data, 40)
    fields.append(_field("SST", _hex_slice(data, 40, 2), raw, round(raw / 1000, 3), "°C"))

    # EC Conductivity (42-43)
    raw = _uint16(data, 42)
    fields.append(_field("EC Conductivity", _hex_slice(data, 42, 2), raw, round(raw / 100, 2), "mS/cm"))

    # Salinity (44-45)
    raw = _uint16(data, 44)
    fields.append(_field("Salinity", _hex_slice(data, 44, 2), raw, round(raw / 1000, 3), "PSS-78"))

    # CRC (46)
    crc_byte = data[46]
    crc_calc = calculate_crc8(data[:46])
    crc_ok = crc_byte == crc_calc

    return {
        "version": "FY26+EC",
        "byte_len": 47,
        "crc_ok": crc_ok,
        "fields": fields,
    }


def auto_detect_and_decode(hex_string: str, force_version: Optional[str] = None) -> dict:
    """
    Decode a hex-encoded telemetry packet.

    Args:
        hex_string: Hex-encoded packet data (whitespace/0x prefix stripped automatically).
        force_version: If set, force a specific decoder version instead of auto-detecting.

    Returns:
        Dict with version, byte_len, crc_ok, and fields list.
    """
    hex_clean = hex_string.strip().replace(" ", "").replace("0x", "").replace("0X", "")

    if len(hex_clean) % 2 != 0:
        return {"error": f"Odd number of hex characters ({len(hex_clean)})", "version": None, "byte_len": 0, "crc_ok": False, "fields": []}

    try:
        data = bytes.fromhex(hex_clean)
    except ValueError as e:
        return {"error": f"Invalid hex string: {e}", "version": None, "byte_len": 0, "crc_ok": False, "fields": []}

    byte_len = len(data)

    if force_version:
        version_map = {
            "FY25": (38, decode_fy25),
            "FY26(v3)": (37, decode_fy26_v3),
            "FY26": (43, decode_fy26),
            "FY26+EC": (47, decode_fy26_ec),
        }
        if force_version not in version_map:
            return {"error": f"Unknown version: {force_version}", "version": None, "byte_len": byte_len, "crc_ok": False, "fields": []}
        expected_len, decoder = version_map[force_version]
        if byte_len == 41 and force_version == "FY25":
            data = data[:38]
            byte_len = 38
        if byte_len != expected_len:
            return {"error": f"Expected {expected_len} bytes for {force_version}, got {byte_len}", "version": force_version, "byte_len": byte_len, "crc_ok": False, "fields": []}
        return decoder(data)

    # Auto-detect by length
    if byte_len == 38:
        return decode_fy25(data)
    elif byte_len == 41:
        # Retry artifact — decode first 38 as FY25
        return decode_fy25(data[:38])
    elif byte_len == 37:
        return decode_fy26_v3(data)
    elif byte_len == 43:
        return decode_fy26(data)
    elif byte_len == 47:
        return decode_fy26_ec(data)
    else:
        return {
            "error": f"Unknown packet length: {byte_len} bytes. Expected 37, 38, 41, 43, or 47.",
            "version": None,
            "byte_len": byte_len,
            "crc_ok": False,
            "fields": [],
        }


# Sample data for testing
SAMPLE_DATA = {
    "FY26(v3)": "0002037300000272000200040f5800000f580000000000000000027239a9047c017a0a1441",
    "FY25": "000200000000000000000000000000" + "0f58" + "00000000" + "00000000" + "0000" + "39a9" + "047c" + "017a" + "0a14" + "0000" + "00",
}
