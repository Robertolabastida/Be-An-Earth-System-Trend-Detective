import math
import os
import time
from datetime import date

from flask import Flask, jsonify, render_template, request
from dotenv import load_dotenv

from analysis import AnalysisError, analyze
from data_sources import VARIABLES, DataError, fetch_monthly
from modis import MODIS_VARIABLES, ModisError, submit_point, get_task, fetch_point_monthly

load_dotenv()

app = Flask(__name__)
CACHE, TTL = {}, 6 * 3600
MODIS_TASKS = {}


@app.route("/")
def index():
    return render_template("gt.html")


@app.route("/api/variables")
def variables():
    return jsonify(list(VARIABLES.values()) + list(MODIS_VARIABLES.values()))


@app.route("/api/series")
def series():
    var = VARIABLES.get(request.args.get("var", ""))
    if var is None:
        return jsonify(error="Unknown variable."), 400
    try:
        lat, lon = float(request.args["lat"]), float(request.args["lon"])
        y0 = int(request.args.get("start", 1985))
        y1 = int(request.args.get("end", date.today().year))
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
    if y0 > y1:
        return jsonify(error="Start year must not exceed end year."), 400
    if y1 - y0 < 9:
        return jsonify(error="Select at least 10 years for a meaningful trend."), 400

    key = (var["id"], round(lat, 2), round(lon, 2), y0, y1)
    hit = CACHE.get(key)
    if hit and time.time() - hit[0] < TTL:
        payload = hit[1]
    else:
        try:
            result = analyze(fetch_monthly(var, lat, lon, y0, y1))
        except DataError as e:
            return jsonify(error=str(e)), 502
        except AnalysisError as e:
            return jsonify(error=str(e)), 422
        payload = {"variable": var, "lat": lat, "lon": lon, "start": y0, "end": y1, **result}
        CACHE[key] = (time.time(), payload)
    return jsonify({**payload, "notes": notes})



@app.post("/api/modis/tasks")
def submit_modis_task():
    params = request.get_json(silent=True) or {}
    var = MODIS_VARIABLES.get(params.get("var"))
    if var is None:
        return jsonify(error="Unknown Aqua MODIS variable."), 400
    try:
        lat, lon = float(params["lat"]), float(params["lon"])
        y0, y1 = int(params["start"]), int(params["end"])
    except (KeyError, ValueError, TypeError):
        return jsonify(error="Provide valid coordinates and years."), 400
    if not math.isfinite(lat) or not math.isfinite(lon) or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return jsonify(error="Coordinates are outside geographic bounds."), 400
    if y0 < 2002 or y1 > date.today().year or y1 < y0 or y1 - y0 < 9:
        return jsonify(error="Choose at least 10 years between 2002 and the current year."), 400
    try:
        task = submit_point(var, lat, lon, y0, y1)
    except ModisError as exc:
        return jsonify(error=str(exc)), 502
    MODIS_TASKS[task["task_id"]] = {"variable": var, "lat": lat, "lon": lon, "start": y0, "end": y1}
    return jsonify(task), 202


@app.get("/api/modis/tasks/<uuid:task_id>")
def modis_task_status(task_id):
    task_id = str(task_id)
    meta = MODIS_TASKS.get(task_id)
    if meta is None:
        return jsonify(error="Task is not tracked by this server. Submit a new request."), 404
    if "result" in meta:
        return jsonify(meta["result"])
    try:
        task = get_task(task_id)
        state = task.get("status", "unknown")
        if state in ("error", "cancelled", "expired"):
            return jsonify(status=state, error="NASA could not finish this task. Try a shorter range."), 502
        if state != "done":
            return jsonify(status=state, task_id=task_id)
        data, notes = fetch_point_monthly(task_id, meta["variable"])
        result = analyze(data)
    except (ModisError, AnalysisError) as exc:
        return jsonify(error=str(exc)), 502
    except (ValueError, TypeError):
        return jsonify(error="NASA returned an unexpected task response."), 502
    payload = {**meta, "task_id": task_id, "status": "done", "notes": notes, **result}
    meta["result"] = payload
    return jsonify(payload)


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5000)