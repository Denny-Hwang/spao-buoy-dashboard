# Packet Format

Telemetry packet structure for all supported SPAO buoy hardware versions.

---

## Overview

Each buoy transmits a binary packet via RockBLOCK satellite modem. The packet is hex-encoded for transport. The dashboard auto-detects the version by byte length and decodes the fields accordingly.

| Version | Bytes | Auto-detect | Description |
|---------|-------|-------------|-------------|
| FY25 | 38 | Yes | Bering Sea deployment, supercapacitor fields |
| FY26 (v3) | 37 | Yes | Early Arctic deployment, simplified prev session |
| FY26 (v5) | 43 | Yes | Extended sensor set |
| FY26 (v5) + EC | 47 | Yes | v5 + electrical conductivity & salinity |
| FY26 (v6.4) | 45 | Yes | Adds Prev Oper Time, TENG scale change (latest standard) |
| FY26 (v6.4) + EC | 49 | Yes | v6.4 + conductivity & salinity |

All packets end with a **CRC-8** checksum byte (polynomial `0x8C`, LSB-first).

---

## FY26 (v6.4) — 45 Bytes (Current Standard)

This is the most commonly used format for active deployments.

| Offset | Bytes | Field | Scale | Unit | Notes |
|--------|-------|-------|-------|------|-------|
| 0–1 | 2 | TENG Current Avg | / 100 | mA | Best 1-min sliding window |
| 2–3 | 2 | Prev 1st RB Time | / 10 | s | Previous session: 1st RockBLOCK TX time |
| 4–5 | 2 | Prev 2nd RB Time | / 10 | s | Previous session: 2nd TX time (0 if no retry) |
| 6–7 | 2 | Prev GPS Time | / 10 | s | Previous session: GPS acquisition time |
| 8–9 | 2 | Prev TENG Avg | / 100 | mA | Previous session: average TENG current |
| 10–11 | 2 | Prev TENG Max | / 100 | mA | Previous session: max TENG current |
| 12–17 | 6 | Prev TENG Time | — | — | YY, MM, DD, HH, mm, SS (1 byte each) |
| 18–19 | 2 | Prev Battery | / 1000 | V | Previous session: battery voltage |
| 20–21 | 2 | Prev End | raw | — | Previous session end code |
| 22–23 | 2 | Prev Oper Time | raw | s | Previous session: operation duration (new in v6.4) |
| 24–25 | 2 | Battery | / 1000 | V | Current battery voltage |
| 26–29 | 4 | Latitude | / 1e7 | deg | Signed 32-bit integer, decimal degrees |
| 30–33 | 4 | Longitude | / 1e7 | deg | Signed 32-bit integer, decimal degrees |
| 34–35 | 2 | GPS Time | / 10 | s | GPS acquisition time |
| 36–37 | 2 | Pressure | / 1000 | psi | Atmospheric/water pressure |
| 38–39 | 2 | Internal Temp | / 100 | C | Signed 16-bit, internal temperature |
| 40–41 | 2 | Humidity | / 10 | %RH | Relative humidity |
| 42–43 | 2 | Sea Surface Temp | / 1000 | C | Signed 16-bit, ocean temperature |
| 44 | 1 | CRC-8 | — | — | Polynomial 0x8C, LSB-first |

---

## FY26 (v6.4) + EC — 49 Bytes

Extends v6.4 with electrical conductivity and sea surface salinity.

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0–43 | 44 | *(Same as v6.4 above)* | — | — |
| 44–45 | 2 | Sea Surface Salinity | / 1000 | PSU |
| 46–47 | 2 | EC Conductivity | / 100 | mS/cm |
| 48 | 1 | CRC-8 | — | — |

---

## FY26 (v5) — 43 Bytes

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0–1 | 2 | TENG Current Avg | raw | mA |
| 2–3 | 2 | Prev 1st RB Time | / 10 | s |
| 4–5 | 2 | Prev 2nd RB Time | / 10 | s |
| 6–7 | 2 | Prev GPS Time | / 10 | s |
| 8–9 | 2 | Prev TENG Avg | raw | mA |
| 10–11 | 2 | Prev TENG Max | raw | mA |
| 12–17 | 6 | Prev TENG Time | — | YY MM DD HH mm SS |
| 18–19 | 2 | Prev Battery | / 1000 | V |
| 20–21 | 2 | Prev End | raw | — |
| 22–23 | 2 | Battery | / 1000 | V |
| 24–27 | 4 | Latitude | / 1e7 | deg |
| 28–31 | 4 | Longitude | / 1e7 | deg |
| 32–33 | 2 | GPS Time | / 10 | s |
| 34–35 | 2 | Pressure | / 1000 | psi |
| 36–37 | 2 | Internal Temp | / 100 | C |
| 38–39 | 2 | Humidity | / 10 | %RH |
| 40–41 | 2 | Sea Surface Temp | / 1000 | C |
| 42 | 1 | CRC-8 | — | — |

---

## FY26 (v5) + EC — 47 Bytes

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0–41 | 42 | *(Same as v5 above)* | — | — |
| 42–43 | 2 | Sea Surface Salinity | / 1000 | PSU |
| 44–45 | 2 | EC Conductivity | / 100 | mS/cm |
| 46 | 1 | CRC-8 | — | — |

---

## FY26 (v3) — 37 Bytes

Earlier Arctic deployment format without TENG time or extended fields.

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0–1 | 2 | TENG Current Avg | raw | mA |
| 2–3 | 2 | Prev 1st RB Time | / 10 | s |
| 4–5 | 2 | Prev 2nd RB Time | / 10 | s |
| 6–7 | 2 | Prev GPS Time | / 10 | s |
| 8–9 | 2 | Prev TENG Avg | raw | mA |
| 10–11 | 2 | Prev TENG Max | raw | mA |
| 12–13 | 2 | Prev Battery | / 1000 | V |
| 14–15 | 2 | Prev End | raw | — |
| 16–17 | 2 | Battery | / 1000 | V |
| 18–21 | 4 | Latitude | / 1e7 | deg |
| 22–25 | 4 | Longitude | / 1e7 | deg |
| 26–27 | 2 | GPS Time | / 10 | s |
| 28–29 | 2 | Pressure | / 1000 | psi |
| 30–31 | 2 | Internal Temp | / 100 | C |
| 32–33 | 2 | Humidity | / 10 | %RH |
| 34–35 | 2 | Sea Surface Temp | / 1000 | C |
| 36 | 1 | CRC-8 | — | — |

---

## FY25 — 38 Bytes

Bering Sea deployment format with supercapacitor monitoring fields.

| Offset | Bytes | Field | Scale | Unit |
|--------|-------|-------|-------|------|
| 0–1 | 2 | TENG Current | / 1000 | mA | Stored as uA |
| 2–3 | 2 | Prev 2nd RB Time | / 10 | s |
| 4–5 | 2 | Prev GPS Time | / 10 | s |
| 6–7 | 2 | Prev SCap Initial | / 1000 | V |
| 8–9 | 2 | Prev SCap 1st Charge | / 1000 | V |
| 10–11 | 2 | *(unused)* | — | — |
| 12–13 | 2 | Prev SCap After TX | / 1000 | V |
| 14 | 1 | *(unused)* | — | — |
| 15–16 | 2 | Battery | / 1000 | V |
| 17–20 | 4 | Latitude | / 1e7 | deg |
| 21–24 | 4 | Longitude | / 1e7 | deg |
| 25–26 | 2 | GPS Time | x100 / 1000 | s |
| 27–28 | 2 | Pressure | / 1000 | psi |
| 29–30 | 2 | Internal Temp | / 100 | C |
| 31–32 | 2 | Humidity | / 10 | %RH |
| 33–34 | 2 | Sea Surface Temp | / 1000 | C |
| 35–36 | 2 | Super Capacitor | / 1000 | V |
| 37 | 1 | CRC-8 | — | — |

---

## CRC-8 Validation

All packets use CRC-8 with polynomial `0x8C` (Dallas/Maxim, LSB-first processing).

```
Algorithm:
  crc = 0
  for each byte in payload (excluding CRC byte):
    extract = byte
    for 8 bits:
      if (crc XOR extract) & 0x01:
        crc = (crc >> 1) XOR 0x8C
      else:
        crc = crc >> 1
      extract >>= 1
  compare crc with last byte
```

The dashboard shows a CRC status badge (Pass / Fail) for every decoded packet.

---

## Auto-Detection Logic

The `auto_detect_and_decode()` function selects the decoder based on byte length:

```
38 bytes  →  FY25
41 bytes  →  FY25 (truncate to 38, handles RockBLOCK retry artifacts)
37 bytes  →  FY26 (v3)
43 bytes  →  FY26 (v5)
45 bytes  →  FY26 (v6.4)
47 bytes  →  FY26 (v5) + EC
49 bytes  →  FY26 (v6.4) + EC
Other     →  Error or best-effort decode with warning
```

Users can also force a specific version in the Decoder page to override auto-detection.

---

## Sample Data

These sample hex strings can be used to test the decoder:

**FY26 (v6.4) — 45 bytes:**
```
000500c8000000640000000000000000000010680000018110681c5f2f00b71a8040009939a309c401c230d48c
```

**FY26 (v6.4) + EC — 49 bytes:**
```
000500c8000000640000000000000000000010680000018110681c5f2f00b71a8040009939a309c401c230d486c414b452
```

**FY26 (v3) — 37 bytes:**
```
0002037300000272000200040f5800000f580000000000000000027239a9047c017a0a1441
```

Paste these into the Decoder page's **Single Decode** tab to verify correct parsing.
