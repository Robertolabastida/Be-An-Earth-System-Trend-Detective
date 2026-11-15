import os
import time
import json
import requests
import pandas as pd
import numpy as np
import scipy.stats as stats
import pymannkendall as mk
from statsmodels.tsa.stattools import adfuller
import matplotlib.pyplot as plt

API = "https://appeears.earthdatacloud.nasa.gov/api"
TOKEN = "lOJuatMu6KXuUiPCWpawihx_ygGgCYKCafksZUbqZFO2XMRTt16mspYsa-ocXapmDyoNpjVy7IWiPgPYQqCVPw"
HEADERS = {"Authorization": f"Bearer {TOKEN}"}

variables = {
    "NDVI": ("MYD13A2.061", "NDVI"),
    "EVI": ("MYD13A2.061", "EVI"),
    "LST": ("MYD11A2.061", "LST_Day_1km"),
    "Evapotranspiracion": ("MYD16A2GF.061", "ET_500m"),
    "Productividad_GPP": ("MYD17A2HGF.061", "Gpp_500m"),
}

# --- PHASE 1: DATA EXTRACTION ---
def fetch_modis_api_data(lat, lon, inicio, fin, directory=".", on_status=None):
    layers = []
    for nombre, (producto, variable) in variables.items():
        r = requests.get(f"{API}/product/{producto}", timeout=60)
        r.raise_for_status()
        disponibles = r.json()
        capa = next(k for k in disponibles if k.lower().endswith(variable.lower()))
        layers.append({"product": producto, "layer": capa})

    task = {
        "task_type": "point",
        "task_name": "Aqua_MODIS_Analysis",
        "params": {
            "dates": [{"startDate": inicio, "endDate": fin}],
            "layers": layers,
            "coordinates": [{"latitude": lat, "longitude": lon, "id": "Test"}],
        },
    }
    r = requests.post(f"{API}/task", headers=HEADERS, json=task, timeout=60)
    r.raise_for_status()
    task_id = r.json()["task_id"]

    print("Cargando datos MODIS... La consulta puede tardar varios minutos.", flush=True)
    while True:
        r = requests.get(f"{API}/task/{task_id}", headers=HEADERS, timeout=60)
        r.raise_for_status()
        estado = r.json()["status"].lower()
        print(f"Estado: {estado}", flush=True)
        if on_status:
            on_status({"status": estado, "task_id": task_id, "message":
                       "Datos disponibles" if estado == "done" else
                       "Cargando datos... Esto puede tardar varios minutos."})
        if estado == "done":
            break
        if estado in ("error", "cancelled", "expired"):
            raise RuntimeError(f"Error al procesar datos MODIS: {estado}")
        print("Cargando datos... NASA sigue procesando. Puede tardar varios minutos.", flush=True)
        time.sleep(15)

    r = requests.get(f"{API}/bundle/{task_id}", headers=HEADERS, timeout=60)
    r.raise_for_status()
    os.makedirs(os.path.join(directory, "datos_modis"), exist_ok=True)
    loaded_data = {}

    for archivo in r.json()["files"]:
        if not archivo["file_name"].lower().endswith(".csv"):
            continue
        r_csv = requests.get(
            f"{API}/bundle/{task_id}/{archivo['file_id']}", headers=HEADERS, timeout=180
        )
        r_csv.raise_for_status()
        ruta = os.path.join(directory, "datos_modis", os.path.basename(archivo["file_name"]))
        with open(ruta, "wb") as f:
            f.write(r_csv.content)
        tabla = pd.read_csv(ruta)
        if "Date" not in tabla.columns:
            continue

        for nombre, (producto, variable) in variables.items():
            columna = f"{producto.replace('.', '_')}_{variable}"
            if columna not in tabla.columns:
                continue
            df = tabla[["Date", columna]].rename(
                columns={"Date": "time", columna: "Raw_Value"}
            )
            df["time"] = pd.to_datetime(df["time"], errors="coerce")
            df["Raw_Value"] = pd.to_numeric(df["Raw_Value"], errors="coerce")
            df = df.dropna(subset=["time"]).sort_values("time")

            # AppEEARS already applies the MODIS scale factors in CSV files.
            limites = ((-0.2, 1.0) if nombre in ("NDVI", "EVI") else
                       (150, 400) if nombre == "LST" else
                       (0, 3270) if nombre == "Evapotranspiracion" else (0, 3.0))
            df.loc[~df["Raw_Value"].between(*limites), "Raw_Value"] = np.nan
            if nombre == "LST":
                df["Raw_Value"] -= 273.15  # Kelvin -> Celsius

            # 8-day ET/GPP totals are assigned to the month of their start date.
            datos = df.set_index("time")["Raw_Value"].resample("MS")
            mensual = (datos.sum(min_count=1) if nombre in
                       ("Evapotranspiracion", "Productividad_GPP") else datos.mean())
            loaded_data[nombre] = mensual.rename("Raw_Value").reset_index()

    if not loaded_data:
        raise RuntimeError("NASA no devolvió columnas MODIS reconocibles en los CSV.")
    print("Datos descargados y procesados.", flush=True)
    return loaded_data


# --- PHASE 2: SCREENING AND STATISTICAL ANALYSIS ---
def analyze_modis_trends(lat, lon, inicio, fin, directory=".", top_n=5, on_status=None):
    figures_dir = os.path.join(directory, "Figures_MODIS")
    os.makedirs(figures_dir, exist_ok=True)
    loaded_data = fetch_modis_api_data(lat, lon, inicio, fin, directory, on_status)
    screening_results = []

    for var_name, df in loaded_data.items():
        series = df["Raw_Value"].dropna().values
        if len(series) < 24:
            print(f"{var_name}: datos insuficientes para analizar tendencias (mínimo 24 meses).")
            continue
        chunk_size = max(1, int(len(series) * 0.15))
        initial_avg = np.mean(series[:chunk_size])
        final_avg = np.mean(series[-chunk_size:])
        abs_change = abs(final_avg - initial_avg)
        pct_change = (abs_change / abs(initial_avg)) * 100 if initial_avg != 0 else 0
        screening_results.append({"variable": var_name, "change_pct": pct_change})

    top_vars = sorted(screening_results, key=lambda x: x["change_pct"], reverse=True)[:top_n]
    final_report = []

    for item in top_vars:
        var = item["variable"]
        df = loaded_data[var].copy()
        df["Year"] = df["time"].dt.year
        df["Smoothed_Value"] = df["Raw_Value"].rolling(window=12, center=True).mean()
        grupo = df.groupby("Year")["Raw_Value"]
        df_annual = (grupo.sum(min_count=1) if var in
                     ("Evapotranspiracion", "Productividad_GPP") else grupo.mean()).dropna().reset_index()
        if len(df_annual) < 5:
            print(f"{var}: se necesitan al menos 5 años para las pruebas anuales.")
            continue

        y_annual = df_annual["Raw_Value"].values
        x_annual = df_annual["Year"].values
        slope, intercept, _, p_value_ols, _ = stats.linregress(x_annual, y_annual)
        ols_sig = p_value_ols < 0.05
        ols_trend = "Increasing" if ols_sig and slope > 0 else "Decreasing" if ols_sig and slope < 0 else "No Trend"

        mk_res = mk.original_test(y_annual)
        mk_sig = mk_res.p < 0.05
        mk_trend = mk_res.trend if mk_sig else "No Trend"

        # Seasonal tests require a continuous monthly sequence.
        y_raw = df["Raw_Value"].values
        if np.isfinite(y_raw).all():
            smk_res = mk.seasonal_test(y_raw, period=12)
            smk_sig = smk_res.p < 0.05
            smk_trend = smk_res.trend if smk_sig else "No Trend"
            adf_res = adfuller(y_raw) if np.std(y_raw) > 0 else None
        else:
            smk_res, adf_res, smk_sig, smk_trend = None, None, False, "Not evaluated"

        if mk_sig and ols_sig:
            conclusion = f"A statistically significant long-term trend was detected in {var}."
        elif mk_sig or ols_sig:
            conclusion = f"Moderate evidence suggests a trend in {var} based on annual averages."
        elif smk_sig:
            conclusion = f"A significant seasonal trend was detected in {var}."
        else:
            conclusion = f"No statistically significant trend was detected in {var}."

        # --- PHASE 3: VISUALIZATION AND REPORTING ---
        plt.figure(figsize=(10, 5))
        plt.plot(df["time"], df["Raw_Value"], label="Monthly Data", color="lightgray")
        plt.plot(df["time"], df["Smoothed_Value"], label="12-Month Rolling Mean", color="blue")
        if ols_sig or mk_sig or smk_sig:
            fechas = pd.to_datetime(df_annual["Year"].astype(str) + "-07-01")
            plt.plot(fechas, intercept + slope * x_annual, "r--", label="General Trend")
        plt.title(f"Time Series Analysis: {var}")
        plt.xlabel("Year")
        unidad = {"LST": "°C", "NDVI": "Index", "EVI": "Index",
                  "Evapotranspiracion": "mm (approx.)",
                  "Productividad_GPP": "kg C/m² (approx.)"}[var]
        plt.ylabel(unidad)
        plt.legend()
        plt.grid(alpha=0.5)
        plt.tight_layout()
        plot_filename = os.path.join(figures_dir, f"plot_{var}.png")
        plt.savefig(plot_filename)
        plt.close()

        final_report.append({
            "variable": var,
            "overall_change_pct": round(item["change_pct"], 2),
            "human_conclusion": conclusion,
            "plot_saved_as": plot_filename,
            "expert_statistics": {
                "annual_linear_regression": {"slope": float(slope), "p_value": float(p_value_ols), "is_significant": bool(ols_sig), "direction": ols_trend},
                "annual_mann_kendall": {"z_score": float(mk_res.z), "p_value": float(mk_res.p), "is_significant": bool(mk_sig), "direction": mk_trend},
                "monthly_seasonal_mann_kendall": {"z_score": float(smk_res.z) if smk_res else None, "p_value": float(smk_res.p) if smk_res else None, "is_significant": bool(smk_sig), "direction": smk_trend},
                "unit_root_adf": {"test_statistic": float(adf_res[0]) if adf_res else None, "p_value": float(adf_res[1]) if adf_res else None, "is_stationary": bool(adf_res[1] < 0.05) if adf_res else None}
            }
        })
    return final_report


if __name__ == "__main__":
    lat = -3.3
    lon = -60.5
    inicio = "06-01-2021"
    fin = "08-31-2021"
    results = analyze_modis_trends(lat, lon, inicio, fin)
    print(json.dumps(results, indent=2, ensure_ascii=False))