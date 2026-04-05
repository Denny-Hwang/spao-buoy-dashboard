# SPAO Buoy Dashboard

Streamlit web application for monitoring **SPAO (Self-Powered Arctic Ocean)** buoy telemetry. Reads satellite data from Google Sheets, decodes hex-encoded packets, and provides interactive visualization tools.

## Features

| Page | Description |
|------|-------------|
| **Dashboard** | Device overview, battery status, GPS mini-map |
| **Live Data** | Real-time data table with filtering, CSV export, and notes |
| **Decoder** | Standalone hex packet decoder (single and batch mode) |
| **Historical** | Past deployment data browser with summary statistics |
| **Visualization** | Drift trajectory maps and sensor time-series plots |

### Supported Data Formats

The dashboard reads two Google Sheets formats automatically:

- **Webhook-decoded data** — Pre-decoded rows from the Apps Script webhook
- **RockBLOCK CSV exports** — Raw hex payloads pasted directly into Sheets

### Packet Versions

| Version | Bytes | Description |
|---------|-------|-------------|
| FY25 | 38 | First-generation format |
| FY26(v3) | 37 | FY26 without TENG timestamp |
| FY26 | 43 | Full FY26 with TENG timestamp |
| FY26+EC | 47 | FY26 + conductivity and salinity |

## Setup

### 1. Install

```bash
git clone https://github.com/Denny-Hwang/spao-buoy-dashboard.git
cd spao-buoy-dashboard
pip install -r requirements.txt
```

### 2. Configure Google Sheets Access

1. Create a GCP service account with **Google Sheets API** enabled
2. Share the target spreadsheet with the service account email as **Editor**
3. Create `.streamlit/secrets.toml`:

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

For Streamlit Community Cloud, paste the same content under **Settings > Secrets**.

### 3. Run

```bash
streamlit run app.py
```

## Project Structure

```
spao-buoy-dashboard/
├── app.py                        # Main entry point
├── pages/
│   ├── 1_📡_Dashboard.py
│   ├── 2_📊_Live_Data.py
│   ├── 3_🔧_Decoder.py
│   ├── 4_📁_Historical.py
│   └── 5_🗺️_Visualization.py
├── utils/
│   ├── decoders.py               # Packet decoders (FY25–FY26+EC)
│   ├── sheets_client.py          # Google Sheets I/O + format detection
│   ├── plot_utils.py             # Plotly chart helpers
│   └── map_utils.py              # Folium map builder
├── apps_script/
│   └── Code.gs                   # Webhook receiver (reference)
├── .streamlit/config.toml
├── requirements.txt
└── README.md
```

## Contact

Sungjoo Hwang — sungjoo.hwang@pnnl.gov

Pacific Northwest National Laboratory | DOE Water Power Technologies Office
