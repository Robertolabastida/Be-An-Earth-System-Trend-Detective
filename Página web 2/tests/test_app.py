"""Offline tests; never require personal Earthdata credentials or live NASA calls."""
import math
import os
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app
import modis
from analysis import analyze


def test_products_list_includes_existing_sources_and_modis():
    response = app.app.test_client().get("/api/variables")
    assert response.status_code == 200
    ids = {item["id"] for item in response.get_json()}
    assert {"t2m", "precip", "sst", "modis_ndvi", "modis_evi", "modis_lst"} <= ids


def test_modis_rejects_invalid_years_without_calling_nasa():
    client = app.app.test_client()
    response = client.post("/api/modis/tasks", json={
        "var": "modis_ndvi", "lat": 31.87, "lon": -116.6, "start": 1981, "end": 2025,
    })
    assert response.status_code == 400


def test_modis_submits_then_returns_statistical_analysis():
    app.MODIS_TASKS.clear()
    client = app.app.test_client()
    task_id = "c1d2e3f4-5678-4123-9234-112233445566"
    example = {(year, month): 0.20 + (year - 2010) * .003 + month * .0002
               for year in range(2010, 2026) for month in range(1, 13)}
    with patch.object(app, "submit_point", return_value={"task_id": task_id, "status": "pending"}):
        started = client.post("/api/modis/tasks", json={
            "var": "modis_ndvi", "lat": 31.87, "lon": -116.6, "start": 2010, "end": 2025,
        })
    assert started.status_code == 202
    with patch.object(app, "get_task", return_value={"status": "done"}), \
         patch.object(app, "fetch_point_monthly", return_value=(example, ["QA applied."])):
        result = client.get("/api/modis/tasks/" + task_id)
    assert result.status_code == 200
    data = result.get_json()
    assert data["status"] == "done"
    assert len(data["values"]) == 192
    assert data["stats"]["ols_slope_per_decade"] > 0
    assert data["notes"] == ["QA applied."]


def test_point_csv_uses_qa_and_skips_fill_values():
    csv_data = (
        "Date,MYD13A2_061__1_km_16_days_NDVI,MYD13A2_061__1_km_16_days_pixel_reliability\n"
        "2015-01-01,0.50,0\n"
        "2015-01-17,0.80,3\n"
        "2015-02-01,-9999,0\n"
        "2015-03-01,6500,1\n"
    ).encode()
    data, notes = modis.parse_point_csv(csv_data, modis.MODIS_VARIABLES["modis_ndvi"])
    assert data == {(2015, 1): 0.5, (2015, 3): 0.65}
    assert "Excluded 1" in notes[-1]


def test_lst_is_converted_from_kelvin_to_celsius():
    csv_data = "Date,MYD11A2_061_LST_Day_1km\n2015-01-01,300\n".encode()
    data, _ = modis.parse_point_csv(csv_data, modis.MODIS_VARIABLES["modis_lst"])
    assert math.isclose(data[(2015, 1)], 26.85, abs_tol=1e-8)


def test_appeears_task_uses_real_product_layers():
    layers = {
        "_1_km_16_days_NDVI": {"Available": True},
        "_1_km_16_days_pixel_reliability": {"Available": True},
    }
    sample = {"task_id": "c1d2e3f4-5678-4123-9234-112233445566", "status": "pending"}
    with patch.object(modis, "_layers", return_value=layers), \
         patch.object(modis, "_call") as request:
        request.return_value.json.return_value = sample
        result = modis.submit_point(modis.MODIS_VARIABLES["modis_ndvi"], 31.87, -116.6, 2010, 2025)
    assert result["status"] == "pending"
    payload = request.call_args.kwargs["json"]
    assert payload["task_type"] == "point"
    assert payload["params"]["layers"][0]["product"] == "MYD13A2.061"
    assert len(payload["params"]["layers"]) == 2
    assert payload["params"]["coordinates"][0]["longitude"] == -116.6


def test_constant_series_produces_finite_statistics():
    data = {(year, month): 5.0 for year in range(2010, 2025) for month in range(1, 13)}
    result = analyze(data)
    assert result["stats"]["ols_slope_per_year"] == 0.0
    assert result["stats"]["ols_p"] == 1.0
    assert result["stats"]["significant"] is False
    assert math.isfinite(result["stats"]["r2"])
