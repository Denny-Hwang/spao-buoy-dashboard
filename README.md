# SPAO Buoy Dashboard

Streamlit web application for monitoring **SPAO (Self-Powered Arctic Ocean)** buoy telemetry. Reads satellite data from Google Sheets, decodes hex-encoded packets, and provides interactive visualization.

## Features

| Page | Description |
|------|-------------|
| **Dashboard** | Device status cards, battery levels, satellite trajectory map with latest position |
| **Live Data** | Real-time data table with date filtering, inline notes editing, CSV export |
| **Decoder** | Hex packet decoder — single input or batch CSV upload (RockBLOCK format supported) |
| **Historical** | Multi-device data browser with summary statistics and date filtering |
| **Visualization** | Drift trajectory maps and interactive sensor time-series plots, per-device filtering |

### Supported Data Formats

- **RockBLOCK CSV exports** — Raw hex payloads pasted directly into Google Sheets
- **Webhook-decoded data** — Pre-decoded rows from the Apps Script webhook

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

For Streamlit Community Cloud, add the same content under **Settings > Secrets**.

### 3. Run

```bash
streamlit run app.py
```

## Contact

Sungjoo Hwang — sungjoo.hwang@pnnl.gov

Pacific Northwest National Laboratory
