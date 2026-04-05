"""
Folium map builder for SPAO buoy drift trajectory visualization.
"""

import folium
import numpy as np
import pandas as pd
from folium.plugins import MarkerCluster

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


def interpolate_gps_zeros(df: pd.DataFrame, lat_col: str = "GPS Latitude", lon_col: str = "GPS Longitude") -> pd.DataFrame:
    """
    Interpolate GPS (0,0) points from neighboring valid fixes.
    Adds an 'interpolated' boolean column.
    """
    df = df.copy()
    df["interpolated"] = False

    # Mark zero GPS as NaN for interpolation
    zero_mask = (df[lat_col] == 0) & (df[lon_col] == 0)
    df.loc[zero_mask, lat_col] = np.nan
    df.loc[zero_mask, lon_col] = np.nan
    df.loc[zero_mask, "interpolated"] = True

    # Interpolate linearly
    df[lat_col] = df[lat_col].interpolate(method="linear", limit_direction="both")
    df[lon_col] = df[lon_col].interpolate(method="linear", limit_direction="both")

    return df


def _popup_html(row: pd.Series) -> str:
    """Generate HTML popup content for a map marker."""
    lines = []
    for col, val in row.items():
        if col == "interpolated":
            continue
        lines.append(f"<b>{col}:</b> {val}")
    return "<br>".join(lines)


def build_drift_map(
    df: pd.DataFrame,
    basemap: str = "Street",
    lat_col: str = "GPS Latitude",
    lon_col: str = "GPS Longitude",
    device_col: str = "IMEI",
    max_points: int = 1000,
) -> folium.Map:
    """
    Build a Folium drift trajectory map.

    Args:
        df: DataFrame with GPS and sensor data.
        basemap: One of "Satellite", "Terrain", "Dark", "Street".
        lat_col: Column name for latitude.
        lon_col: Column name for longitude.
        device_col: Column name for device ID.
        max_points: Subsample if total points exceed this.

    Returns:
        Folium Map object.
    """
    if df.empty:
        return folium.Map(location=[0, 0], zoom_start=2)

    # Subsample if too many points
    if len(df) > max_points:
        df = df.iloc[:: len(df) // max_points + 1].copy()

    # Interpolate GPS zeros
    df = interpolate_gps_zeros(df, lat_col, lon_col)

    # Drop rows where GPS is still NaN after interpolation
    df = df.dropna(subset=[lat_col, lon_col])
    if df.empty:
        return folium.Map(location=[0, 0], zoom_start=2)

    # Create base map
    center_lat = df[lat_col].mean()
    center_lon = df[lon_col].mean()

    bm = BASEMAPS.get(basemap, BASEMAPS["Street"])
    if bm["tiles"] in ("OpenStreetMap", "cartodbdark_matter"):
        m = folium.Map(location=[center_lat, center_lon], zoom_start=4, tiles=bm["tiles"])
    else:
        m = folium.Map(location=[center_lat, center_lon], zoom_start=4)
        folium.TileLayer(
            tiles=bm["tiles"],
            attr=bm["attr"],
            name=bm["name"],
        ).add_to(m)

    # Add device tracks
    if device_col in df.columns:
        devices = df[device_col].unique()
    else:
        devices = ["All"]
        df = df.copy()
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

        # Add markers
        for _, row in device_df.iterrows():
            is_interp = row.get("interpolated", False)
            icon_color = "gray" if is_interp else "blue"
            icon = "question-sign" if is_interp else "record"
            prefix = "glyphicon"

            folium.CircleMarker(
                location=[row[lat_col], row[lon_col]],
                radius=5 if not is_interp else 4,
                color=color,
                fill=not is_interp,
                fill_color=color if not is_interp else "white",
                fill_opacity=0.8 if not is_interp else 0.3,
                popup=folium.Popup(_popup_html(row), max_width=300),
                tooltip=f"{device} {'(interpolated)' if is_interp else ''}",
            ).add_to(m)

    # Add layer control if multiple basemaps
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

    m = folium.Map(location=[0, 0], zoom_start=2, width="100%", height="300px")

    if device_col in df.columns:
        devices = df[device_col].unique()
    else:
        devices = ["All"]
        df = df.copy()
        df[device_col] = "All"

    lats, lons = [], []
    for i, device in enumerate(devices):
        device_df = df[df[device_col] == device]
        if device_df.empty:
            continue

        # Get latest row with valid GPS
        valid = device_df[(device_df[lat_col] != 0) | (device_df[lon_col] != 0)]
        if valid.empty:
            continue

        last = valid.iloc[-1]
        lat, lon = last[lat_col], last[lon_col]
        lats.append(lat)
        lons.append(lon)

        color = COLORS[i % len(COLORS)]
        folium.Marker(
            location=[lat, lon],
            popup=f"{device}",
            icon=folium.Icon(color="blue", icon="info-sign"),
        ).add_to(m)

    if lats and lons:
        m.fit_bounds([[min(lats), min(lons)], [max(lats), max(lons)]])

    return m
