import io
import os
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import requests
import numpy as np

load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
METEO_USER = os.getenv("METEOMATICS_USER")
METEO_PWD = os.getenv("METEOMATICS_PASSWORD")


def get_meteomatics_auth():
    if not METEO_USER or not METEO_PWD:
        raise HTTPException(
            status_code=503,
            detail="Meteomatics credentials are not configured. Set METEOMATICS_USER and METEOMATICS_PASSWORD.",
        )
    return METEO_USER, METEO_PWD

app = FastAPI()

# Habilitar CORS (apertura básica para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"]
)

@app.get("/api/time-series")
def get_time_series(param: str, lat: float, lon: float, start: str, end: str):
    """
    Recupera datos de Meteomatics en formato JSON para una serie de tiempo.
    Calcula pendiente y R^2 de una regresión lineal sobre los valores.
    """
    # Formato del rango de tiempo (por horas diarias)
    time_range = f"{start}--{end}:PT24H"
    url = f"https://api.meteomatics.com/{time_range}/{param}/{lat},{lon}/json"

    try:
        res = requests.get(url, auth=get_meteomatics_auth(), timeout=10)
        res.raise_for_status()
        json_data = res.json()
    except (requests.RequestException, ValueError) as e:
        raise HTTPException(status_code=502, detail=f"Error calling Meteomatics API: {str(e)}")

    # Extraer fechas y valores
    try:
        if not isinstance(json_data, dict):
            raise ValueError("Expected a JSON object")

        if "data" in json_data:
            data_entries = json_data["data"]
            if not isinstance(data_entries, list) or not data_entries:
                raise ValueError("No data entries in response")
            data_entry = data_entries[0]
        else:
            # Compatibilidad con respuestas que usan el nombre del parámetro como clave.
            data_entry = next(iter(json_data.values()))[0]

        coords = data_entry["coordinates"]
        if not coords:
            raise ValueError("No coordinates in response")
        date_entries = coords[0]["dates"]
        dates = [entry["date"] for entry in date_entries]
        values = [entry["value"] for entry in date_entries]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected response format: {str(e)}")

    # Calcular regresión lineal (pendiente y R^2)
    slope = intercept = r2 = None
    if len(values) > 1:
        x = np.arange(len(values))
        y = np.array(values, dtype=float)
        # Ajuste lineal
        slope, intercept = np.polyfit(x, y, 1)
        # Calcular R^2
        y_pred = slope * x + intercept
        ss_res = np.sum((y - y_pred) ** 2)
        ss_tot = np.sum((y - np.mean(y)) ** 2)
        r2 = 1 - ss_res/ss_tot if ss_tot != 0 else None

    return {
        "dates": dates,
        "values": values,
        "slope": float(slope) if slope is not None else None,
        "intercept": float(intercept) if intercept is not None else None,
        "r2": float(r2) if r2 is not None else None
    }

@app.get("/api/heatmap")
def get_heatmap(param: str, latN: float, lonW: float, latS: float, lonE: float, time: str):
    """
    Devuelve una imagen PNG (heatmap) de Meteomatics para el parámetro y región dada.
    """
    # Construir URL para Meteomatics (ancho x alto fijos 600x400)
    url = (
        f"https://api.meteomatics.com/{time}/{param}/"
        f"{latN},{lonW}_{latS},{lonE}:600x400/png"
    )
    try:
        res = requests.get(url, auth=get_meteomatics_auth(), timeout=10)
        res.raise_for_status()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error fetching heatmap: {str(e)}")

    return StreamingResponse(io.BytesIO(res.content), media_type="image/png")
