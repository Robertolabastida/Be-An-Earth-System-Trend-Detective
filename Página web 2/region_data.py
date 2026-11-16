"""Climate data for ANY point on Earth, from the NASA POWER monthly point API.

Two things live here:
  1. region_report()   -> the charts of the "Climate Atlas" panel (grouped by theme).
  2. EXTRA_VARIABLES + extra_analyze() -> more variables for the "Choose variables"
     list, analysed with the same statistics as the original variables.
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
    i, j = np.triu_indices(len(x), 1)
    dx = x[j] - x[i]
    ok = dx > 0
    return float(np.median((y[j] - y[i])[ok] / dx[ok]))


def _mk_s_var(y):
    y = np.asarray(y, dtype=float)
    n = len(y)
    if n < 3:
        return 0.0, 0.0
    d = y[None, :] - y[:, None]
    s = float(np.sign(d[np.triu_indices(n, 1)]).sum())
    _, counts = np.unique(y, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - sum(c * (c - 1) * (2 * c + 5) for c in counts)) / 18
    return s, float(var)


def _z_to_p(s, var):
    if var <= 0:
        return 1.0
    z = (s - 1) / math.sqrt(var) if s > 0 else (s + 1) / math.sqrt(var) if s < 0 else 0.0
    return float(2 * (1 - stats.norm.cdf(abs(z))))


def _mann_kendall_p(y):
    return _z_to_p(*_mk_s_var(y))


def _seasonal_mk_p(v, mon):
    """Hirsch et al. (1982): one Mann-Kendall test per calendar month, summed."""
    s_tot = var_tot = 0.0
    for mo in range(1, 13):
        s, var = _mk_s_var(v[mon == mo])
        s_tot += s
        var_tot += var
    return _z_to_p(s_tot, var_tot)


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


def _atlas_item(param, title, unit, group, t, v):
    if len(v) < 24:
        return None
    w = 12
    sm = np.convolve(v, np.ones(w) / w, mode="valid")
    smooth = [[round(float(t[i + w // 2]), 3), round(float(sm[i]), 4)] for i in range(len(sm))]

    years = np.floor(t + 1e-9).astype(int)
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
            return spec, _atlas_item(param, title, unit, group, t, v)
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



def _extra(id_, power, name, unit, group, explain, meaning, limits, start=1981,
           source="NASA POWER / MERRA-2", dataset="MERRA-2 reanalysis via NASA POWER",
           resolution="0.5° × 0.625°, monthly",
           kind="Reanalysis (model-assimilated, not a direct measurement)."):
    return {"id": id_, "power": power, "name": name, "unit": unit, "group": group, "start": start,
            "explain": explain, "meaning": meaning, "limits": limits, "source": source,
            "dataset": dataset, "resolution": resolution, "kind": kind, "ocean_only": False}


EXTRA_VARIABLES = {v["id"]: v for v in [
    _extra("ps", "PS", "Surface pressure", "kPa", "Atmosphere",
           "Air pressure at the surface.",
           "Rising or falling pressure can reflect shifts in circulation and storm tracks.",
           "Pressure trends are small and dominated by natural circulation cycles."),
    _extra("ws10m", "WS10M", "Wind speed at 10 m", "m/s", "Atmosphere",
           "Average wind speed 10 m above the ground.",
           "An increase means windier conditions; a decrease means calmer ones (wind energy, erosion, dust).",
           "Reanalysis winds are smoothed and miss local effects of terrain and coastlines."),
    _extra("solar", "ALLSKY_SFC_SW_DWN", "Solar radiation at the surface", "kWh/m²/day", "Atmosphere",
           "Sunlight reaching the ground under real sky conditions.",
           "More radiation means clearer skies; less means more cloud or aerosols.",
           "Driven by cloud and aerosol changes; changes in the satellite record can affect long trends.",
           start=1984, source="NASA POWER / CERES", dataset="CERES-based product via NASA POWER",
           resolution="1° × 1°, monthly", kind="Satellite-derived estimate, not a ground measurement."),
    _extra("qv2m", "QV2M", "Specific humidity at 2 m", "g/kg", "Water Cycle",
           "Mass of water vapor per kilogram of air near the surface.",
           "Higher humidity means more water vapor in the air, which usually follows warming.",
           "Reanalysis humidity depends on model physics and observation coverage."),
    _extra("rh2m", "RH2M", "Relative humidity at 2 m", "%", "Water Cycle",
           "How close the air is to saturation.",
           "A rise means moister, cloudier air; a fall means drier air and higher drought and fire risk.",
           "Relative humidity also changes with temperature, so trends can be small."),
    _extra("evptrns", "EVPTRNS", "Evapotranspiration energy flux", "MJ/m²/day", "Water Cycle",
           "Energy used to move water from land and plants into the air.",
           "An increase means more water leaving the land; a decrease usually means dry soils or sparse vegetation.",
           "Modeled, not measured. Most meaningful over land."),
    _extra("ts", "TS", "Earth skin temperature", "°C", "Land & Soil",
           "Temperature of the surface itself (ground or sea skin).",
           "A rise means a warmer surface; it often moves faster than air temperature over dry land.",
           "Modeled surface temperature; it can differ from satellite skin temperature."),
    _extra("tsoil1", "TSOIL1", "Soil temperature (top layer)", "°C", "Land & Soil",
           "Temperature of the uppermost soil layer.",
           "A rise means warming soils, which affects crops, permafrost and soil carbon.",
           "Modeled, land only; no data over open ocean."),
    _extra("gwettop", "GWETTOP", "Surface soil wetness", "0–1", "Land & Soil",
           "Fraction of soil pore space filled with water at the surface (0 = dry, 1 = saturated).",
           "Higher values mean wetter surface soil; lower values mean drier soil and drought risk.",
           "Modeled, land only. Surface wetness changes quickly with each rain event."),
    _extra("gwetroot", "GWETROOT", "Root-zone soil wetness", "0–1", "Land & Soil",
           "Fraction of soil pore space filled with water in the root zone (0 = dry, 1 = saturated).",
           "Higher values mean more water available to plants; lower values mean agricultural drought stress.",
           "Modeled, land only; it responds slowly and reflects model assumptions."),
]}


def extra_analyze(var, lat, lon, y0, y1):
    """Same statistics as the original variables, returned in the same JSON shape."""
    try:
        t, v = _fetch(var["power"], lat, lon, y0, y1)
    except Exception as e:
        raise RegionError(f"NASA POWER could not provide {var['name']} ({e.__class__.__name__}). Try again later.")
    if len(v) < 60:
        raise RegionError(f"Not enough {var['name']} data here. Land variables have no data over open ocean.")

    n = len(v)
    mon = np.clip(np.rint((t - np.floor(t + 1e-9)) * 12 + 0.5).astype(int), 1, 12)
    yrs = np.floor(t + 1e-9).astype(int)
    clim = {mo: float(v[mon == mo].mean()) for mo in range(1, 13) if (mon == mo).any()}
    anom = v - np.array([clim[m] for m in mon])                      # seasonal anomalies

    # Linear trend with autocorrelation-adjusted uncertainty (AR(1) effective sample size)
    lr = stats.linregress(t, anom)
    res = anom - (lr.intercept + lr.slope * t)
    r1 = float(np.corrcoef(res[:-1], res[1:])[0, 1]) if n > 3 and np.std(res) > 0 else 0.0
    neff = max(3.0, n * (1 - r1) / (1 + r1)) if r1 > 0 else float(n)
    se = lr.stderr * math.sqrt(n / neff)
    df = neff - 2
    ols_p = float(2 * (1 - stats.t.cdf(abs(lr.slope / se), df))) if se > 0 else 1.0
    tcrit = float(stats.t.ppf(0.975, df))
    ci = [(lr.slope - tcrit * se) * 10, (lr.slope + tcrit * se) * 10]

    # Sen's slope on monthly anomalies
    sen = _sen(t, anom)
    sen_icpt = float(np.median(anom - sen * t))
    t0, t1 = float(t[0]), float(t[-1])

    # Annual mean anomalies (complete years only) and tests
    ax, ay = [], []
    for yr in np.unique(yrs):
        m = yrs == yr
        if m.sum() == 12:
            ax.append(yr + 0.5)
            ay.append(float(anom[m].mean()))
    annual_p = _mann_kendall_p(ay) if len(ay) >= 5 else None
    seasonal_p = _seasonal_mk_p(v, mon)

    first = [int(yrs[0]), int(mon[0])]
    last = [int(yrs[-1]), int(mon[-1])]
    return {
        "stats": {
            "direction": "increasing" if sen > 0 else "decreasing",
            "significant": bool(annual_p is not None and annual_p < 0.05),
            "n_months": int(n), "first": first, "last": last,
            "sen_per_decade": sen * 10, "sen_total_change": sen * (t1 - t0),
            "ols_slope_per_decade": float(lr.slope) * 10, "ols_ci_per_decade": ci,
            "r2": float(lr.rvalue ** 2), "annual_mk_p": annual_p, "seasonal_mk_p": seasonal_p,
            "ols_p": ols_p, "lag1_autocorr": r1,
        },
        "t": [round(float(x), 3) for x in t],
        "values": [round(float(x), 4) for x in v],
        "anomalies": [round(float(x), 4) for x in anom],
        "annual": [[round(x, 2), round(y, 4)] for x, y in zip(ax, ay)],
        "trend_sen": [[round(t0, 3), round(sen_icpt + sen * t0, 4)], [round(t1, 3), round(sen_icpt + sen * t1, 4)]],
        "trend_ols": [[round(t0, 3), round(lr.intercept + lr.slope * t0, 4)],
                      [round(t1, 3), round(lr.intercept + lr.slope * t1, 4)]],
    }
