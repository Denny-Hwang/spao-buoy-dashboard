"""
Page 3: Packet Decoder — Standalone packet decoder for SPAO telemetry.
Supports manual hex input, CSV batch decode, and RockBLOCK export format.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

from utils.decoders import auto_detect_and_decode, SAMPLE_DATA
from utils.theme import (
    render_header, render_footer, render_empty_state,
    render_sidebar, inject_custom_css,
    PNNL_BLUE, SUCCESS, DANGER,
)

st.set_page_config(page_title="Packet Decoder", page_icon="🔬", layout="wide")

inject_custom_css()
render_sidebar()
render_header()

st.markdown(
    f'<h1 style="color:{PNNL_BLUE}; margin-top:0;">Packet Decoder</h1>',
    unsafe_allow_html=True,
)

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
            placeholder="Enter hex string (e.g., 90 chars = 45B, 98 chars = 49B with EC)",
        )
        # Character counter
        if hex_input:
            hex_clean = hex_input.strip().replace(" ", "").replace("0x", "")
            char_count = len(hex_clean)
            byte_count = char_count // 2
            st.markdown(
                f'<span style="font-size:12px; color:#5A5A5A;">'
                f'{char_count} chars &middot; {byte_count} bytes</span>',
                unsafe_allow_html=True,
            )
    with col2:
        st.write("")
        st.write("")
        # Sample buttons — all versions
        sample_keys = list(SAMPLE_DATA.keys())
        sample_cols = st.columns(min(len(sample_keys), 3))
        for i, key in enumerate(sample_keys[:3]):
            with sample_cols[i]:
                short_label = key.split()[0] if " " in key else key
                if st.button(short_label, key=f"sample_{i}"):
                    hex_input = SAMPLE_DATA[key]
                    st.session_state["hex_input_val"] = hex_input

    # Additional sample buttons
    if len(sample_keys) > 3:
        extra_cols = st.columns(min(len(sample_keys) - 3, 4))
        for i, key in enumerate(sample_keys[3:]):
            with extra_cols[i]:
                if st.button(key.split()[0], key=f"sample_extra_{i}"):
                    hex_input = SAMPLE_DATA[key]
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

                # CRC validation card
                crc_ok = result["crc_ok"]
                crc_color = SUCCESS if crc_ok else DANGER
                crc_label = "Valid" if crc_ok else "FAIL"
                crc_icon = "&#10003;" if crc_ok else "&#10007;"
                with col_c:
                    st.markdown(
                        f'<div style="background:{"#E8F5E9" if crc_ok else "#FEF2F2"}; '
                        f'border:1px solid {crc_color}; border-radius:4px; padding:12px; text-align:center;">'
                        f'<div style="font-size:12px; color:#5A5A5A;">CRC Validation</div>'
                        f'<div style="font-size:24px; color:{crc_color}; font-weight:700;">'
                        f'{crc_icon} {crc_label}</div>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )

                # Results table
                if result["fields"]:
                    fields_df = pd.DataFrame(result["fields"])
                    fields_df.columns = ["Field Name", "Hex Bytes", "Raw Value", "Decoded Value", "Unit"]
                    st.dataframe(fields_df, width="stretch", hide_index=True)

                # GPS mini-map
                if result["fields"]:
                    lat_field = next((f for f in result["fields"] if "latitude" in f["name"].lower()), None)
                    lon_field = next((f for f in result["fields"] if "longitude" in f["name"].lower()), None)
                    if lat_field and lon_field:
                        lat_val = float(lat_field["value"])
                        lon_val = float(lon_field["value"])
                        if lat_val != 0 or lon_val != 0:
                            st.markdown(f'<h4 style="color:{PNNL_BLUE};">GPS Location</h4>', unsafe_allow_html=True)
                            map_df = pd.DataFrame({"lat": [lat_val], "lon": [lon_val]})
                            st.map(map_df, zoom=5)

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
            render_empty_state("Enter a hex string", "Paste a hex-encoded packet or load sample data above.")

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
            # Auto-detect hex column
            hex_col = None
            for candidate in ["Payload", "payload", "data", "Data", "hex", "Hex", "Raw Hex"]:
                if candidate in input_df.columns:
                    hex_col = candidate
                    break

            if hex_col is None:
                st.warning("Could not auto-detect hex column.")
                hex_col = st.selectbox("Select column containing hex data", input_df.columns)

            if hex_col:
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
                    st.dataframe(results_df, width="stretch", hide_index=True)

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

render_footer()
