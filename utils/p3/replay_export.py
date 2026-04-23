"""Build CSV / Excel payloads for Field Replay downloads.

The Field-Replay page exports the selected (device, time-range) slice
enriched with the Phase 3 ``IRI_*`` / ``GPS_*`` columns. We offer two
formats:

* **CSV** — single flat file, one row per TX.
* **Excel** — three sheets: the flat ``events`` sheet, then
  ``sat_visibility_iri`` and ``sat_visibility_gps`` long-format tables
  with one row per (TX, visible sat) pair. Useful for downstream
  analysis in Excel / pandas / MATLAB.

Both exporters share the same enrichment pass so the downloaded
numbers exactly match what the UI showed.
"""

from __future__ import annotations

import io
from datetime import datetime, timezone
from typing import Sequence

import pandas as pd

from utils.p3 import gps_geometry as _gps
from utils.p3 import tz as _tz
from utils.p3.sgp4_engine import Sat, look_angles
from utils.p3.tx_join import (
    ColumnMap,
    P3_COLUMNS,
    enrich_phase1_frame,
    resolve_columns,
)

IRI_MIN_EL_DEG = 8.2
_TIME_COLS_DEFAULT = ("Timestamp",)


def _ensure_time_col_exists(df: pd.DataFrame, cols: ColumnMap) -> pd.DataFrame:
    """Return a copy where the resolved time column is standard ``Timestamp``.

    Keeps downstream TZ formatting consistent when the source used
    e.g. ``Date Time`` or ``DateTime``.
    """
    if cols.time is None or cols.time == "Timestamp":
        return df
    out = df.copy()
    out["Timestamp"] = pd.to_datetime(out[cols.time], errors="coerce", utc=True)
    return out


def build_events_csv(df_enriched: pd.DataFrame,
                     tz_name: str | None = None) -> bytes:
    """Return UTF-8 CSV bytes for the events sheet (UTC + local columns)."""
    if df_enriched is None or df_enriched.empty:
        return b""
    time_cols = [c for c in _TIME_COLS_DEFAULT if c in df_enriched.columns]
    expanded = _tz.add_local_columns(df_enriched, time_cols, tz_name=tz_name)
    # Normalise "Timestamp" to ISO-8601 UTC string for cross-tool safety.
    if "Timestamp" in expanded.columns:
        expanded["Timestamp"] = pd.to_datetime(
            expanded["Timestamp"], errors="coerce", utc=True
        ).dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    buf = io.StringIO()
    expanded.to_csv(buf, index=False)
    return buf.getvalue().encode("utf-8")


def _sat_detail_rows(
    df: pd.DataFrame,
    sats: Sequence[Sat],
    *,
    min_el_deg: float,
    cols: ColumnMap,
    tag: str,
) -> pd.DataFrame:
    """Long-format (TX, sat) rows used for the Excel export."""
    if df is None or df.empty or not cols.ready():
        return pd.DataFrame(
            columns=["Timestamp", "Device", "sat_name",
                     "el_deg", "az_deg", "range_km", "visible", "constellation"]
        )
    ts = pd.to_datetime(df[cols.time], errors="coerce", utc=True)
    lat = pd.to_numeric(df[cols.lat], errors="coerce")
    lon = pd.to_numeric(df[cols.lon], errors="coerce")
    dev_col = "Device Tab" if "Device Tab" in df.columns else (
        "device" if "device" in df.columns else None
    )
    rows: list[dict] = []
    for idx in df.index:
        t = ts.loc[idx]
        la = lat.loc[idx]
        lo = lon.loc[idx]
        if pd.isna(t) or pd.isna(la) or pd.isna(lo):
            continue
        if la == 0.0 and lo == 0.0:
            continue
        dt = t.to_pydatetime()
        for s in sats:
            la_ang = look_angles(s, dt, float(la), float(lo))
            if la_ang is None:
                continue
            vis = la_ang.el_deg > min_el_deg
            rows.append(dict(
                Timestamp=t.strftime("%Y-%m-%dT%H:%M:%SZ"),
                Device=df.at[idx, dev_col] if dev_col else "",
                sat_name=s.name,
                el_deg=round(la_ang.el_deg, 2),
                az_deg=round(la_ang.az_deg, 1),
                range_km=round(la_ang.range_km, 1),
                visible=bool(vis),
                constellation=tag,
            ))
    return pd.DataFrame(rows)


def build_events_excel(
    df_enriched: pd.DataFrame,
    iridium_sats: Sequence[Sat],
    gps_sats: Sequence[Sat],
    *,
    tz_name: str | None = None,
) -> bytes:
    """Return Excel (xlsx) bytes with events + per-sat visibility tabs."""
    if df_enriched is None or df_enriched.empty:
        return b""

    cols = resolve_columns(df_enriched)
    events_csv_bytes = build_events_csv(df_enriched, tz_name=tz_name)
    events = pd.read_csv(io.BytesIO(events_csv_bytes))

    iri_detail = _sat_detail_rows(
        df_enriched, iridium_sats,
        min_el_deg=IRI_MIN_EL_DEG, cols=cols, tag="IRIDIUM",
    )
    gps_detail = _sat_detail_rows(
        df_enriched, gps_sats,
        min_el_deg=_gps.GPS_MIN_EL_DEG, cols=cols, tag="GPS",
    )

    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        events.to_excel(writer, sheet_name="events", index=False)
        iri_detail.to_excel(writer, sheet_name="sat_visibility_iri", index=False)
        gps_detail.to_excel(writer, sheet_name="sat_visibility_gps", index=False)
    return buf.getvalue()


def default_filename(stem: str, *,
                     start: datetime | None = None,
                     end: datetime | None = None,
                     ext: str = "csv") -> str:
    """Compose the filename used by the download button."""
    start = start or datetime.now(timezone.utc)
    end = end or start
    fmt = "%Y%m%d"
    return f"phase3_replay_{stem}_{start.strftime(fmt)}_{end.strftime(fmt)}.{ext}"


def enrich_and_build(
    df: pd.DataFrame,
    iridium_sats: Sequence[Sat],
    gps_sats: Sequence[Sat],
    *,
    tle_epoch_utc=None,
    tz_name: str | None = None,
    as_excel: bool = False,
) -> tuple[bytes, pd.DataFrame]:
    """One-shot convenience: enrich then render.

    Returns ``(bytes, enriched_df)`` so the page can both hand the
    bytes to :func:`st.download_button` and keep the enriched frame
    around for on-screen rendering.
    """
    enriched = enrich_phase1_frame(
        df,
        iridium_sats=iridium_sats,
        gps_sats=gps_sats,
        tle_epoch_utc=tle_epoch_utc,
    )
    cols = resolve_columns(enriched)
    enriched = _ensure_time_col_exists(enriched, cols)

    if as_excel:
        payload = build_events_excel(enriched, iridium_sats, gps_sats, tz_name=tz_name)
    else:
        payload = build_events_csv(enriched, tz_name=tz_name)
    return payload, enriched


__all__ = [
    "P3_COLUMNS",
    "build_events_csv",
    "build_events_excel",
    "default_filename",
    "enrich_and_build",
]
