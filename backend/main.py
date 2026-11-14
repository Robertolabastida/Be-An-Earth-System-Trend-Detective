import os
import io
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
import requests
import numpy as np

# Cargar variables de entorno desde backend/.env
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))
METEO_USER = os.getenv("METEOMATICS_USER")
METEO_PWD = os.getenv("METEOMATICS_PASSWORD")
if not METEO_USER or not METEO_PWD:
    raise RuntimeError("Missing Meteomatics credentials in .env file")

app = FastAPI()

# Habilitar CORS (apertura básica para desarrollo)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"]
)

@app.get("/api/time-series")
async def get_time_series(param: str, lat: float, lon: float, start: str, end: str):
    """
    Recupera datos de Meteomatics en formato JSON para una serie de tiempo.
    Calcula pendiente y R^2 de una regresión lineal sobre los valores.
    """
    # Formato del rango de tiempo (por horas diarias)
    time_range = f"{start}--{end}:PT24H"
    url = f"https://api.meteomatics.com/{time_range}/{param}/{lat},{lon}/json"

    try:
        res = requests.get(url, auth=(METEO_USER, METEO_PWD), timeout=10)
        res.raise_for_status()
        json_data = res.json()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error calling Meteomatics API: {str(e)}")

    # Extraer fechas y valores
    try:
        param_key = next(iter(json_data))
        coords = json_data[param_key][0]["coordinates"]
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
async def get_heatmap(param: str, latN: float, lonW: float, latS: float, lonE: float, time: str):
    """
    Devuelve una imagen PNG (heatmap) de Meteomatics para el parámetro y región dada.
    """
    # Construir URL para Meteomatics (ancho x alto fijos 600x400)
    url = (
        f"https://api.meteomatics.com/{time}/{param}/"
        f"{latN},{lonW}_{latS},{lonE}:600x400/png"
    )
    try:
        res = requests.get(url, auth=(METEO_USER, METEO_PWD), timeout=10)
        res.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Error fetching heatmap: {str(e)}")

    return StreamingResponse(io.BytesIO(res.content), media_type="image/png")
