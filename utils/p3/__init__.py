"""Phase 3 — Iridium Link & RF Performance analysis package.

Phase 1 = operational telemetry (pages 1–6, untouched).
Phase 2 = oceanographic enrichment (pages 7–11, utils/p2/).
Phase 3 = satellite-link analysis (pages 12–15, this package).

The Phase 3 utilities answer questions like:
  - "Why did rb1 take 90 s on this particular TX?"
  - "How many Iridium satellites were above 8.2° at the fix time?"
  - "If we raised the GNSS timeout from 30 → 45 s, what would
     the fail rate have been across the last deployment?"

Design constraints carried over from Phase 2:
  * No external API calls happen inside the Streamlit process.
    TLE data is fetched by a cron job and written to the same
    Google Sheet used by Phase 1 (tabs ``_iridium_tle`` / ``_gps_tle``).
  * Phase 1 pages and their behavior must remain identical.
  * All timestamps are UTC internally; display-time localisation is
    a rendering-only concern handled by ``utils.p3.tz``.
"""
