# CLAUDE.md — project-wide context for SPAO Buoy Dashboard

## Architecture
- Phase 1 (operational): pages 1–6, existing utils. DO NOT MODIFY.
- Phase 2 (scientific): pages 7–11, utils/p2/, cron-based enrichment.
- Enrichment: GitHub Actions (hourly Open-Meteo, daily satellite) writes to
  Google Sheets. Streamlit reads enriched Sheets — no runtime external API calls.

## Phase 2 pages (emoji option B)
- 7_📖_Phase2_Overview.py   (reference / landing page)
- 8_🔋_TENG_Performance.py
- 9_🌊_SST_Validation.py
- 10_🧭_Drift_Dynamics.py
- 11_📡_Data_Enrichment.py

## Enriched v2 columns
WAVE_H_cm, WAVE_T_ds, WAVE_DIR_deg, SWELL_H_cm, SWELL_T_ds,
WIND_SPD_cms, WIND_DIR_deg, ERA5_PRES_dPa, ERA5_AIRT_cC,
SAT_SST_OISST_cC, SAT_SST_ERA5_cC, SAT_SST_MUR_cC, SAT_SST_OSTIA_cC,
SAT_SST_OPENMETEO_cC (coastal/inland fallback),
OSCAR_U_mms, OSCAR_V_mms, SEAICE_CONC_pct, ENRICH_FLAG (uint16 bitfield).

## Cron tiers
- enrichment_hourly.yml (:15 every hour): Open-Meteo Marine + Historical
- enrichment_daily.yml (07:30 UTC): OISST, MUR, OSTIA, OSCAR, OSI SAF sea ice

## Secrets
GitHub Actions: GCP_SERVICE_ACCOUNT_JSON, GOOGLE_SHEETS_ID,
COPERNICUS_USERNAME, COPERNICUS_PASSWORD.
Streamlit: gcp_service_account (unchanged).

## Non-negotiable rules
1. Phase 1 files untouched except utils/sheets_client.py (one helper appended).
2. Never commit secrets or credential files.
3. New utility modules require tests under tests/.
4. Each PR must preserve Phase 1 behavior — smoke test imports before opening PR.
5. All timestamps in UTC with pd.Timestamp(tz='UTC').
6. Enrichment fetchers must handle failures gracefully (return NaN, set flag bit).
7. Prefer vectorized pandas operations over row loops.
8. Phase 2 feature toggle: st.session_state["p2_show_enriched"] (default False).
9. copernicusmarine SDK is cron-only; never imported from Streamlit pages.
10. Page 1–6 behavior must be identical with or without Phase 2 merged.
