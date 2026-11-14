"""Real data adapters. Each returns {(year, month): value}. No simulated data anywhere."""
import csv
import io
from collections import defaultdict
from datetime import date

import requests

HTTP = requests.Session()
HTTP.headers["User-Agent"] = "EarthTrendDetective/1.0 (NASA Space Apps 2026)"
TIMEOUT = 90
POWER_URL = "https://power.larc.nasa.gov/api/temporal/monthly/point"
OISST_URL = "https://coastwatch.pfeg.noaa.gov/erddap/griddap/ncdcOisst21Agg_LonPM180.csv"


class DataError(Exception):
    pass


VARIABLES = {
    "t2m": {
        "id": "t2m", "name": "Air temperature (2 m)", "unit": "°C", "source": "NASA POWER / MERRA-2",
        "dataset": "POWER monthly point API, parameter T2M", "resolution": "0.5° × 0.625°, monthly",
        "start": 1981, "kind": "Reanalysis (model-assimilated, not a direct measurement)",
        "explain": "Temperature of the air about 2 meters above the surface.",
        "meaning": "A rise suggests regional warming; a fall suggests cooling.",
        "limits": "Grid-cell average (~50 km); reanalysis can carry biases over complex terrain.",
        "provider": "power", "param": "T2M", "ocean_only": False,
    },
    "precip": {
        "id": "precip", "name": "Precipitation", "unit": "mm/day", "source": "NASA POWER / MERRA-2",
        "dataset": "POWER monthly point API, parameter PRECTOTCORR", "resolution": "0.5° × 0.625°, monthly",
        "start": 1981, "kind": "Reanalysis (bias-corrected model product)",
        "explain": "Average daily rainfall and snowfall water equivalent.",
        "meaning": "An increase means wetter conditions; a decrease means drier ones (flood or drought risk).",
        "limits": "Precipitation is the least reliable reanalysis variable; trends are highly variable.",
        "provider": "power", "param": "PRECTOTCORR", "ocean_only": False,
    },
    "sst": {
        "id": "sst", "name": "Sea surface temperature", "unit": "°C", "source": "NOAA OISST v2.1",
        "dataset": "ERDDAP ncdcOisst21Agg_LonPM180 (doi:10.25921/RE9P-PT57)", "resolution": "0.25°, daily → monthly mean",
        "start": 1982, "kind": "Satellite + in situ analysis (optimum interpolation)",
        "explain": "Temperature of the top layer of the ocean.",
        "meaning": "A rise indicates ocean warming, affecting marine life, storms and climate patterns.",
        "limits": "Ocean only (land points have no data); 0.25° grid; daily blended analysis.",
        "provider": "oisst", "param": "sst", "ocean_only": True,
    },
}


def fetch_monthly(var, lat, lon, y0, y1):
    if var["provider"] == "power":
        return _power(var, lat, lon, y0, y1)
    return _oisst(var, lat, lon, y0, y1)


def _power(var, lat, lon, y0, y1):
    p = {"parameters": var["param"], "community": "AG", "longitude": round(lon, 4),
         "latitude": round(lat, 4), "start": y0, "end": y1, "format": "JSON"}
    try:
        r = HTTP.get(POWER_URL, params=p, timeout=TIMEOUT)
        r.raise_for_status()
        raw = r.json()["properties"]["parameter"][var["param"]]
    except (requests.RequestException, KeyError, ValueError) as e:
        raise DataError(f"NASA POWER is unavailable or rejected the request ({e}).")
    out = {}
    for k, v in raw.items():
        if len(k) == 6 and k[4:] != "13" and v is not None and v > -900:  # 13 = annual mean; -999 = fill
            out[(int(k[:4]), int(k[4:]))] = float(v)
    return out


def _oisst(var, lat, lon, y0, y1):
    q = (f"sst[({y0}-01-01T12:00:00Z):1:({y1}-12-31T12:00:00Z)]"
         f"[(0.0):1:(0.0)][({lat}):1:({lat})][({lon}):1:({lon})]")
    try:
        r = HTTP.get(OISST_URL + "?" + q, timeout=TIMEOUT)
        if r.status_code == 404:
            raise DataError("No SST data for this period/location. Is the point over land?")
        r.raise_for_status()
    except requests.RequestException as e:
        raise DataError(f"NOAA ERDDAP is unavailable ({e}).")
    rows = list(csv.reader(io.StringIO(r.text)))[2:]  # row 0 = header, row 1 = units
    acc = defaultdict(list)
    for row in rows:
        try:
            v = float(row[4])
        except (ValueError, IndexError):
            continue
        if v == v:  # skip NaN
            acc[(int(row[0][:4]), int(row[0][5:7]))].append(v)
    # keep only months with near-complete coverage
    return {k: sum(v) / len(v) for k, v in acc.items() if len(v) >= 20}