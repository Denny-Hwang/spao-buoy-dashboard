# Google Sheets Format

How the SPAO Buoy Dashboard reads and organizes data in Google Sheets.

---

## Spreadsheet Structure

The dashboard expects one Google Spreadsheet with the following tab layout:

```
Spreadsheet
├── 300434005060840    ← Device tab (IMEI number)
├── 300434007080123    ← Device tab
├── 300434009012456    ← Device tab
├── _devices           ← (Optional) Nickname mapping
├── _errors            ← (Auto-created) Webhook error log
├── Sheet1             ← (Ignored) Default sheet
└── ...
```

### Device Tabs

Each tab is named after a device's **IMEI number** and contains telemetry data. Tabs are created automatically by the Apps Script webhook when a new device reports in.

The dashboard reads **all tabs** except those matching:
- `_errors`
- `_devices`
- `Sheet1`, `Sheet2`, ... (regex: `^Sheet\d*$`)

### `_devices` Tab (Optional)

Maps device IDs to human-readable nicknames. If present, nicknames appear in device selectors throughout the app.

| Device ID | Nickname |
|-----------|----------|
| 300434005060840 | Buoy Alpha |
| 300434007080123 | Buoy Beta |

- First column: device identifier (IMEI or tab name)
- Second column: display name
- Header row is required

### `_errors` Tab

Auto-created by the Apps Script webhook to log errors. The dashboard ignores this tab.

---

## Supported Data Formats

The dashboard auto-detects four data formats based on column headers. You can mix formats across different tabs, but each tab should be consistent.

### 1. Webhook Decoded (`webhook_decoded`)

Created by the Apps Script webhook (`Code.gs`). Data arrives pre-decoded.

**Detection:** First column header is `Receive Time`

| Column | Description |
|--------|-------------|
| Receive Time | ISO timestamp when webhook received the data |
| Transmit Time | Satellite transmission timestamp |
| IMEI | Device IMEI number |
| MOMSN | Mobile-Originated Message Sequence Number |
| Raw Hex | Original hex payload |
| Packet Ver | Detected version (e.g., "FY26(v6.4)") |
| Bytes | Packet byte count |
| CRC Valid | TRUE / FALSE |
| TENG Current Avg | Decoded sensor value |
| Battery | Decoded sensor value |
| GPS Latitude | Decoded coordinate |
| GPS Longitude | Decoded coordinate |
| ... | *(remaining decoded fields)* |

The dashboard re-decodes the Raw Hex column to ensure all fields are present, then merges with any pre-decoded values.

### 2. RockBLOCK CSV Export (`rockblock_csv`)

Exported directly from the RockBLOCK admin portal.

**Detection:** First column header is `Date Time (UTC)` or `Date Time`

| Column | Description |
|--------|-------------|
| Date Time (UTC) | Transmission timestamp |
| IMEI | Device IMEI |
| MOMSN | Message sequence number |
| Payload | Hex-encoded telemetry data |
| ... | *(other RockBLOCK fields)* |

The dashboard decodes the `Payload` column automatically.

### 3. RockBLOCK Download / Webhook Errors (`rb_download`)

A variation with different column naming.

**Detection:** Has both `Raw Hex` and either `Error` or `Time` columns

| Column | Description |
|--------|-------------|
| Time | Timestamp |
| Raw Hex | Hex payload |
| Error | Error message (if any) |

### 4. Unknown / Custom (`unknown`)

For any other format, the dashboard searches for a hex column using these candidate names (in order):
- `Payload`
- `payload`
- `data`
- `Data`
- `hex`
- `Hex`
- `Raw Hex`

If found, the hex column is decoded and sensor fields are added as new columns.

---

## Adding Data Manually

You can paste data directly into Google Sheets without the webhook:

### Option A: Paste Raw RockBLOCK CSV

1. Export CSV from the RockBLOCK portal
2. Open the target tab in Google Sheets
3. Paste the CSV data (keep headers)
4. The dashboard will auto-detect the `rockblock_csv` format

### Option B: Paste Hex Payloads Only

1. Create a tab with at least one column named `Payload` (or `data`, `hex`, etc.)
2. Paste one hex string per row
3. Optionally add a `Date Time (UTC)` column for timestamps
4. The dashboard will decode each row automatically

### Option C: Use the Batch Decoder

1. Go to the **Decoder** page in the dashboard
2. Select the **Batch Decode** tab
3. Upload a CSV file containing hex payloads
4. Download the decoded results as CSV
5. Paste into Google Sheets

---

## Column Behavior

### Auto-Hidden Columns

The dashboard hides columns that are entirely empty across all rows. This keeps the UI clean when a field doesn't apply to the current hardware version (e.g., EC/salinity columns for non-EC devices).

### Column Reordering

For readability, certain columns are moved to the end of the table:
- `Raw Hex` / `Payload` (long hex strings)
- `Packet Ver`, `Bytes`, `CRC Valid` (metadata)

### Notes Column

- Present on the **Live Data** page
- Editable inline via Streamlit's data editor
- Saved back to Google Sheets when the user clicks **Save Notes**
- If the column doesn't exist in the sheet, it is created automatically

---

## Cache and Refresh

The dashboard caches data to minimize Google Sheets API calls:

| Data | TTL | Refresh Trigger |
|------|-----|-----------------|
| Tab list | 60 seconds | Refresh button or page reload |
| Device data | 120 seconds | Refresh button or page reload |
| All data (merged) | 120 seconds | Refresh button or page reload |
| Device nicknames | 300 seconds | Refresh button or page reload |

Saving notes clears **all** caches immediately to reflect changes.

The **Live Data** page has an auto-refresh toggle that reloads data every 5 minutes.

---

## Google Sheets API Limits

Be aware of [Google Sheets API quotas](https://developers.google.com/sheets/api/limits):

- **Read requests:** 300 per minute per project
- **Write requests:** 60 per minute per project

The caching strategy is designed to stay well within these limits during normal use. If multiple users access the dashboard simultaneously on Streamlit Community Cloud, consider increasing cache TTLs in `utils/sheets_client.py`.
