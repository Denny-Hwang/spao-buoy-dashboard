# SPAO Buoy Monitoring System

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Streamlit](https://img.shields.io/badge/Streamlit-FF4B4B?logo=streamlit&logoColor=white)](https://streamlit.io/)
[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)

Real-time monitoring dashboard for the Self-Powered Arctic Ocean (SPAO) buoy system, developed at Pacific Northwest National Laboratory under the DOE Water Power Technologies Office.

**Live Demo:** [https://spao-buoy-dashboard.streamlit.app/](https://spao-buoy-dashboard.streamlit.app/)

---

## Features

| Page | What it does |
|------|-------------|
| **Overview** | KPI cards (active buoys, last contact, data quality), mini map, activity feed, trajectory map |
| **Live Telemetry** | Real-time data table with battery/CRC badges, date filtering, inline notes editing, CSV export |
| **Packet Decoder** | Hex packet decoder — single input with CRC card and GPS mini-map, or batch CSV upload |
| **Archive** | Multi-device data browser with KPI summary statistics |
| **Analytics** | Drift trajectory maps with detail panel, time-series sensor plots, custom 3D scatter |

### Supported Hardware

Six telemetry packet versions are auto-detected by byte length:

| Version | Bytes | Key Difference |
|---------|-------|----------------|
| FY25 | 38 | Bering Sea deployment, supercapacitor fields |
| FY26 (v3) | 37 | Simplified previous-session fields |
| FY26 (v5) | 43 | Extended sensor set |
| FY26 (v5) + EC | 47 | Adds electrical conductivity & salinity |
| FY26 (v6.4) | 45 | Adds Prev Oper Time, TENG scale change |
| FY26 (v6.4) + EC | 49 | v6.4 + conductivity & salinity |

---

## Quick Start

### 1. Clone & Install

```bash
git clone https://github.com/Denny-Hwang/spao-buoy-dashboard.git
cd spao-buoy-dashboard
pip install -r requirements.txt
```

### 2. Set Up Google Sheets Credentials

Create `.streamlit/secrets.toml` with your GCP service account key:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "sa@project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

> **Prerequisites:** A GCP service account with the Google Sheets API enabled, and the target spreadsheet shared with the service account email as **Editor**. See [docs/setup-guide.md](docs/setup-guide.md) for step-by-step instructions.

### 3. Run

```bash
streamlit run app.py
```

The app opens at `http://localhost:8501`. Select a page from the sidebar to start.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    Streamlit App                        │
│                                                         │
│  app.py (Home)                                          │
│  pages/                                                 │
│    ├─ Overview      ── KPI cards, mini map, activity    │
│    ├─ Live Telemetry── data table, battery/CRC badges   │
│    ├─ Packet Decoder── hex decoder, GPS mini-map        │
│    ├─ Archive       ── past deployment browser          │
│    └─ Analytics     ── drift maps, sensor plots         │
│                                                         │
│  utils/                                                 │
│    ├─ theme.py         ── PNNL brand colors, UI helpers │
│    ├─ sheets_client.py ── Google Sheets read/write      │
│    ├─ decoders.py      ── packet decode (6 versions)    │
│    ├─ map_utils.py     ── Folium map builder            │
│    └─ plot_utils.py    ── Plotly chart styling           │
└──────────────────┬──────────────────────────────────────┘
                   │ Google Sheets API
                   ▼
┌──────────────────────────────────┐
│         Google Sheets            │
│  (per-IMEI tabs, auto-decoded)  │
└──────────────────┬───────────────┘
                   ▲
                   │ RockBLOCK webhook POST
┌──────────────────┴───────────────┐
│    Google Apps Script Webhook    │
│    (apps_script/Code.gs)         │
│    — receives satellite data     │
│    — decodes & appends to sheet  │
└──────────────────────────────────┘
```

**Key points:**

- **No backend server or database** — Streamlit handles both UI and logic; Google Sheets is the sole data store.
- **Data flows in two ways:** the Apps Script webhook writes decoded telemetry into Google Sheets, and the Streamlit app reads it for display and analysis.
- **Packet decoding** is duplicated in both the webhook (Apps Script) and the dashboard (Python) so data can be ingested from either raw or pre-decoded sources.
- **Caching** — Streamlit's `@st.cache_data` with TTLs (60–300s) minimizes API calls.
- **PNNL Branding** — Consistent color system based on PNNL brand standards with accessible color contrast.

For detailed architecture documentation, see the [docs/](docs/) folder.

---

## Deployment

### Streamlit Community Cloud (Recommended)

1. Push your repo to GitHub
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) and connect the repo
3. Add the GCP service account JSON under **Settings > Secrets**
4. Done — the app auto-deploys on every push to `main`

### Local / Server

```bash
pip install -r requirements.txt
streamlit run app.py --server.port 8501
```

---

## Documentation

| Document | Description |
|----------|-------------|
| [docs/setup-guide.md](docs/setup-guide.md) | Full setup — GCP credentials, Google Sheets, Apps Script webhook |
| [docs/architecture.md](docs/architecture.md) | Detailed architecture, data flow, and module reference |
| [docs/packet-format.md](docs/packet-format.md) | Telemetry packet structure for all hardware versions |
| [docs/google-sheets-format.md](docs/google-sheets-format.md) | Spreadsheet structure, supported data formats, tab naming |

---

## License

This project is licensed under the GPL-3.0 License — see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- Pacific Northwest National Laboratory
- DOE Water Power Technologies Office
- NOAA PMEL (Bering Sea deployment support)

## Contact

**Sungjoo Hwang** — sungjoo.hwang@pnnl.gov
Pacific Northwest National Laboratory
