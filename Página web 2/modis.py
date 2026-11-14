"""NASA AppEEARS point samples for Aqua MODIS. No credentials reach the browser."""
import csv
import io
import math
import os
from collections import defaultdict
from datetime import date, datetime, timezone
from functools import lru_cache
from uuid import UUID

import requests

BASE = "https://appeears.earthdatacloud.nasa.gov/api"
HTTP = requests.Session()
HTTP.headers["User-Agent"] = "EarthTrendDetective/1.0 (NASA Space Apps 2026)"
_TOKEN = None
_EXPIRES = None

MODIS_VARIABLES = {
    "modis_ndvi": {
        "id": "modis_ndvi", "name": "Vegetation (NDVI)", "unit": "index",
        "source": "NASA AppEEARS / Aqua MODIS", "dataset": "MYD13A2.061, NDVI",
        "resolution": "1 km, 16-day composites → monthly", "start": 2002,
        "kind": "Satellite-derived vegetation index",
        "explain": "Greenness of vegetation, from red and near-infrared observations.",
        "meaning": "Increasing NDVI can indicate greener vegetation; decreasing NDVI may indicate vegetation stress.",
        "limits": "Clouds, snow, and surface conditions affect measurements. A point represents a satellite pixel.",
        "provider": "appeears", "product": "MYD13A2.061", "suffix": "NDVI", "qa": "pixel_reliability",
    },
    "modis_evi": {
        "id": "modis_evi", "name": "Vegetation (EVI)", "unit": "index",
        "source": "NASA AppEEARS / Aqua MODIS", "dataset": "MYD13A2.061, EVI",
        "resolution": "1 km, 16-day composites → monthly", "start": 2002,
        "kind": "Satellite-derived vegetation index",
        "explain": "Enhanced vegetation index, less prone to some atmospheric and canopy effects than NDVI.",
        "meaning": "Trends indicate changing vegetation activity, not a direct biomass measurement.",
        "limits": "Clouds, snow, seasonal coverage, and surface conditions affect measurements.",
        "provider": "appeears", "product": "MYD13A2.061", "suffix": "EVI", "qa": "pixel_reliability",
    },
    "modis_lst": {
        "id": "modis_lst", "name": "Land surface temperature (day)", "unit": "°C",
        "source": "NASA AppEEARS / Aqua MODIS", "dataset": "MYD11A2.061, LST_Day_1km",
        "resolution": "1 km, 8-day composites → monthly", "start": 2002,
        "kind": "Satellite-derived land skin temperature (not air temperature)",
        "explain": "Temperature of the land surface at the satellite overpass.",
        "meaning": "A positive trend means warmer land surfaces at observed overpass times.",
        "limits": "Not 2 m air temperature. Mostly clear-sky retrievals; cloud gaps can bias trends.",
        "provider": "appeears", "product": "MYD11A2.061", "suffix": "LST_Day_1km", "qa": "QC_Day",
    },
}


class ModisError(Exception):
    pass


def _token():
    global _TOKEN, _EXPIRES
    # AppEEARS_TOKEN can be supplied as a Codespaces secret instead of a password.
    static = os.getenv("APPEEARS_TOKEN", "").strip()
    if static:
        return static
    if _TOKEN and _EXPIRES and datetime.now(timezone.utc) < _EXPIRES:
        return _TOKEN
    username, password = os.getenv("EARTHDATA_USERNAME"), os.getenv("EARTHDATA_PASSWORD")
    if not username or not password:
        raise ModisError("Configure APPEEARS_TOKEN or EARTHDATA_USERNAME and EARTHDATA_PASSWORD as server secrets.")
    try:
        r = HTTP.post(BASE + "/login", auth=(username, password), timeout=(10, 30))
        r.raise_for_status()
        body = r.json()
        _TOKEN = body["token"]
        _EXPIRES = datetime.fromisoformat(body["expiration"].replace("Z", "+00:00"))
        return _TOKEN
    except (requests.RequestException, ValueError, KeyError) as exc:
        raise ModisError("NASA Earthdata authentication failed. Check the server credentials.") from exc


def _call(method, endpoint, **kwargs):
    try:
        r = HTTP.request(method, BASE + endpoint, headers={"Authorization": "Bearer " + _token()},
                         timeout=(10, 65), **kwargs)
        if r.status_code in (401, 403):
            raise ModisError("NASA AppEEARS authentication expired or was denied. Renew APPEEARS_TOKEN.")
        r.raise_for_status()
        return r
    except requests.RequestException as exc:
        code = getattr(getattr(exc, "response", None), "status_code", None)
        raise ModisError(f"NASA AppEEARS request failed (HTTP {code or 'network error'}).") from exc


@lru_cache(maxsize=4)
def _layers(product):
    try:
        r = HTTP.get(BASE + "/product/" + product, timeout=(10, 30))
        r.raise_for_status()
        result = r.json()
        if not isinstance(result, dict):
            raise ValueError("Unexpected layers response")
        return result
    except (requests.RequestException, ValueError) as exc:
        raise ModisError("Could not retrieve the MODIS product layer catalog.") from exc


def _layer_name(layers, suffix):
    matches = [name for name, info in layers.items()
               if name.lower().endswith(suffix.lower()) and info.get("Available", True)]
    if not matches:
        raise ModisError(f"Layer ending in {suffix} is unavailable in the selected NASA product.")
    return min(matches, key=len)


def submit_point(variable, lat, lon, start_year, end_year):
    layers = _layers(variable["product"])
    science = _layer_name(layers, variable["suffix"])
    chosen = [{"product": variable["product"], "layer": science}]
    # Request QA as an additional layer where available; never silently treat all pixels as valid.
    qa = next((name for name, info in layers.items()
               if name.lower().endswith(variable["qa"].lower()) and info.get("Available", True)), None)
    if qa:
        chosen.append({"product": variable["product"], "layer": qa})
    payload = {
        "task_type": "point",
        "task_name": f"EarthTrend-{variable['id']}-{date.today():%Y%m%d}",
        "params": {
            "dates": [{"startDate": f"01-01-{start_year}", "endDate": f"12-31-{end_year}"}],
            "layers": chosen,
            "coordinates": [{"latitude": lat, "longitude": lon, "id": "earthtrend-point"}],
        },
    }
    r = _call("POST", "/task", json=payload)
    try:
        task = r.json()
        return {"task_id": str(UUID(task["task_id"])), "status": task.get("status", "pending")}
    except (ValueError, KeyError, TypeError) as exc:
        raise ModisError("NASA returned an unexpected task response.") from exc


def get_task(task_id):
    return _call("GET", "/task/" + str(UUID(task_id))).json()


def _column(columns, suffix):
    # AppEEARS output headers generally resemble MYD13A2_061__1_km_16_days_NDVI.
    return next((name for name in columns if name.lower().endswith("_" + suffix.lower())
                 or name.lower() == suffix.lower()), None)


def _parse_date(value):
    for format_ in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%j"):
        try:
            return datetime.strptime(value.strip().split("T")[0], format_).date()
        except ValueError:
            pass
    raise ValueError("Unrecognized MODIS observation date")


def parse_point_csv(content, variable):
    """Clean a single-point AppEEARS CSV and aggregate available composite observations by month."""
    reader = csv.DictReader(io.StringIO(content.decode("utf-8-sig")))
    cols = reader.fieldnames or []
    data_col = _column(cols, variable["suffix"])
    date_col = next((c for c in cols if c.lower() == "date"), None)
    qa_col = _column(cols, variable["qa"])
    if not data_col or not date_col:
        raise ModisError("AppEEARS CSV has unexpected columns; the requested layer or Date was not found.")
    values = defaultdict(list)
    rejected = 0
    for row in reader:
        try:
            when = _parse_date(row[date_col])
            value = float(row[data_col])
            if not math.isfinite(value) or value <= -900 or abs(value) >= 30000:
                continue
            if qa_col and row.get(qa_col) not in ("", None):
                qa = int(float(row[qa_col]))
                if variable["id"] == "modis_lst" and (qa & 3) != 0:
                    rejected += 1
                    continue
                if variable["id"] != "modis_lst" and qa not in (0, 1):
                    rejected += 1
                    continue
            if variable["id"] == "modis_lst":
                if value > 1000:  # raw MODIS LST; scaled CSV values are already Kelvin
                    value *= 0.02
                if 150 <= value <= 400:
                    value -= 273.15
                if not -100 <= value <= 100:
                    continue
            else:
                if abs(value) > 1.2 and abs(value) <= 10000:
                    value *= 0.0001  # raw vegetation index, if not already scaled
                if not -1 <= value <= 1:
                    continue
            values[(when.year, when.month)].append(value)
        except (ValueError, TypeError, KeyError):
            continue
    if not values:
        raise ModisError("No valid MODIS observations remained for the selected point and dates.")
    notes = ["Aqua MODIS point pixel (not an average over the surrounding region)."]
    notes.append(f"Quality layer: {'applied' if qa_col else 'not provided in CSV; no QA filter applied'}.")
    if qa_col:
        notes.append(f"Excluded {rejected} low-quality observations.")
    return {key: sum(v) / len(v) for key, v in values.items()}, notes


def fetch_point_monthly(task_id, variable):
    response = _call("GET", "/bundle/" + str(UUID(task_id))).json()
    files = response.get("files", [])
    # Different products may be present in one task; choose its own CSV.
    product = variable["product"].split(".")[0].lower()
    candidate = next((file for file in files if file.get("file_type") == "csv"
                      and product in file.get("file_name", "").lower()), None)
    if candidate is None:
        raise ModisError("The completed AppEEARS task contains no CSV for this MODIS product.")
    if int(candidate.get("file_size") or 0) > 8_000_000:
        raise ModisError("The sample exceeds the 8 MB limit for this demo.")
    csv_response = _call("GET", "/bundle/" + str(UUID(task_id)) + "/" + str(UUID(candidate["file_id"])))
    if len(csv_response.content) > 8_000_000:
        raise ModisError("The sample is too large for this demo.")
    return parse_point_csv(csv_response.content, variable)
