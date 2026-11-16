# Be An Earth System Trend Detective

**NASA Space Apps Challenge 2026**

Be An Earth System Trend Detective is an interactive 3D globe that helps anyone explore how the climate of a place has changed over time. The user selects a country or a point on Earth, and the page shows trend charts for variables such as air temperature, precipitation, humidity, wind, evapotranspiration and soil moisture, together with simple statistical tests that indicate whether each change is real or just natural variability.

Video demonstrations: https://drive.google.com/drive/folders/1Qo57TDtzWzsjyyVo1HgW0vD-qcWXPjV0?usp=sharing

## What the page does

- **3D globe:** built with CesiumJS. The user can search for a place or click on the globe, and the selected country is highlighted.
- **Map layers:** NASA GIBS layers (air temperature, land surface temperature, sea surface temperature and rainfall) can be painted over the globe as a color gradient.
- **Climate Atlas:** for the selected region, the page downloads monthly data and shows charts grouped by theme, with the Sen's slope, the Mann-Kendall test and a plain-language explanation of each result. The default period is 2003–2025.
- **Help (?):** a short guide explaining the project, the databases, the analysis, how to select a location, and the team.
- **Neural network section:** an animated illustration and an explanation of the Temporal Convolutional Network (TCN) we trained to forecast nine variables, with two sections of forecast charts: **1 Month** (36 months of history to predict the next month) and **12 Months** (24 months of history to predict the next 12).

## How it works

1. The browser page (`templates/gt.html`) finds the coordinates of the chosen place and sends them to the Flask server.
2. The server (`app.py` and `region_data.py`) downloads monthly climate data from the NASA POWER API (based on MERRA-2), calculates the trends and returns the results as JSON.
3. The page draws the charts and explanations. The map layers come directly from NASA GIBS.

## Project files

- `app.py`: Flask server, page route and `/api/...` routes.
- `region_data.py`: data download and trend statistics for any region.
- `templates/gt.html`: the complete front end (globe, charts, help and neural network windows).
- `static/forecasts/`: the 18 forecast charts (`h1_*.png` and `h12_*.png`).
- `requirements.txt`: Python packages needed.

## Run it

```bash
cd "Página web 2"
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
python app.py
```

Open <http://127.0.0.1:5000> in your browser. In GitHub Codespaces, open port 5000 from the **Ports** tab.

## Contact

g14_garces@ens.cnyn.unam.mx- g14_valdivia@ens.cnyn.unam.mx - g14_noriega@ens.cnyn.unam.mx - g14_leon@ens.cnyn.unam.mx - g15_acevedo@ens.cnyn.unam.mx -g16_medina@ens.cnyn.unam.mx -· <https://github.com/Robertolabastida/Be-An-Earth-System-Trend-Detective>
