# Be An Earth System Trend Detective

**NASA Space Apps Challenge 2026**

An interactive 3D globe that lets anyone pick a place on Earth and see how its climate has changed over time. Click a country or a point on the globe and the page shows trend charts for temperature, precipitation, humidity, wind, soil moisture and more, together with simple statistical tests that tell you whether each change is real or just noise. It also explains the neural networks we trained to forecast these variables.

---

## What can you do on the page?

| Button | What it does |
|---|---|
| **Search box / click on the globe** | Select a country, city or any point on Earth. The country is highlighted. |
| **Layers** | Paint the globe with a NASA map layer (air temperature, land surface temperature, sea surface temperature, rainfall). The window can be minimized. |
| **Data sources (Climate Atlas)** | Charts and trend statistics for the selected region, grouped by theme. Change the period (default 2003–2025). |
| **? (Help)** | A short guide: what the project is, the databases, how the analysis works, FAQ, contact and team. |
| **Neural network** | An animated illustration, an explanation of our forecasting model, and two sections: **1 Month** and **12 Months**, each with 9 forecast charts. |

---

## How it works (in simple words)

```
 Your browser (gt.html)                     Flask server (app.py)                    Outside data
 ┌────────────────────┐   /api/region      ┌─────────────────────┐   NASA POWER   ┌──────────────┐
 │ 3D globe (Cesium)  │ ────────────────►  │ region_data.py      │ ─────────────► │ MERRA-2 data │
 │ Charts (Chart.js)  │ ◄────────────────  │ trends + statistics │ ◄───────────── │ (monthly)    │
 │ Help / NN windows  │      JSON          └─────────────────────┘                └──────────────┘
 └────────────────────┘
        │   map tiles                                           ┌────────────────────────────┐
        └─────────────────────────────────────────────────────► │ NASA GIBS (map layers)     │
        │   search + country outline                            │ Nominatim / OpenStreetMap  │
        └─────────────────────────────────────────────────────► └────────────────────────────┘
```

1. **You pick a place.** The page finds its latitude and longitude (using OpenStreetMap's Nominatim) and outlines the country.
2. **The page asks our server for data.** It calls `/api/region` with the coordinates and the years you chose.
3. **The server downloads monthly climate data** from the NASA POWER API (which is built on NASA's MERRA-2 reanalysis) and calculates the trends.
4. **The page draws the charts** and shows a plain-language explanation next to each one.
5. **The globe layers** come straight from NASA GIBS, so they do not pass through our server.

### How do we know if a trend is real?

For each variable we compute:

- **Sen's slope**: the typical rate of change per year (or per decade). It is robust to outliers.
- **Mann-Kendall test**: checks whether there is a consistent upward or downward trend. A small *p-value* (below 0.05) means the trend is unlikely to be random.
- **Seasonal Mann-Kendall test**: the same idea, but it compares each month with the same month in other years, so the seasons do not hide or fake a trend.
- **Autocorrelation-adjusted regression (AR(1))**: a check that takes into account that consecutive months are not independent.

### The neural networks

We trained a **Temporal Convolutional Network (TCN)** that looks at the past and predicts the future of nine variables:

- **1 Month:** uses the last 36 months to forecast the next month.
- **12 Months:** uses the last 24 months to forecast the next 12 months.

Variables: soil temperature, surface soil moisture, deep soil moisture, precipitation, evapotranspiration, air temperature, specific humidity, east wind and north wind. The 18 forecast charts (9 per horizon) are static images generated from our training notebooks and shown in the page.

> The forecast charts do not change when you select a different country. They show the results of the trained model for the study area described in the page.

---

## Project structure

```
Página web 2/
├── app.py                 # Flask server: serves the page and the /api/... routes
├── region_data.py         # Downloads NASA POWER data and computes the trend statistics
├── analysis.py            # Statistical analysis helpers
├── data_sources.py        # Variable definitions and data download helpers
├── requirements.txt       # Python packages needed
├── templates/
│   └── gt.html            # The whole web page (HTML + CSS + JavaScript)
└── static/
    └── forecasts/         # 18 PNG charts of the neural networks
        ├── h1_*.png       #   1-month forecasts   (9 images)
        └── h12_*.png      #   12-month forecasts  (9 images)
```

### What each file does

- **`app.py`** — Creates the Flask app. Its routes are:
  - `/` shows the page.
  - `/api/variables` lists all the variables available.
  - `/api/series` returns the time series and trend for one variable.
  - `/api/region` returns the full Climate Atlas report for a place.
  - `/api/local/...` lets the page read the local plots and CSV files of our own analysis, if those folders exist.
- **`region_data.py`** — The part that makes the page work for *any* region. It downloads data from NASA POWER, groups the variables into themes (with friendly names), runs the statistics and returns a JSON report.
- **`templates/gt.html`** — The entire front end: the Cesium globe, map-layer selector, country highlight, charts (Chart.js), the help window and the neural-network window.
- **`static/forecasts/`** — The nine charts for each forecast horizon. File names must stay exactly as they are, because the page loads them by name (for example `h1_air_temp.png`, `h12_precip.png`).

---

## Run it on your computer

You need **Python 3.10 or newer** and internet access.

```bash
# 1. Clone the repository and go into the web folder
git clone https://github.com/Robertolabastida/Be-An-Earth-System-Trend-Detective.git
cd Be-An-Earth-System-Trend-Detective/"Página web 2"

# 2. Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate

# 3. Install the packages
pip install -r requirements.txt

# 4. Start the server
python app.py
```

Then open <http://127.0.0.1:5000> in your browser. In GitHub Codespaces, open the forwarded port 5000 from the **Ports** tab.

### Optional settings (environment variables)

| Variable | Purpose |
|---|---|
| `FLASK_DEBUG=1` | Turns on Flask debug mode. |
| `PRECIP_DIR`, `STATS_DIR` | Folders with our local precipitation data and statistical analysis outputs. |

If you use a `.env` file for private tokens (for example a NASA AppEEARS token), **never commit it**. Keep `.env` and `.venv/` in `.gitignore`.

---

## Data sources

- **NASA POWER** (Prediction Of Worldwide Energy Resources), monthly point data derived from **MERRA-2** — climate series for the Climate Atlas.
- **NASA GIBS** (Global Imagery Browse Services) — the map layers on the globe: MERRA-2 air temperature, MODIS land surface temperature, GHRSST MUR sea surface temperature and IMERG precipitation rate.
- **OpenStreetMap Nominatim** — place search and country outlines.
- **CesiumJS** — the 3D globe. **Chart.js** — the charts.

## Limitations (please read)

- Each report uses **one point** (the place you click or the centre of the country), not an average of the whole country. Large countries can have very different climates inside.
- MERRA-2 is a **model-based reanalysis** with a resolution of about 50 km. It is not the same as a weather-station measurement.
- A trend over about 20 years describes **recent variability and change**. It is not by itself proof of long-term climate change.
- The forecast charts are examples of model performance and are not official predictions.

## Troubleshooting

| Problem | Solution |
|---|---|
| `ModuleNotFoundError` | The virtual environment is not active, or you skipped `pip install -r requirements.txt`. |
| The page says "Image not found" in a forecast section | Make sure the 18 PNG files are in `static/forecasts/` with the exact names. |
| Charts do not load for a region | NASA POWER may be slow or temporarily unavailable. Wait a few seconds and try again. |
| You see old content after an update | Hard refresh with Ctrl+F5 and restart `python app.py`. |
| The page does not open in Codespaces | Open the **Ports** tab and make sure port 5000 is forwarded. |

## Team and contact

Team members are listed in the **?** section of the page.
Questions: - g14_garces@ens.cnyn.unam.mx- g14_valdivia@ens.cnyn.unam.mx - g14_noriega@ens.cnyn.unam.mx - g14_leon@ens.cnyn.unam.mx - g15_acevedo@ens.cnyn.unam.mx -g16_medina@ens.cnyn.unam.mx - · Repository: <https://github.com/Robertolabastida/Be-An-Earth-System-Trend-Detective>
