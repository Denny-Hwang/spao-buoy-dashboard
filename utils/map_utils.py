"""
Folium map builder for SPAO buoy drift trajectory visualization.
"""

import folium
import numpy as np
import pandas as pd

from utils.plot_utils import COLORS

BASEMAPS = {
    "Satellite": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "attr": "Esri",
        "name": "Esri Satellite",
    },
    "Terrain": {
        "tiles": "https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "attr": "Esri",
        "name": "Esri Terrain",
    },
    "Dark": {
        "tiles": "cartodbdark_matter",
        "attr": "CartoDB",
        "name": "CartoDB Dark",
    },
    "Street": {
        "tiles": "OpenStreetMap",
        "attr": "OpenStreetMap",
        "name": "OpenStreetMap",
    },
}


def interpolate_gps_zeros(df: pd.DataFrame, lat_col: str, lon_col: str) -> pd.DataFrame:
    """Interpolate GPS (0,0) points from neighboring valid fixes."""
    df = df.copy()
    df["interpolated"] = False

    zero_mask = (df[lat_col] == 0) & (df[lon_col] == 0)
    df.loc[zero_mask, lat_col] = np.nan
    df.loc[zero_mask, lon_col] = np.nan
    df.loc[zero_mask, "interpolated"] = True

    df[lat_col] = df[lat_col].interpolate(method="linear", limit_direction="both")
    df[lon_col] = df[lon_col].interpolate(method="linear", limit_direction="both")

    return df


def _popup_html(row: pd.Series, device_name: str = "") -> str:
    """Generate HTML popup content for a map marker with sensor details."""
    lines = []
    if device_name:
        lines.append(f"<b style='font-size:11px'>{device_name}</b><hr style='margin:2px 0'>")
    for col, val in row.items():
        if col in ("interpolated", "Device Tab", "IMEI", "_parsed_time"):
            continue
        if pd.isna(val):
            continue
        if isinstance(val, float):
            lines.append(f"<span style='font-size:10px'><b>{col}:</b> {val:.4f}</span>")
        else:
            lines.append(f"<span style='font-size:10px'><b>{col}:</b> {val}</span>")
    return "<br>".join(lines)


def build_drift_map(
    df: pd.DataFrame,
    basemap: str = "Satellite",
    lat_col: str = "GPS Latitude",
    lon_col: str = "GPS Longitude",
    device_col: str = "Device Tab",
    max_points: int = 1000,
    highlight_latest: bool = False,
) -> folium.Map:
    """Build a Folium drift trajectory map with per-device colors and clickable markers."""
    if df.empty:
        return folium.Map(location=[0, 0], zoom_start=2)

    # Ensure numeric GPS
    df = df.copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    # Subsample if too many points
    if len(df) > max_points:
        df = df.iloc[:: len(df) // max_points + 1].copy()

    # Interpolate GPS zeros
    df = interpolate_gps_zeros(df, lat_col, lon_col)
    df = df.dropna(subset=[lat_col, lon_col])
    if df.empty:
        return folium.Map(location=[0, 0], zoom_start=2)

    # Create base map
    center_lat = df[lat_col].mean()
    center_lon = df[lon_col].mean()

    bm = BASEMAPS.get(basemap, BASEMAPS["Satellite"])
    if bm["tiles"] in ("OpenStreetMap", "cartodbdark_matter"):
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6, tiles=bm["tiles"])
    else:
        m = folium.Map(location=[center_lat, center_lon], zoom_start=6)
        folium.TileLayer(
            tiles=bm["tiles"],
            attr=bm["attr"],
            name=bm["name"],
        ).add_to(m)

    # Device grouping
    if device_col in df.columns:
        devices = df[device_col].unique()
    else:
        devices = ["All"]
        df[device_col] = "All"

    for i, device in enumerate(devices):
        color = COLORS[i % len(COLORS)]
        device_df = df[df[device_col] == device].copy()

        if device_df.empty:
            continue

        # Draw trajectory line
        coords = list(zip(device_df[lat_col], device_df[lon_col]))
        if len(coords) > 1:
            folium.PolyLine(
                coords,
                color=color,
                weight=3,
                opacity=0.8,
                popup=str(device),
            ).add_to(m)

        # Add markers with popups
        for idx, (_, row) in enumerate(device_df.iterrows()):
            is_interp = row.get("interpolated", False)
            is_latest = highlight_latest and (idx == len(device_df) - 1)

            popup_html = _popup_html(row, device_name=str(device))

            if is_latest:
                # Latest point — large highlighted marker with star
                folium.Marker(
                    location=[row[lat_col], row[lon_col]],
                    popup=folium.Popup(popup_html, max_width=350),
                    tooltip=f"{device} (Latest)",
                    icon=folium.Icon(color="red", icon="star", prefix="fa"),
                ).add_to(m)
            else:
                # Regular trajectory point
                folium.CircleMarker(
                    location=[row[lat_col], row[lon_col]],
                    radius=5 if not is_interp else 3,
                    color=color,
                    fill=not is_interp,
                    fill_color=color if not is_interp else "white",
                    fill_opacity=0.8 if not is_interp else 0.3,
                    popup=folium.Popup(popup_html, max_width=350),
                    tooltip=f"{device}{' (interpolated)' if is_interp else ''}",
                ).add_to(m)

    folium.LayerControl().add_to(m)

    # Auto-zoom to fit all tracks
    all_lats = df[lat_col].tolist()
    all_lons = df[lon_col].tolist()
    if all_lats and all_lons:
        m.fit_bounds([[min(all_lats), min(all_lons)], [max(all_lats), max(all_lons)]])

    return m


def build_mini_map(
    df: pd.DataFrame,
    lat_col: str = "GPS Latitude",
    lon_col: str = "GPS Longitude",
    device_col: str = "IMEI",
) -> folium.Map:
    """Build a small overview map showing latest position per device."""
    if df.empty:
        return folium.Map(location=[0, 0], zoom_start=2, width="100%", height="300px")

    # Use satellite basemap
    bm = BASEMAPS["Satellite"]
    m = folium.Map(location=[0, 0], zoom_start=2, width="100%", height="300px")
    folium.TileLayer(tiles=bm["tiles"], attr=bm["attr"], name=bm["name"]).add_to(m)

    df = df.copy()
    df[lat_col] = pd.to_numeric(df[lat_col], errors="coerce")
    df[lon_col] = pd.to_numeric(df[lon_col], errors="coerce")

    if device_col not in df.columns:
        device_col_actual = "Device Tab" if "Device Tab" in df.columns else None
        if device_col_actual:
            device_col = device_col_actual
        else:
            devices = ["All"]
            df[device_col] = "All"

    devices = df[device_col].unique()

    lats, lons = [], []
    for i, device in enumerate(devices):
        device_df = df[df[device_col] == device]
        if device_df.empty:
            continue

        valid = device_df[device_df[lat_col].notna() & device_df[lon_col].notna()]
        valid = valid[(valid[lat_col] != 0) | (valid[lon_col] != 0)]
        if valid.empty:
            continue

        last = valid.iloc[-1]
        lat, lon = last[lat_col], last[lon_col]
        lats.append(lat)
        lons.append(lon)

        folium.Marker(
            location=[lat, lon],
            popup=f"{device}",
            icon=folium.Icon(color="red", icon="star", prefix="fa"),
        ).add_to(m)

    if lats and lons:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    return m
