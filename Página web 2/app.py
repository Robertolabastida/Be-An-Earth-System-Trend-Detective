import csv
import math
import os
import re
import time
import zipfile
from datetime import date
from urllib.parse import urlencode


from flask import Flask, Response, abort, jsonify, render_template, request, send_from_directory
from werkzeug.utils import safe_join

from analysis import AnalysisError, analyze
from data_sources import VARIABLES, DataError, fetch_monthly
from region_data import EXTRA_VARIABLES, RegionError, extra_analyze, region_report

app = Flask(__name__)
app.config["TEMPLATES_AUTO_RELOAD"] = True      # re-read gt.html on every visit
CACHE, TTL = {}, 6 * 3600
DEFAULT_START, DEFAULT_END = 2003, 2025         # default analysis period

# ---------------------------------------------------------------------------
# Local data folders (GPM precipitation, MERRA-2, GLDAS plots and CSV files).
# By default they are looked up next to this file. Change the paths here, or set
# the PRECIP_DIR / STATS_DIR environment variables, if your folders live elsewhere.
# ---------------------------------------------------------------------------
BASE = os.path.dirname(os.path.abspath(__file__))
DATA_ROOTS = {
    "precip": os.environ.get("PRECIP_DIR", os.path.join(BASE, "Precipitation_data")),
    "stats": os.environ.get("STATS_DIR", os.path.join(BASE, "Statistical_Analysis")),
}


@app.after_request
def no_cache_html(resp):
    if resp.mimetype == "text/html":
        resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/")
def index():
    return render_template("gt.html")


@app.route("/api/variables")
def variables():
    # original variables + the extra NASA POWER variables (humidity, wind, soil, ...)
    return jsonify(list(VARIABLES.values()) + list(EXTRA_VARIABLES.values()))


@app.route("/api/series")
def series():
    var = VARIABLES.get(request.args.get("var", "")) or EXTRA_VARIABLES.get(request.args.get("var", ""))
    if var is None:
        return jsonify(error="Unknown variable."), 400
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
        y0 = int(request.args.get("start", DEFAULT_START))
        y1 = int(request.args.get("end", DEFAULT_END))
    except (KeyError, ValueError):
        return jsonify(error="Provide valid lat, lon, start and end."), 400
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90):
        return jsonify(error="Latitude must be between -90 and 90."), 400
    lon = ((lon + 180) % 360) - 180

    notes, today = [], date.today().year
    if y0 < var["start"]:
        notes.append(f"{var['name']} data begin in {var['start']}; the start year was adjusted.")
        y0 = var["start"]
    y1 = min(y1, today)
    if y1 - y0 < 9:
        return jsonify(error="Select at least 10 years for a meaningful trend."), 400

    key = (var["id"], round(lat, 2), round(lon, 2), y0, y1)
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        payload = hit[1]
    else:
        try:
            if var["id"] in EXTRA_VARIABLES:
                result = extra_analyze(var, lat, lon, y0, y1)
            else:
                result = analyze(fetch_monthly(var, lat, lon, y0, y1))
        except DataError as e:
            return jsonify(error=str(e)), 502
        except RegionError as e:
            return jsonify(error=str(e)), 502
        except AnalysisError as e:
            return jsonify(error=str(e)), 422
        payload = {"variable": var, "lat": lat, "lon": lon, "start": y0, "end": y1, **result}
        CACHE[key] = (time.time(), payload)
    return jsonify({**payload, "notes": notes})


# ---------------------------------------------------------------------------
# Climate Atlas: charts for ANY selected place (NASA POWER, see region_data.py)
# ---------------------------------------------------------------------------
@app.route("/api/region")
def region():
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
        y0 = max(1981, int(request.args.get("start", DEFAULT_START)))
        y1 = min(date.today().year, int(request.args.get("end", DEFAULT_END)))
    except (KeyError, ValueError):
        return jsonify(error="Provide valid lat, lon, start and end."), 400
    if not (math.isfinite(lat) and math.isfinite(lon) and -90 <= lat <= 90):
        return jsonify(error="Latitude must be between -90 and 90."), 400
    if y1 - y0 < 9:
        return jsonify(error="Select at least 10 years."), 400
    lon = ((lon + 180) % 360) - 180
    try:
        return jsonify(region_report(lat, lon, y0, y1))
    except RegionError as e:
        return jsonify(error=str(e)), 502


# ---------------------------------------------------------------------------
# Local data: discovery, images, CSV series (kept available, no longer used by the panel)
# ---------------------------------------------------------------------------
SKIP_DIRS = {"__pycache__", ".git", "node_modules", "venv", ".venv"}
IMG_EXT = (".png", ".jpg", ".jpeg")
SOURCES = [
    ("gpm", "GPM precipitation",
     "Outputs of the GPM precipitation analysis for Ensenada: accumulation, intensity, spatial distribution and temporal variation."),
    ("merra2", "MERRA-2",
     "MERRA-2 reanalysis variables: specific humidity, sea-level pressure, air temperature, aerosol optical thickness and wind speed."),
    ("gldas", "GLDAS",
     "GLDAS-2.1 land-surface model: soil moisture, soil temperature, runoff and evapotranspiration."),
    ("other", "Other", "Other plots and tables found in the data folders."),
]
KNOWN_TITLES = {
    "plot_qv2m": "Specific humidity at 2 m (QV2M)",
    "plot_slp": "Sea-level pressure (SLP)",
    "plot_t2m": "Air temperature at 2 m (T2M)",
    "plot_totexttau": "Total aerosol extinction AOT (TOTEXTTAU)",
    "plot_wind_speed": "Wind speed",
}
LOCAL = {"t": 0.0, "data": None}


def classify(path):
    p = path.lower()
    name = os.path.basename(p)
    if "gldas" in p:
        return "gldas"
    if "gpm" in p or "precipitation" in p:
        return "gpm"
    if "merra" in p or "m2t" in name or "/figures/" in "/" + p:
        return "merra2"
    return "other"


def pretty(name):
    stem = os.path.splitext(os.path.basename(name))[0]
    if stem.lower() in KNOWN_TITLES:
        return KNOWN_TITLES[stem.lower()]
    m = re.match(r"g4\.areaAvgTimeSeries\.([A-Za-z0-9_]+)\.(\d{4})\d{4}-(\d{4})\d{4}", stem)
    if m:                                   # Giovanni area-averaged time series
        return f"{m.group(1).replace('_', ' ')} · area-averaged series {m.group(2)}–{m.group(3)}"
    t = re.sub(r"^\d+[a-z]?_", "", stem)
    t = re.sub(r"^plot_", "", t, flags=re.I).replace("_", " ")
    return t[:1].upper() + t[1:]


def discover():
    found, seen = {}, set()

    def add(src, kind, title, shown, url, size):
        key = (src, kind, os.path.basename(shown).lower(), size)
        if key in seen:                     # same file copied into two folders
            return
        seen.add(key)
        found.setdefault(src, []).append({"kind": kind, "title": title, "file": shown, "url": url})

    for rk, root in DATA_ROOTS.items():
        if not os.path.isdir(root):
            continue
        for dirpath, dirs, files in os.walk(root):
            dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS)
            for fn in sorted(files):
                full = os.path.join(dirpath, fn)
                rel = os.path.relpath(full, root).replace("\\", "/")
                low = fn.lower()
                try:
                    size = os.path.getsize(full)
                except OSError:
                    continue
                if low.endswith(IMG_EXT):
                    add(classify(rel), "png", pretty(fn), rel,
                        "/api/local/file?" + urlencode({"root": rk, "path": rel}), size)
                elif low.endswith(".csv"):
                    add(classify(rel), "csv", pretty(fn), rel,
                        "/api/local/csv?" + urlencode({"root": rk, "path": rel}), size)
                elif low.endswith(".zip"):          # plots stored inside the result zips
                    try:
                        with zipfile.ZipFile(full) as z:
                            for info in z.infolist():
                                n = info.filename
                                if n.lower().endswith(IMG_EXT) and not n.startswith("__MACOSX"):
                                    add(classify(rel + "/" + n), "png", pretty(n), f"{rel} → {n}",
                                        "/api/local/zip?" + urlencode({"root": rk, "path": rel, "member": n}),
                                        info.file_size)
                    except (zipfile.BadZipFile, OSError, RuntimeError):
                        pass

    sources = []
    for sid, name, note in SOURCES:
        items = sorted(found.get(sid, []), key=lambda i: (i["kind"] != "png", i["file"].lower()))
        if items:
            sources.append({"id": sid, "name": name, "note": note, "items": items})
    return {"sources": sources, "roots": {k: os.path.isdir(v) for k, v in DATA_ROOTS.items()}}


def _root_arg():
    root = DATA_ROOTS.get(request.args.get("root", ""))
    if not root or not os.path.isdir(root):
        abort(404)
    return root


@app.route("/api/local")
def local_index():
    if LOCAL["data"] is None or time.time() - LOCAL["t"] > 30:
        LOCAL.update(t=time.time(), data=discover())
    return jsonify(LOCAL["data"])


@app.route("/api/local/file")
def local_file():
    rel = request.args.get("path", "")
    if not rel.lower().endswith(IMG_EXT):
        abort(404)
    return send_from_directory(_root_arg(), rel)        # refuses paths outside the folder


@app.route("/api/local/zip")
def local_zip():
    root, rel, member = _root_arg(), request.args.get("path", ""), request.args.get("member", "")
    full = safe_join(root, rel)
    if not full or not full.lower().endswith(".zip") or not os.path.isfile(full) or not member.lower().endswith(IMG_EXT):
        abort(404)
    try:
        with zipfile.ZipFile(full) as z:
            if member not in z.namelist():
                abort(404)
            data = z.read(member)
    except (zipfile.BadZipFile, RuntimeError, NotImplementedError, OSError):
        abort(404)
    return Response(data, mimetype="image/png" if member.lower().endswith(".png") else "image/jpeg")


DATE_RE = re.compile(r"^\s*(\d{4})-(\d{2})(?:-(\d{2}))?")


def _num(text):
    try:
        v = float(text)
    except (TypeError, ValueError):
        return None
    return v if math.isfinite(v) and abs(v) < 1e30 and v > -9990 else None   # -9999 = fill value


def _read_rows(path):
    with open(path, encoding="utf-8-sig", errors="replace", newline="") as f:
        return [r for r in csv.reader(f) if any(c.strip() for c in r)]


def _parse_csv(path):
    rows = _read_rows(path)
    if not rows:
        raise ValueError("This file is empty.")

    header, data = None, None
    for i in range(len(rows) - 1):          # a header row followed by rows that start with a date
        if len(rows[i]) >= 2 and not DATE_RE.match(rows[i][0]) and DATE_RE.match(rows[i + 1][0]):
            header, data = rows[i], rows[i + 1:]
            break
    if header is None:                      # no dates: maybe "year" (and "month") columns
        low = [h.strip().lower() for h in rows[0]]
        if "year" in low and len(rows) > 2:
            header, data = rows[0], rows[1:]

    if header is not None:
        low = [h.strip().lower() for h in header]
        yi = low.index("year") if "year" in low else None
        mi = low.index("month") if "month" in low else None
        xcols = {0} if (DATE_RE.match(data[0][0] or "") and yi is None) else {c for c in (yi, mi) if c is not None}

        def xval(r):
            if yi is None:
                m = DATE_RE.match(r[0])
                return int(m.group(1)) + ((int(m.group(2)) - 1) + ((int(m.group(3) or 1) - 1) / 31)) / 12 if m else None
            y = _num(r[yi]) if yi < len(r) else None
            mo = _num(r[mi]) if mi is not None and mi < len(r) else 1
            return None if y is None else y + ((mo or 1) - 1) / 12

        cols = []
        for c, name in enumerate(header):
            if c in xcols:
                continue
            vals = [_num(r[c]) if c < len(r) else None for r in data]
            if sum(v is not None for v in vals) >= 0.6 * len(vals):
                cols.append((name.strip() or f"column {c + 1}", vals))
        xs = [xval(r) for r in data]
        if cols and sum(x is not None for x in xs) >= 0.6 * len(xs):
            step = max(1, len(data) // 6000)
            series = [{"name": n, "points": [[round(x, 4), round(v, 5)] for x, v in zip(xs, vals) if x is not None and v is not None][::step]}
                      for n, vals in cols[:6]]
            return {"kind": "series", "x_label": "Year", "series": series, "rows": len(data)}

    head = rows[0][:12]                     # fallback: show the table
    return {"kind": "table", "columns": head, "rows": [r[:12] for r in rows[1:201]], "total": len(rows) - 1}


@app.route("/api/local/csv")
def local_csv():
    full = safe_join(_root_arg(), request.args.get("path", ""))
    if not full or not full.lower().endswith(".csv") or not os.path.isfile(full):
        abort(404)
    try:
        return jsonify(_parse_csv(full))
    except (ValueError, OSError, IndexError) as e:
        return jsonify(error=f"Could not read this CSV ({e})."), 422


if __name__ == "__main__":
    print("Template in use:", os.path.join(app.root_path, "templates", "gt.html"))
    for k, v in DATA_ROOTS.items():
        print(f"Data folder [{k}]:", v, "(found)" if os.path.isdir(v) else "(NOT found)")
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)