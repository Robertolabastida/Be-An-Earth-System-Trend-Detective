import os
import glob
import pandas as pd
import numpy as np
import requests
import scipy.stats as stats
import pymannkendall as mk
from statsmodels.tsa.stattools import adfuller
import matplotlib.pyplot as plt
import json

# --- PHASE 1: DATA EXTRACTION ---
def fetch_nasa_api_data(min_lat, max_lat, min_lon, max_lon, start_year, end_year):
    center_lat = round((min_lat + max_lat) / 2.0, 4)
    center_lon = round((min_lon + max_lon) / 2.0, 4)
    
    url = "https://power.larc.nasa.gov/api/temporal/monthly/point"
    variables = "T2M,WS10M,QV2M,SLP,PRECTOTCORR,GWETTOP,EVPTRNS,TSOIL1,TS"
    
    params = {
        "parameters": variables,
        "community": "AG",
        "latitude": center_lat,
        "longitude": center_lon,
        "start": start_year,
        "end": end_year,
        "format": "JSON"
    }
    
    response = requests.get(url, params=params)
    
    if response.status_code != 200:
        return None, {"error": f"API Error {response.status_code}: {response.text}"}
        
    data = response.json()
    raw_series = {var: {} for var in variables.split(',')}
    parameters_data = data.get('properties', {}).get('parameter', {})
    
    for var_name, time_series in parameters_data.items():
        for date_key, val in time_series.items():
            if not date_key.endswith('13') and val > -900:
                raw_series[var_name][date_key] = val
                    
    loaded_data = {}
    for var_name, time_data in raw_series.items():
        if not time_data:
            continue
            
        df = pd.DataFrame(list(time_data.items()), columns=['time', 'Raw_Value'])
        df['time'] = pd.to_datetime(df['time'], format='%Y%m')
        df = df.sort_values('time').reset_index(drop=True)
        df['Year'] = df['time'].dt.year
        loaded_data[var_name] = df
        
    return loaded_data, None

# --- PHASE 2: SCREENING AND STATISTICAL ANALYSIS ---
def analyze_climate_trends(min_lat, max_lat, min_lon, max_lon, start_year, end_year, directory=".", top_n=9):
    figures_dir = os.path.join(directory, "Figures_API")
    if os.path.exists(figures_dir):
        for file in glob.glob(os.path.join(figures_dir, "*.*")):
            os.remove(file)
    else:
        os.makedirs(figures_dir)

    loaded_data, error = fetch_nasa_api_data(min_lat, max_lat, min_lon, max_lon, start_year, end_year)
    if error:
        return error
        
    screening_results = []
    
    for var_name, df in loaded_data.items():
        series = df['Raw_Value'].dropna().values
        if len(series) < 24:
            continue
            
        chunk_size = max(1, int(len(series) * 0.15))
        initial_avg = np.mean(series[:chunk_size])
        final_avg = np.mean(series[-chunk_size:])
        
        abs_change = abs(final_avg - initial_avg)
        pct_change = (abs_change / abs(initial_avg)) * 100 if initial_avg != 0 else 0
            
        screening_results.append({
            "variable": var_name,
            "change_pct": pct_change
        })
        
    top_vars = sorted(screening_results, key=lambda x: x['change_pct'], reverse=True)[:top_n]
    final_report = []
    
    for item in top_vars:
        var = item['variable']
        df = loaded_data[var]
        
        y_raw = df['Raw_Value'].dropna().values
        df['Smoothed_Value'] = df['Raw_Value'].rolling(window=12, center=True).mean()
        
        df_annual = df.groupby('Year')['Raw_Value'].mean().reset_index()
        y_annual = df_annual['Raw_Value'].values
        x_annual = np.arange(len(y_annual))
        
        slope, intercept, _, p_value_ols, _ = stats.linregress(x_annual, y_annual)
        ols_sig = p_value_ols < 0.05
        ols_trend = "Increasing" if (ols_sig and slope > 0) else "Decreasing" if ols_sig else "No Trend"
        
        mk_res = mk.original_test(y_annual)
        mk_sig = abs(mk_res.z) > 1.96 and mk_res.p < 0.05
        mk_trend = "Increasing" if (mk_sig and mk_res.trend == 'increasing') else "Decreasing" if mk_sig else "No Trend"
        
        smk_res = mk.seasonal_test(y_raw, period=12)
        smk_sig = smk_res.p < 0.05
        smk_trend = "Increasing" if (smk_sig and smk_res.trend == 'increasing') else "Decreasing" if smk_sig else "No Trend"

        adf_res = adfuller(y_raw)
        is_stationary = adf_res[1] < 0.05

        if mk_sig and ols_sig:
            if item['change_pct'] < 1.0:
                conclusion = f"A statistically significant {mk_res.trend} long-term trend was detected in {var}, but the absolute magnitude of change is minimal ({round(item['change_pct'], 2)}%)."
            else:
                conclusion = f"Strong evidence indicates a significant {mk_res.trend} long-term trend in {var} over the selected period."
        elif mk_sig or ols_sig:
            trend_dir = mk_trend if mk_sig else ols_trend
            conclusion = f"Moderate evidence suggests a {trend_dir} trend in {var} based on annual averages."
        elif smk_sig:
            conclusion = f"A {smk_trend} seasonal trend was detected in {var}, meaning specific months are changing, but the annual average remains stable."
        else:
            conclusion = f"No statistically significant long-term changes were detected for {var}. Variations appear to be natural climate noise."

# --- PHASE 3: VISUALIZATION AND REPORTING ---
        plt.figure(figsize=(10, 5))
        plt.plot(df['time'], df['Raw_Value'], label='Monthly Raw Data', color='lightgray', alpha=0.5)
        plt.plot(df['time'], df['Smoothed_Value'], label='12-Month Rolling Mean', color='blue', alpha=0.7)
        
        if ols_sig or mk_sig or smk_sig:
            trend_line_annual = intercept + slope * x_annual
            annual_dates = pd.to_datetime(df_annual['Year'].astype(str) + '-07-01')
            plt.plot(annual_dates, trend_line_annual, color='red', linewidth=2.5, linestyle='--', label='General Trend')

        plt.title(f"Time Series Analysis: {var}")
        plt.xlabel("Year")
        plt.ylabel("Value")
        plt.legend(loc='best')
        plt.grid(linestyle='--', alpha=0.5)
        plt.tight_layout()
        
        plot_filename = os.path.join(figures_dir, f"plot_{var}.png")
        plt.savefig(plot_filename)
        plt.close()

        final_report.append({
            "variable": var,
            "overall_change_pct": round(item['change_pct'], 2),
            "human_conclusion": conclusion,
            "plot_saved_as": plot_filename,
            "expert_statistics": {
                "annual_linear_regression": {
                    "slope": slope, "p_value": p_value_ols, "is_significant": bool(ols_sig), "direction": ols_trend
                },
                "annual_mann_kendall": {
                    "z_score": mk_res.z, "p_value": mk_res.p, "is_significant": bool(mk_sig), "direction": mk_trend
                },
                "monthly_seasonal_mann_kendall": {
                    "z_score": smk_res.z, "p_value": smk_res.p, "is_significant": bool(smk_sig), "direction": smk_trend
                },
                "unit_root_adf": {
                    "test_statistic": adf_res[0], "p_value": adf_res[1], "is_stationary": bool(is_stationary)
                }
            }
        })
        
 # TRIAL CODE ONLY FOR VERIFYING DATA LOCALLY ------------------------------------------------------------------       
    #output_txt_path = os.path.join(figures_dir, "resultados_analisis.txt")
    #with open(output_txt_path, 'w', encoding='utf-8') as f:
    #    json.dump(final_report, f, indent=2, ensure_ascii=False)
 # ------------------------------------------------------------------------------------------------------------------------------------------
    return final_report

if __name__ == "__main__":
    user_min_lat = 33.3
    user_max_lat = 33.6
    user_min_lon = -112.2
    user_max_lon = -111.9
    user_start_year = "2000"
    user_end_year = "2023"
    
    results = analyze_climate_trends(
        min_lat=user_min_lat,
        max_lat=user_max_lat,
        min_lon=user_min_lon,
        max_lon=user_max_lon,
        start_year=user_start_year, 
        end_year=user_end_year,
        directory="."
    )
    
