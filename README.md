# SPAO Buoy Dashboard

Multi-page Streamlit web app for the **SPAO (Self-Powered Arctic Ocean)** buoy monitoring system. Reads decoded satellite telemetry data from Google Sheets, provides interactive visualization, standalone decoder tools, and data annotation capabilities.

**Deployment:** Streamlit Community Cloud

## Features

- **Dashboard** — Device overview, quick status, mini-map of latest positions
- **Live Data** — Real-time data table with date filtering, CSV export, and notes editing
- **Decoder Tool** — Standalone hex packet decoder supporting FY25, FY26(v3), FY26, and FY26+EC formats with single and batch decode modes
- **Historical Data** — Browse past deployment data with summary statistics
- **Visualization** — Drift trajectory maps (Folium) and interactive sensor plots (Plotly) with custom plot builder

## Setup

### 1. Clone the Repository

```bash
git clone https://github.com/Denny-Hwang/spao-buoy-dashboard.git
cd spao-buoy-dashboard
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Google Cloud Service Account Setup

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Create a new project (or select an existing one)
3. Enable the **Google Sheets API**:
   - Navigate to APIs & Services > Library
   - Search for "Google Sheets API" and enable it
4. Create a service account:
   - Go to APIs & Services > Credentials
   - Click "Create Credentials" > "Service Account"
   - Fill in the details and click "Create"
   - Skip optional steps, click "Done"
5. Create a JSON key:
   - Click on the newly created service account
   - Go to the "Keys" tab
   - Click "Add Key" > "Create new key" > JSON
   - Download and save the JSON file securely
6. Share the Google Sheet:
   - Open the Google Sheet (`1qJWka_8kDlLBRFXtUtYWLl3S026KxP3tRCmlC_N6dkU`)
   - Click "Share"
   - Add the service account email (e.g., `name@project.iam.gserviceaccount.com`) as an **Editor**

### 4. Configure Streamlit Secrets

#### Local Development

Create `.streamlit/secrets.toml`:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-private-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "your-service-account@your-project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

#### Streamlit Community Cloud

1. Deploy the app from the GitHub repo
2. Go to your app's settings in the Streamlit Cloud dashboard
3. Under "Secrets", paste the same TOML content as above

### 5. Run Locally

```bash
streamlit run app.py
```

## Project Structure

```
spao-buoy-dashboard/
├── app.py                      # Main entry point
├── pages/
│   ├── 1_📡_Dashboard.py       # Device overview
│   ├── 2_📊_Live_Data.py       # Data table + notes
│   ├── 3_🔧_Decoder.py         # Packet decoder tool
│   ├── 4_📁_Historical.py      # Historical data viewer
│   └── 5_🗺️_Visualization.py   # Maps + plots
├── utils/
│   ├── decoders.py             # Packet decoders
│   ├── sheets_client.py        # Google Sheets client
│   ├── plot_utils.py           # Plotly styling
│   └── map_utils.py            # Folium map builder
├── .streamlit/
│   └── config.toml             # Streamlit theme
├── requirements.txt
└── README.md
```

## Packet Formats

| Version   | Bytes | Description                           |
|-----------|-------|---------------------------------------|
| FY25      | 38    | First-generation buoy format          |
| FY26(v3)  | 37    | FY26 without Prev TENG Time field     |
| FY26      | 43    | Full FY26 with TENG timestamp         |
| FY26+EC   | 47    | FY26 + conductivity and salinity      |

---

SPAO Buoy Dashboard — Pacific Northwest National Laboratory · DOE Water Power Technologies Office
