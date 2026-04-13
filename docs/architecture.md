# Architecture

Detailed technical architecture of the SPAO Buoy Dashboard.

---

## System Overview

The SPAO Buoy Dashboard is a **single-framework Streamlit application** with no separate backend, database, or container infrastructure. Google Sheets serves as the sole data store.

```
                 ┌──────────────────────┐
                 │  RockBLOCK Satellite  │
                 └──────────┬───────────┘
                            │ HTTP POST (imei, hex data)
                            ▼
                 ┌──────────────────────┐
                 │  Google Apps Script   │
                 │  Webhook (Code.gs)    │
                 │  — decode packet      │
                 │  — append to sheet    │
                 └──────────┬───────────┘
                            │ Write
                            ▼
               ┌────────────────────────────┐
               │       Google Sheets        │
               │                            │
               │  Tab per IMEI:             │
               │  ┌──────┐ ┌──────┐        │
               │  │300434│ │300434│ ...     │
               │  │005060│ │007080│         │
               │  └──────┘ └──────┘        │
               │                            │
               │  Special tabs:             │
               │  _devices (nickname map)   │
               │  _errors  (webhook logs)   │
               └────────────┬───────────────┘
                            │ Read / Write (via API)
                            ▼
┌───────────────────────────────────────────────────────────┐
│                    Streamlit App                          │
│                                                          │
│  ┌─────────┐  ┌───────────────────────────────────────┐  │
│  │ app.py  │  │  pages/                               │  │
│  │ (Home)  │  │  ├─ 1_Dashboard.py                    │  │
│  └─────────┘  │  ├─ 2_Live_Data.py                    │  │
│               │  ├─ 3_Decoder.py                      │  │
│               │  ├─ 4_Historical.py                   │  │
│               │  └─ 5_Visualization.py                │  │
│               └───────────────────────────────────────┘  │
│                            │                              │
│               ┌────────────┴────────────┐                │
│               ▼            ▼            ▼                │
│  ┌──────────────┐ ┌────────────┐ ┌────────────┐         │
│  │sheets_client │ │ decoders   │ │ map_utils  │         │
│  │  .py         │ │  .py       │ │ plot_utils │         │
│  │              │ │            │ │  .py       │         │
│  │ read/write   │ │ 6 versions │ │ Folium +   │         │
│  │ Google Sheets│ │ auto-detect│ │ Plotly     │         │
│  └──────────────┘ └────────────┘ └────────────┘         │
└───────────────────────────────────────────────────────────┘
```

---

## Data Flow

### Reading (Dashboard, Live Data, Historical, Visualization)

```
User opens page
  → list_device_tabs(sheet_id)           # Get tab names (cached 60s)
  → For each tab:
      get_device_data(tab_name)           # Cached 120s
        → worksheet.get_all_records()
        → detect_sheet_format(headers)    # rockblock_csv | webhook_decoded | ...
        → normalize_sheet_data(records)
            → For each row with hex payload:
                auto_detect_and_decode()  # Byte-length detection → version decoder
            → Return DataFrame with decoded sensor columns
  → Concatenate all tabs, add "Device Tab" column
  → Apply user filters (device, date range)
  → Render UI (tables, maps, charts)
```

### Writing (Live Data — Notes)

```
User edits "Notes" cell in data editor
  → Click "Save Notes"
  → Detect changed rows by comparing with original
  → update_note(tab, sheet_row, note_text)
      → Find "Notes" column index in sheet
      → worksheet.update_cell(row, col, text)
  → Clear all caches
  → st.rerun()
```

---

## Module Reference

### `app.py` — Home Page

Entry point and system diagnostics. Renders the welcome page and checks:
- Service account secret availability
- Package installation status
- Google Sheets connectivity

### `utils/sheets_client.py` — Data Access Layer

All Google Sheets interaction goes through this module.

| Function | Description |
|----------|-------------|
| `get_client()` | Returns a cached `gspread` client authenticated via `st.secrets` |
| `list_device_tabs(sheet_id)` | Lists worksheet names, excluding `_errors`, `_devices`, `Sheet1` etc. |
| `get_device_data(tab, sheet_id)` | Reads one worksheet, detects format, decodes hex, returns DataFrame |
| `get_all_data(sheet_id)` | Merges all device tabs into a single DataFrame |
| `detect_sheet_format(headers)` | Identifies data format from column headers |
| `normalize_sheet_data(records, fmt)` | Normalizes any format to a standard DataFrame with decoded fields |
| `update_note(tab, row, text, sheet_id)` | Writes a note to a specific cell in the Notes column |
| `get_device_nicknames(sheet_id)` | Reads optional `_devices` tab for IMEI → nickname mapping |
| `reorder_columns(df)` | Moves hex/metadata columns to the end for readability |

**Format detection** supports four source types:
- `rockblock_csv` — Raw RockBLOCK CSV exports (header starts with "Date Time (UTC)")
- `webhook_decoded` — Pre-decoded rows from Apps Script (header starts with "Receive Time")
- `rb_download` — RockBLOCK download format with "Raw Hex" column
- `unknown` — Auto-detects hex column from candidates: Payload, data, hex, Raw Hex

**Caching strategy:**
- `list_device_tabs`: 60s TTL
- `get_device_data`: 120s TTL
- `get_all_data`: 120s TTL
- `get_device_nicknames`: 300s TTL
- All caches are invalidated when notes are saved

### `utils/decoders.py` — Packet Decoding

Decodes hex-encoded telemetry packets for six SPAO hardware versions.

| Function | Version | Bytes |
|----------|---------|-------|
| `decode_fy25(data)` | FY25 | 38 |
| `decode_fy26_v3(data)` | FY26 (v3) | 37 |
| `decode_fy26(data)` | FY26 (v5) | 43 |
| `decode_fy26_ec(data)` | FY26 (v5) + EC | 47 |
| `decode_v64(data)` | FY26 (v6.4) | 45 |
| `decode_v64_ec(data)` | FY26 (v6.4) + EC | 49 |
| `auto_detect_and_decode(hex, force)` | Auto-detect by byte length |
| `calculate_crc8(data)` | CRC-8 validation (polynomial 0x8C) |

Each decoder returns a dict of `{name, hex, raw, value, unit}` per field, plus metadata (version, byte count, CRC status).

See [packet-format.md](packet-format.md) for full packet structures.

### `utils/map_utils.py` — Map Builder

Builds Folium maps for drift trajectory visualization.

| Function | Description |
|----------|-------------|
| `build_drift_map(df, basemap, ...)` | Full trajectory map with per-device colored lines, markers, popups |
| `interpolate_gps_zeros(df, lat, lon)` | Fills (0, 0) GPS readings by linear interpolation from neighbors |

**Basemap options:** Satellite (Esri), Terrain (Esri), Dark (CartoDB), Street (OSM)

**Map features:**
- Per-device colored trajectory lines
- Circle markers at each data point (smaller for interpolated points)
- Star marker at latest position
- Clickable popups with full sensor details
- Layer control for toggling device tracks
- Auto-zoom with padding

### `utils/plot_utils.py` — Chart Styling

Plotly chart helpers with consistent styling.

| Function | Description |
|----------|-------------|
| `apply_plot_style(fig, ...)` | Apply standardized layout to any Plotly figure |
| `make_time_series(df, x, y, ...)` | Time-series line chart with per-device coloring |
| `make_scatter(df, x, y, ...)` | 2D scatter plot with optional trendline |
| `make_3d_scatter(df, x, y, z, ...)` | 3D scatter visualization |

**Color palette:** 10 Tailwind CSS colors, cycled for multi-device plots.

---

## Page Details

### Dashboard (`pages/1_📡_Dashboard.py`)
- Multi-device selector with date range filter
- Per-device status cards: message count, latest battery, latest GPS
- Freshness indicator (time since last data)
- Full trajectory map via `map_utils.build_drift_map()`

### Live Data (`pages/2_📊_Live_Data.py`)
- Single-device selector
- Auto-refresh toggle (5-minute intervals)
- Editable data table (Notes column only)
- Save notes back to Google Sheets
- CSV export download
- Auto-hides empty columns

### Decoder (`pages/3_🔧_Decoder.py`)
- **Single Decode tab:** Paste hex string, see field-by-field breakdown and hex dump
- **Batch Decode tab:** Upload CSV, auto-detect hex column, decode all rows with progress bar
- Version auto-detection or manual override
- Sample data buttons for quick testing

### Historical (`pages/4_📁_Historical.py`)
- Optional external spreadsheet ID input
- Multi-device browser with summary statistics (record count, battery min/max/avg)
- Date range filter and CSV export

### Visualization (`pages/5_🗺️_Visualization.py`)
- **Drift Map tab:** Interactive trajectory map with basemap selector
- **Sensor Plots tab:** Auto-generated time-series for battery, SST, pressure, humidity, TENG, etc.
- **Custom Plot tab:** User-selectable axes, optional 3D scatter, optional trendline

---

## Technology Stack

| Component | Technology |
|-----------|-----------|
| Web framework | Streamlit >= 1.30.0 |
| Data processing | pandas >= 2.0.0, numpy >= 1.24.0 |
| Charts | Plotly >= 5.18.0 |
| Maps | Folium >= 0.15.0, streamlit-folium >= 0.15.0 |
| Google Sheets | gspread >= 5.12.0, google-auth >= 2.25.0 |
| Excel export | openpyxl >= 3.1.0 |

---

## Design Decisions

1. **Google Sheets as database** — Chosen for simplicity and collaboration. The team can view/edit data directly in Sheets, and no database infrastructure is needed.

2. **Dual decoding** — Packets are decoded both in Apps Script (at ingestion) and in Python (at display). This allows the dashboard to work with raw hex data from any source, not just pre-decoded webhook data.

3. **No backend API** — Streamlit handles both UI rendering and data processing. This keeps the stack simple and eliminates the need for a separate server.

4. **TTL caching** — `@st.cache_data` with short TTLs (60–300s) balances freshness with API rate limits. Users can force-refresh with the refresh button.
