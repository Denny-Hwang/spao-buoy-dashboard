# Setup Guide

Complete instructions for setting up the SPAO Buoy Dashboard — from GCP credentials to deployment.

---

## Prerequisites

- **Python 3.9+**
- A **Google Cloud Platform** project with the Google Sheets API enabled
- A **Google Spreadsheet** containing buoy telemetry data (or the default SPAO sheet)

---

## 1. Google Cloud Service Account

The dashboard reads and writes data via the Google Sheets API. Access is authenticated through a GCP service account.

### Create the Service Account

1. Go to [Google Cloud Console](https://console.cloud.google.com/)
2. Select or create a project
3. Navigate to **APIs & Services > Library**
4. Search for and enable:
   - **Google Sheets API**
   - **Google Drive API**
5. Navigate to **APIs & Services > Credentials**
6. Click **Create Credentials > Service Account**
7. Give it a name (e.g., `spao-dashboard`) and click **Done**
8. Click on the new service account, then go to the **Keys** tab
9. Click **Add Key > Create New Key > JSON**
10. Download the JSON key file — you will need it in the next step

### Share the Spreadsheet

1. Open the target Google Spreadsheet
2. Click **Share**
3. Paste the service account's `client_email` (from the JSON key, e.g., `sa@project.iam.gserviceaccount.com`)
4. Set the role to **Editor** (required for notes editing)
5. Click **Send**

---

## 2. Configure Secrets

### Local Development

Create the file `.streamlit/secrets.toml` in the project root:

```toml
[gcp_service_account]
type = "service_account"
project_id = "your-project-id"
private_key_id = "your-key-id"
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "sa@project.iam.gserviceaccount.com"
client_id = "123456789"
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "https://www.googleapis.com/robot/v1/metadata/x509/..."
```

> Copy the values directly from your downloaded JSON key file. The field names match exactly.

> **Important:** `.streamlit/secrets.toml` is listed in `.gitignore` and must **never** be committed.

### Streamlit Community Cloud

1. Go to your app's dashboard on [streamlit.io/cloud](https://streamlit.io/cloud)
2. Click **Settings > Secrets**
3. Paste the exact same TOML content from above
4. Save — the app will restart automatically

---

## 3. Custom Spreadsheet ID (Optional)

By default, the dashboard reads from the SPAO team's shared spreadsheet. To point it to a different sheet:

1. Open `utils/sheets_client.py`
2. Change the `SHEET_ID` constant:

```python
SHEET_ID = "your-spreadsheet-id-here"
```

The spreadsheet ID is the long string in the Google Sheets URL:
```
https://docs.google.com/spreadsheets/d/<THIS_IS_THE_SHEET_ID>/edit
```

Some pages (Historical Data) also accept a sheet ID as user input at runtime.

---

## 4. Run Locally

```bash
# Install dependencies
pip install -r requirements.txt

# Start the app
streamlit run app.py
```

The app will open at `http://localhost:8501`.

### Verify Connectivity

1. Open the home page
2. Expand **System Diagnostics** at the bottom
3. Confirm:
   - `gcp_service_account secret found`
   - All packages show `OK`
   - `Google Sheets connection OK`

If the connection fails, double-check that:
- The service account email has Editor access to the spreadsheet
- The Google Sheets API is enabled in your GCP project
- The `secrets.toml` values match the JSON key file exactly

---

## 5. Deploy to Streamlit Community Cloud

1. Push your repo to GitHub (ensure `secrets.toml` is **not** committed)
2. Go to [streamlit.io/cloud](https://streamlit.io/cloud) and sign in with GitHub
3. Click **New app** and select your repository
4. Set **Main file path** to `app.py`
5. Click **Deploy**
6. After deployment, go to **Settings > Secrets** and add the service account TOML
7. The app auto-redeploys on every push to your default branch

---

## 6. Google Apps Script Webhook (Optional)

The webhook receives satellite data from RockBLOCK and writes decoded rows directly into Google Sheets. This is deployed separately from the Streamlit app.

### Deploy the Webhook

1. Open the target Google Spreadsheet
2. Go to **Extensions > Apps Script**
3. Replace the default code with the contents of `apps_script/Code.gs`
4. Click **Deploy > New deployment**
5. Select type: **Web app**
6. Set **Execute as**: Me
7. Set **Who has access**: Anyone
8. Click **Deploy** and copy the web app URL

### Configure RockBLOCK

1. Log in to the [RockBLOCK admin portal](https://rockblock.rock7.com/)
2. Navigate to your device's settings
3. Set the **Delivery URL** to the Apps Script web app URL
4. The webhook expects standard RockBLOCK POST parameters: `imei`, `data`, `transmit_time`, `momsn`

### How It Works

```
RockBLOCK satellite  →  POST to Apps Script URL
                            ↓
                     Decode hex payload (auto-detect version)
                            ↓
                     Append row to per-IMEI tab in Google Sheets
                            ↓
                     Dashboard reads it on next refresh
```

---

## Streamlit Configuration

The file `.streamlit/config.toml` controls the app's appearance and server behavior:

```toml
[server]
headless = true          # No browser auto-open (for servers)
maxUploadSize = 50       # Max upload size in MB (for batch CSV decode)

[theme]
primaryColor = "#3b82f6"
backgroundColor = "#ffffff"
secondaryBackgroundColor = "#f8fafc"
textColor = "#1a1a1a"
font = "sans serif"

[browser]
gatherUsageStats = false
```

These defaults work for most deployments. Adjust `maxUploadSize` if you need to upload larger CSV files for batch decoding.
