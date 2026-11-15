"""Climate series for the "Data sources" panel, for ANY point on Earth.

Source: NASA POWER monthly point API (MERRA-2 based reanalysis). The same code
works for Ensenada, the Amazon, the Sahel, Svalbard... whatever the user selects.
"""
import math
import time
from concurrent.futures import ThreadPoolExecutor

import numpy as np
import requests
from scipy import stats

POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
SOURCE = "NASA POWER · MERRA-2 reanalysis, monthly, point at the selected place"
CACHE, TTL = {}, 6 * 3600


class RegionError(Exception):
    pass


GROUPS = [
    {"id": "water", "name": "Water Cycle",
     "note": "Rainfall, humidity and evapotranspiration at the selected place."},
    {"id": "atmos", "name": "Atmospheric Conditions",
     "note": "Air temperature, pressure, wind and solar radiation at the selected place."},
    {"id": "land", "name": "Land & Soil Surface",
     "note": "Surface and soil temperature and soil moisture. Over open ocean these variables have no data."},
]

# (POWER parameter, title, unit, group)
VARS = [
    ("PRECTOTCORR", "Precipitation", "mm/day", "water"),
    ("QV2M", "Specific humidity at 2 m", "g/kg", "water"),
    ("RH2M", "Relative humidity at 2 m", "%", "water"),
    ("EVPTRNS", "Evapotranspiration energy flux", "MJ/m²/day", "water"),
    ("T2M", "Air temperature at 2 m", "°C", "atmos"),
    ("PS", "Surface pressure", "kPa", "atmos"),
    ("WS10M", "Wind speed at 10 m", "m/s", "atmos"),
    ("ALLSKY_SFC_SW_DWN", "Solar radiation at the surface", "kWh/m²/day", "atmos"),
    ("TS", "Earth skin temperature", "°C", "land"),
    ("TSOIL1", "Soil temperature (top layer)", "°C", "land"),
    ("GWETTOP", "Surface soil wetness", "0–1", "land"),
    ("GWETROOT", "Root-zone soil wetness", "0–1", "land"),
]


def _fetch(param, lat, lon, y0, y1):
    r = requests.get(POWER_URL, timeout=60, params={
        "parameters": param, "community": "AG", "latitude": round(lat, 4),
        "longitude": round(lon, 4), "start": y0, "end": y1, "format": "JSON"})
    r.raise_for_status()
    series = r.json()["properties"]["parameter"][param]
    t, v = [], []
    for key, val in sorted(series.items()):
        if key.endswith("13") or val is None or val <= -900:     # annual row / fill value
            continue
        t.append(int(key[:4]) + (int(key[4:]) - 0.5) / 12)
        v.append(float(val))
    return np.array(t), np.array(v)


def _sen(x, y):
    n = len(x)
    return float(np.median([(y[j] - y[i]) / (x[j] - x[i])
                            for i in range(n - 1) for j in range(i + 1, n)]))


def _mann_kendall_p(y):
    n = len(y)
    s = sum(np.sign(y[j] - y[i]) for i in range(n - 1) for j in range(i + 1, n))
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in counts)) / 18
    if var <= 0:
        return 1.0
    z = (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var) if s < 0 else 0.0
    return float(2 * (1 - stats.norm.cdf(abs(z))))


def _analyze(param, title, unit, group, t, v):
    if len(v) < 24:
        return None
    w = 12
    sm = np.convolve(v, np.ones(w) / w, mode="valid")
    smooth = [[round(float(t[i + w // 2]), 3), round(float(sm[i]), 4)] for i in range(len(sm))]

    years = np.floor(t).astype(int)
    ax, ay = [], []
    for yr in np.unique(years):
        m = years == yr
        if m.sum() == 12:                                   # complete years only
            ax.append(yr + 0.5)
            ay.append(float(v[m].mean()))
    out = {"id": param, "name": title, "unit": unit, "group": group,
           "t": [round(float(x), 3) for x in t], "values": [round(float(x), 4) for x in v],
           "smooth": smooth, "trend": None, "sen_per_decade": None, "p": None,
           "significant": False, "direction": None}
    if len(ax) >= 10:
        ax, ay = np.array(ax), np.array(ay)
        slope = _sen(ax, ay)
        icpt = float(np.median(ay - slope * ax))
        p = _mann_kendall_p(ay)
        out.update(trend=[[round(float(t[0]), 3), round(icpt + slope * float(t[0]), 4)],
                          [round(float(t[-1]), 3), round(icpt + slope * float(t[-1]), 4)]],
                   sen_per_decade=slope * 10, p=p, significant=bool(p < 0.05),
                   direction="increasing" if slope > 0 else "decreasing")
    return out


def region_report(lat, lon, y0, y1):
    key = (round(lat, 2), round(lon, 2), y0, y1)
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        return hit[1]

    def job(spec):
        param, title, unit, group = spec
        try:
            t, v = _fetch(param, lat, lon, y0, y1)
            return spec, _analyze(param, title, unit, group, t, v)
        except Exception:                                   # one failed variable must not break the rest
            return spec, None

    with ThreadPoolExecutor(6) as ex:
        results = list(ex.map(job, VARS))

    groups = []
    for g in GROUPS:
        items = [res for spec, res in results if spec[3] == g["id"] and res]
        groups.append({**g, "items": items})
    if not any(g["items"] for g in groups):
        raise RegionError("NASA POWER returned no data for this place and period. Try another location or years.")

    payload = {"lat": lat, "lon": lon, "start": y0, "end": y1, "source": SOURCE, "groups": groups}
    CACHE[key] = (time.time(), payload)
    return payload