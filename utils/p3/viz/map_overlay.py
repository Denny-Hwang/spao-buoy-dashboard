"""HTML-prototype-style overlay map used on every Phase 3 page.

Renders a Folium map with three layers:

* the **observer** (red circle),
* the **great-circle horizon** ring at the current elevation mask
  (dashed blue),
* every **visible satellite's sub-point** as a blue circle + a dashed
  line back to the observer.

This replaces the plain "pin + empty map" we had before so the Phase 3
pages look the way the HTML prototype did — sat positions, ground
tracks, and link lines on one world view.

The tile selector defaults to **satellite imagery** (ESRI World
Imagery) per operator preference: oceanographers recognise buoy
positions faster against real-world shorelines than against an
abstract dark theme.
"""

from __future__ import annotations

from typing import Sequence

import folium

from utils.p3.sgp4_engine import (
    Sat,
    look_angles,
    sat_subpoint,
    visibility_radius_km,
)


# Friendly labels the pages show; internal key drives the tile URL.
TILE_LABELS: tuple[str, ...] = ("Satellite", "Terrain", "Dark")
TILE_URLS: dict[str, tuple[str, str]] = {
    "Satellite": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Imagery/MapServer/tile/{z}/{y}/{x}",
        "Esri World Imagery",
    ),
    "Terrain": (
        "https://server.arcgisonline.com/ArcGIS/rest/services/"
        "World_Topo_Map/MapServer/tile/{z}/{y}/{x}",
        "Esri World Topo",
    ),
    "Dark": (
        "https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png",
        "CartoDB",
    ),
}


def add_tile(m: folium.Map, tile: str = "Satellite") -> None:
    """Add the chosen tile layer to ``m`` (default = satellite)."""
    url, attr = TILE_URLS.get(tile, TILE_URLS["Satellite"])
    folium.TileLayer(tiles=url, attr=attr, name=tile,
                     overlay=False, control=False).add_to(m)


def _observer_marker(lat: float, lon: float,
                     label: str = "Observer") -> folium.CircleMarker:
    return folium.CircleMarker(
        location=[lat, lon], radius=7,
        color="#ffffff", weight=2,
        fill=True, fill_color="#C62828", fill_opacity=1.0,
        popup=label,
    )


def _horizon_ring(lat: float, lon: float,
                  min_el_deg: float, h_sat_km: float) -> folium.Circle:
    r_km = visibility_radius_km(min_el_deg, h_sat_km)
    return folium.Circle(
        location=[lat, lon],
        radius=r_km * 1000.0,
        color="#58a6ff",
        weight=1.4, opacity=0.85,
        dash_array="8 6",
        fill=False,
        popup=f"{min_el_deg:.1f}° horizon (~{r_km:.0f} km)",
    )


def _sat_layer(m: folium.Map,
               sats: Sequence[Sat],
               dt,
               obs_lat: float,
               obs_lon: float,
               *,
               min_el_deg: float,
               color: str = "#0078D4",
               link_color: str = "#58a6ff",
               label_prefix: str = "") -> int:
    """Draw visible sats as sub-points + dashed link lines.

    Returns the count of sats actually rendered.
    """
    n = 0
    for s in sats:
        la = look_angles(s, dt, obs_lat, obs_lon)
        if la is None or la.el_deg <= min_el_deg:
            continue
        sub = sat_subpoint(s, dt)
        if sub is None:
            continue
        lat_s, lon_s, alt_s = sub
        folium.CircleMarker(
            location=[lat_s, lon_s], radius=5,
            color="#0b3d66", weight=1,
            fill=True, fill_color=color, fill_opacity=0.9,
            popup=(f"{label_prefix}{s.name}<br>"
                   f"el {la.el_deg:.1f}° · az {la.az_deg:.0f}°<br>"
                   f"alt {alt_s:.0f} km · range {la.range_km:.0f} km"),
        ).add_to(m)
        folium.PolyLine(
            locations=[[obs_lat, obs_lon], [lat_s, lon_s]],
            color=link_color, weight=1.2, opacity=0.55,
            dash_array="5 5",
        ).add_to(m)
        n += 1
    return n


def build_overlay_map(
    observer_lat: float,
    observer_lon: float,
    *,
    dt,
    iridium_sats: Sequence[Sat] | None = None,
    gps_sats: Sequence[Sat] | None = None,
    min_el_deg: float = 8.2,
    h_sat_km: float = 781.0,
    tile: str = "Satellite",
    zoom_start: int = 4,
    observer_label: str = "Observer",
    horizon: bool = True,
) -> folium.Map:
    """Build the HTML-demo-style overlay map.

    Parameters
    ----------
    observer_lat, observer_lon
        The buoy / user / waypoint location.
    dt
        UTC instant used for all SGP4 look-angle calculations.
    iridium_sats / gps_sats
        Optional constellations to overlay. Iridium markers are blue,
        GPS markers are green so both can be visible at once.
    min_el_deg
        Elevation mask for the Iridium layer + horizon ring.
    h_sat_km
        Orbital altitude used for the horizon radius (default Iridium).
    tile
        Base tile key in :data:`TILE_LABELS`. **Default is satellite.**
    """
    m = folium.Map(
        location=[observer_lat, observer_lon],
        zoom_start=zoom_start,
        tiles=None,
        attribution_control=True,
        world_copy_jump=True,
    )
    add_tile(m, tile)
    _observer_marker(observer_lat, observer_lon, observer_label).add_to(m)
    if horizon:
        _horizon_ring(observer_lat, observer_lon, min_el_deg, h_sat_km).add_to(m)
    if iridium_sats:
        _sat_layer(m, iridium_sats, dt, observer_lat, observer_lon,
                   min_el_deg=min_el_deg,
                   color="#1f6feb", link_color="#58a6ff",
                   label_prefix="🛰 ")
    if gps_sats:
        _sat_layer(m, gps_sats, dt, observer_lat, observer_lon,
                   min_el_deg=5.0,
                   color="#2E7D32", link_color="#6fbf73",
                   label_prefix="📡 ")
    return m
