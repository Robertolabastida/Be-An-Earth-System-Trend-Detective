# backend/main.py
import os, datetime
from typing import List
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import requests
from functools import lru_cache

# Load credentials from environment
USER = os.environ.get("METEOMATICS_USER")
PASSWORD = os.environ.get("METEOMATICS_PASSWORD")
BASE_URL = os.environ.get("METEOMATICS_BASE_URL", "https://api.meteomatics.com")

if not USER or not PASSWORD:
    raise RuntimeError("Meteomatics credentials not set in environment")

app = FastAPI(title="EarthTrend AI API")

# Enable CORS for dev (front-end on different port)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # adjust in production
    allow_methods=["*"],
    allow_headers=["*"],
)

def build_time_range(start: str, end: str, step: str) -> str:
    """
    Construct the Meteomatics time range string. e.g. "2026-01-01T00:00:00Z--2026-01-10T00:00:00Z:P1D"
    """
    return f"{start}--{end}:{step}"

@lru_cache(maxsize=128)
def query_meteomatics(range_str: str, parameters: str, location: str, fmt: str) -> dict:
    """
    Perform a GET request to Meteomatics API and return parsed JSON.
    Results are cached for identical queries.
    """
    url = f"{BASE_URL}/{range_str}/{parameters}/{location}/{fmt}"
    res = requests.get(url, auth=(USER, PASSWORD), timeout=10)
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    return res.json()

@app.get("/api/time_series")
def get_time_series(
    parameter: str = Query(..., description="Parameter code (e.g. t_2m:C)"),
    lat: float = Query(..., description="Latitude of point"),
    lon: float = Query(..., description="Longitude of point"),
    start: str = Query(..., description="Start datetime (ISO 8601, e.g. 2026-01-01T00:00:00Z)"),
    end: str = Query(..., description="End datetime (ISO 8601)"),
    step: str = Query("PT1H", description="Time step (ISO 8601 duration, e.g. PT1H or P1D)"),
):
    """
    Returns JSON time series for a given variable at one coordinate.
    """
    range_str = build_time_range(start, end, step)
    loc = f"{lat},{lon}"
    try:
        data = query_meteomatics(range_str, parameter, loc, "json")
    except HTTPException as e:
        raise
    # Transform Meteomatics output to simple {date, value} list
    times = []
    for entry in data["data"]:
        if entry["coordinates"]:
            for point in entry["coordinates"]:
                for dt_val in point["dates"]:
                    times.append({"date": dt_val["date"], "value": dt_val["value"]})
    # Sort by date
    times.sort(key=lambda x: x["date"])
    return {"parameter": parameter, "location": {"lat": lat, "lon": lon}, "series": times}

@app.get("/api/linear_trend")
def get_linear_trend(
    parameter: str = Query(...),
    lat: float = Query(...),
    lon: float = Query(...),
    start: str = Query(...),
    end: str = Query(...),
    step: str = Query("P1M"),
):
    """
    Returns the time series and linear trend (slope) for the specified range.
    """
    ts = get_time_series(parameter, lat, lon, start, end, step)
    series = ts["series"]
    if not series:
        raise HTTPException(status_code=400, detail="No data returned")
    # Compute linear regression (using simple least squares)
    import numpy as np
    dates = [datetime.datetime.fromisoformat(pt["date"][:-1]) for pt in series]
    # Convert to numeric time (days since start)
    base = dates[0]
    xs = np.array([(dt - base).total_seconds() / 86400.0 for dt in dates])
    ys = np.array([pt["value"] for pt in series])
    A = np.vstack([xs, np.ones(len(xs))]).T
    m, c = np.linalg.lstsq(A, ys, rcond=None)[0]  # slope (per day), intercept
    # Calculate R-squared for quality measure
    yfit = m * xs + c
    ss_res = np.sum((ys - yfit) ** 2)
    ss_tot = np.sum((ys - np.mean(ys)) ** 2)
    r2 = 1 - ss_res/ss_tot if ss_tot != 0 else 1.0
    return {
        "parameter": parameter,
        "slope": m,
        "intercept": c,
        "r_squared": r2,
        "series": series
    }

@app.get("/api/heatmap")
def get_heatmap(
    parameter: str = Query(..., description="Parameter code"),
    north: float = Query(..., description="Northern latitude of bounding box"),
    south: float = Query(..., description="Southern latitude"),
    east: float = Query(..., description="Eastern longitude"),
    west: float = Query(..., description="Western longitude"),
    time: str = Query(..., description="Datetime (ISO 8601) for the map"),
):
    """
    Returns a PNG heatmap image for the given parameter and bounding box at one time.
    """
    # Build Meteomatics grid query: lat_south,lon_west_lat_north,lon_east with resolution (auto)
    loc = f"{south},{west}_{north},{east}:0.25,0.25"
    range_str = time
    # Use format=png for heatmap
    url = f"{BASE_URL}/{range_str}/{parameter}/{loc}/png"
    res = requests.get(url, auth=(USER, PASSWORD), timeout=10)
    if res.status_code != 200:
        raise HTTPException(status_code=res.status_code, detail=res.text)
    # Stream back the image bytes
    from fastapi.responses import StreamingResponse
    return StreamingResponse(res.iter_content(chunk_size=1024), media_type="image/png")
