"""
Page 3: Decoder Tool — Standalone packet decoder for SPAO telemetry.
Supports manual hex input, CSV batch decode, and RockBLOCK export format.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

from utils.decoders import auto_detect_and_decode, SAMPLE_DATA

st.set_page_config(page_title="Decoder", page_icon="🔧", layout="wide")
st.title("🔧 Packet Decoder")

VERSIONS = ["Auto-detect", "FY26(v6.4)+EC", "FY26(v6.4)", "FY26(v5)+EC", "FY26(v5)", "FY26(v3)", "FY25"]

# Version selector
version = st.selectbox("Decoder Version", VERSIONS)
force_version = None if version == "Auto-detect" else version

# Mode tabs
tab_single, tab_batch = st.tabs(["Single Decode", "Batch Decode"])

with tab_single:
    col1, col2 = st.columns([3, 1])
    with col1:
        hex_input = st.text_input(
            "Hex String",
            placeholder="Enter hex string (90 chars = 45B without EC, 98 chars = 49B with EC)",
        )
    with col2:
        st.write("")
        st.write("")
        btn_col1, btn_col2 = st.columns(2)
        with btn_col1:
            if st.button("45B Sample"):
                hex_input = SAMPLE_DATA["FY26(v6.4) 45B"]
                st.session_state["hex_input_val"] = hex_input
        with btn_col2:
            if st.button("49B Sample"):
                hex_input = SAMPLE_DATA["FY26(v6.4)+EC 49B"]
                st.session_state["hex_input_val"] = hex_input

    # Use session state for sample loading
    if "hex_input_val" in st.session_state and not hex_input:
        hex_input = st.session_state.pop("hex_input_val")

    if st.button("Decode", type="primary") or hex_input:
        if hex_input:
            result = auto_detect_and_decode(hex_input, force_version=force_version)

            if "error" in result and result["error"]:
                st.error(result["error"])
            else:
                if result.get("warning"):
                    st.warning(result["warning"])

                # Header info
                col_a, col_b, col_c = st.columns(3)
                col_a.metric("Version", result["version"])
                col_b.metric("Bytes", result["byte_len"])
                if result["crc_ok"]:
                    col_c.success("CRC: PASS")
                else:
                    col_c.error("CRC: FAIL")

                # Results table
                if result["fields"]:
                    fields_df = pd.DataFrame(result["fields"])
                    fields_df.columns = ["Field Name", "Hex Bytes", "Raw Value", "Decoded Value", "Unit"]
                    st.dataframe(fields_df, use_container_width=True, hide_index=True)

                # Raw binary dump
                with st.expander("Raw Binary Dump"):
                    hex_clean = hex_input.strip().replace(" ", "").replace("0x", "")
                    try:
                        raw_bytes = bytes.fromhex(hex_clean)
                        lines = []
                        for offset in range(0, len(raw_bytes), 16):
                            chunk = raw_bytes[offset : offset + 16]
                            hex_part = " ".join(f"{b:02x}" for b in chunk)
                            ascii_part = "".join(chr(b) if 32 <= b < 127 else "." for b in chunk)
                            lines.append(f"{offset:04x}  {hex_part:<48s}  {ascii_part}")
                        st.code("\n".join(lines))
                    except Exception:
                        st.code(hex_input)
        else:
            st.info("Enter a hex string or load sample data.")

with tab_batch:
    st.markdown(
        "Upload a CSV file with hex-encoded packets. "
        "Supported formats: RockBLOCK CSV (`Payload`), RB download (`Raw Hex`), or custom CSV (`data`/`hex`)."
    )

    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        try:
            input_df = pd.read_csv(uploaded)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
            input_df = None

        if input_df is not None:
            # Auto-detect hex column — support RockBLOCK format and custom formats
            hex_col = None
            for candidate in ["Payload", "payload", "data", "Data", "hex", "Hex", "Raw Hex"]:
                if candidate in input_df.columns:
                    hex_col = candidate
                    break

            if hex_col is None:
                # Let user pick the column
                st.warning("Could not auto-detect hex column.")
                hex_col = st.selectbox("Select column containing hex data", input_df.columns)

            if hex_col:
                # Detect format for metadata extraction
                cols = set(input_df.columns)
                is_rockblock_csv = "Device" in cols or "Date Time (UTC)" in cols
                is_rb_download = "IMEI" in cols and "Time" in cols

                fmt_label = ""
                if is_rockblock_csv:
                    fmt_label = " (RockBLOCK CSV format)"
                elif is_rb_download:
                    fmt_label = " (RB download format)"

                st.write(f"Found **{len(input_df)}** rows — hex column: `{hex_col}`{fmt_label}")

                if st.button("Decode All", type="primary"):
                    results = []
                    progress = st.progress(0)
                    for i, row in input_df.iterrows():
                        hex_str = str(row[hex_col])
                        result = auto_detect_and_decode(hex_str, force_version=force_version)

                        row_data = {
                            "Row": i + 1,
                            "Version": result.get("version", ""),
                            "CRC": result.get("crc_ok", False),
                        }

                        # Include metadata based on detected format
                        if is_rockblock_csv:
                            row_data["Timestamp"] = row.get("Date Time (UTC)", row.get("Date Time", ""))
                            row_data["Device"] = row.get("Device", "")
                        elif is_rb_download:
                            row_data["Timestamp"] = row.get("Time", "")
                            row_data["Device"] = row.get("IMEI", "")
                            row_data["MOMSN"] = row.get("MOMSN", "")

                        if "error" in result and result["error"]:
                            row_data["Error"] = result["error"]
                        if result.get("warning"):
                            row_data["Warning"] = result["warning"]
                        for field in result.get("fields", []):
                            row_data[field["name"]] = field["value"]
                        results.append(row_data)
                        progress.progress((i + 1) / len(input_df))

                    results_df = pd.DataFrame(results)
                    st.dataframe(results_df, use_container_width=True, hide_index=True)

                    # Download
                    csv_buf = BytesIO()
                    results_df.to_csv(csv_buf, index=False)
                    st.download_button(
                        "Download Decoded CSV",
                        data=csv_buf.getvalue(),
                        file_name="decoded_results.csv",
                        mime="text/csv",
                    )

# Sample data reference
with st.expander("Sample Hex Strings"):
    for ver, hex_str in SAMPLE_DATA.items():
        st.code(f"{ver}: {hex_str}")

st.divider()
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory")
