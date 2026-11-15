import math
import os
import time
from datetime import date

from flask import Flask, jsonify, render_template, request

from analysis import AnalysisError, analyze
from data_sources import VARIABLES, DataError, fetch_monthly

app = Flask(__name__)
CACHE, TTL = {}, 6 * 3600
app.config["TEMPLATES_AUTO_RELOAD"] = True      # relee gt.html en cada visita
app.config["SEND_FILE_MAX_AGE_DEFAULT"] = 0     # sin caché para gt.css y gt.js

@app.after_request
def no_cache(resp):
    resp.headers["Cache-Control"] = "no-store"
    return resp

print("Plantilla en uso:", os.path.join(app.root_path, "templates", "gt.html"))


@app.route("/")
def index():
    return render_template("gt.html")


@app.route("/api/variables")
def variables():
    return jsonify(list(VARIABLES.values()))


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


if __name__ == "__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG") == "1", port=5001)