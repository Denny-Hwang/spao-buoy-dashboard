"""
Page 3: Decoder Tool — Standalone packet decoder for SPAO telemetry.
"""

import streamlit as st
import pandas as pd
from io import BytesIO

from utils.decoders import auto_detect_and_decode, SAMPLE_DATA

st.set_page_config(page_title="Decoder", page_icon="🔧", layout="wide")
st.title("🔧 Packet Decoder")

VERSIONS = ["Auto-detect", "FY25", "FY26(v3)", "FY26", "FY26+EC"]

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
            placeholder="Enter hex-encoded packet data...",
        )
    with col2:
        st.write("")
        st.write("")
        sample_key = list(SAMPLE_DATA.keys())[0]
        if st.button("Load Sample"):
            hex_input = SAMPLE_DATA[sample_key]
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
                        # Show hex dump with offset
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
    st.markdown("Upload a CSV file with a `data` or `hex` column containing hex-encoded packets.")

    uploaded = st.file_uploader("Upload CSV", type=["csv"])
    if uploaded:
        try:
            input_df = pd.read_csv(uploaded)
        except Exception as e:
            st.error(f"Failed to read CSV: {e}")
            input_df = None

        if input_df is not None:
            # Find hex column
            hex_col = None
            for candidate in ["data", "hex", "Data", "Hex", "payload", "Payload"]:
                if candidate in input_df.columns:
                    hex_col = candidate
                    break

            if hex_col is None:
                st.error("CSV must contain a column named 'data' or 'hex'.")
            else:
                st.write(f"Found {len(input_df)} rows with hex column: `{hex_col}`")

                if st.button("Decode All", type="primary"):
                    results = []
                    progress = st.progress(0)
                    for i, row in input_df.iterrows():
                        hex_str = str(row[hex_col])
                        result = auto_detect_and_decode(hex_str, force_version=force_version)

                        row_data = {"Row": i + 1, "Version": result.get("version", ""), "CRC": result.get("crc_ok", False)}
                        if "error" in result and result["error"]:
                            row_data["Error"] = result["error"]
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
st.caption("SPAO Buoy Dashboard — Pacific Northwest National Laboratory · DOE Water Power Technologies Office")
