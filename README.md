# EarthTrend AI — NASA Space Apps 2026

Small, real-data trend explorer for **Be An Earth System Trend Detective!** The active application is **[Página web 2](./P%C3%A1gina%20web%202)** (Flask + Cesium globe + Chart.js). The older React/FastAPI prototypes remain untouched.

## What works

- Choose a **data source** and a scientific variable.
- Pick a point by clicking the globe or searching for a place.
- Choose a year range and inspect monthly observations, seasonal anomalies, linear and Sen slopes, and Mann–Kendall significance.
- Sources:
  - **NASA POWER**: 2 m air temperature and precipitation (monthly; no credentials).
  - **NOAA OISST**: sea surface temperature (ocean only; no credentials).
  - **NASA AppEEARS / Aqua MODIS**: NDVI, EVI, land surface temperature (point samples; Earthdata token required).

NASA GIBS provides the **globe background only**. The visual background is not analyzed as trend data. AppEEARS queries use a single satellite pixel near the selected point, **not a region-wide average or spatial trend heatmap**.

## Run locally or in GitHub Codespaces

Use Python 3.11+ and run from the application folder:

\`\`\`bash
cd "Página web 2"
python -m venv .venv
source .venv/bin/activate                 # Linux / Codespaces
# Windows PowerShell: .venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
\`\`\`

Open the forwarded **port 5000** in Codespaces, or http://127.0.0.1:5000 locally.

### NASA AppEEARS credentials

Sign up for [NASA Earthdata Login](https://urs.earthdata.nasa.gov/) and use the [AppEEARS API](https://appeears.earthdatacloud.nasa.gov/api/) to obtain a Bearer token (normally expires in ~48 hours).

In **Codespaces → Repository Settings → Secrets and variables → Codespaces**, add either:

- \`APPEEARS_TOKEN\` — a fresh Bearer token **without** the \`Bearer \` prefix; **or**
- \`EARTHDATA_USERNAME\` and \`EARTHDATA_PASSWORD\` — the server can obtain a token when needed.

Alternatively create a local ignored \`.env\` from [\`.env.example\`](./.env.example) in the repository root or application directory. **Never commit tokens, passwords, or .env files.** A previously exposed token/password should be revoked or rotated. The frontend never receives NASA credentials.

The token is used only server-side. Aqua MODIS extraction submits an AppEEARS point **task**, checks status, then retrieves the scientific CSV. NASA processing can take time. The running server keeps task metadata in memory; restarting it loses pending-task tracking. New tasks should only be submitted intentionally with **Analyze**.

## Run tests

\`\`\`bash
python -m pytest tests -q
\`\`\`

Tests mock NASA requests; they do **not** contact AppEEARS or verify Earthdata credentials.

## Scientific cautions

- Year ranges require **at least ten years**. 2026 is incomplete; for clean year-to-year comparisons use **2003–2025** for Aqua MODIS.
- AppEEARS supplies **8-day/16-day composite** pixel values; these are aggregated to unweighted monthly means after basic quality masking where a matching QA layer was available.
- AppEEARS point CSV values may be scaled; the parser normalizes NDVI/EVI and converts land surface temperature from Kelvin to Celsius. It rejects fill values, and reports whether a QA column was found.
- POWER air temperature is **not equivalent** to MODIS land surface temperature.
- Mann–Kendall and AR(1)-adjusted linear estimates are useful exploratory statistics, **not proof of causes**. Small sample sizes, seasonality, changing measurement coverage, and spatial bias still matter.
- The optional NOAA source is non-NASA and is provided for context; NASA POWER and Aqua MODIS satisfy the NASA-data emphasis of the challenge.

## Implementation notes

- \`Página web 2/app.py\`: Flask API and small cache.
- \`Página web 2/data_sources.py\`: NASA POWER and NOAA clients.
- \`Página web 2/modis.py\`: NASA AppEEARS point task, QA and CSV handling.
- \`Página web 2/analysis.py\`: trend statistics.
- \`Página web 2/templates/gt.html\`: HTML layout.
- \`Página web 2/static/\`: globe, controls and chart assets.

**Not yet implemented:** area samples/GeoTIFF trend heatmaps, satellite-pixel significance maps, background job persistence or cross-source correlations. These are deliberately out of scope for the first minimal integration.

Official references: [NASA challenge](https://www.spaceappschallenge.org/2026/challenges/earth-system-trend-detective/), [AppEEARS API docs](https://appeears.earthdatacloud.nasa.gov/api/), [NASA AppEEARS tutorials](https://github.com/nasa/AppEEARS-Data-Resources).
