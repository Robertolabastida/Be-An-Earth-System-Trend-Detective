import os
import glob
import pandas as pd
import numpy as np
import scipy.stats as stats
import pymannkendall as mk
from statsmodels.tsa.stattools import adfuller
import matplotlib.pyplot as plt
import json

def load_and_clean_nasa_csv(filepath):
    with open(filepath, 'r') as f:
        lines = f.readlines()
    
    skip_idx = next(i for i, line in enumerate(lines) if line.startswith('time'))
    
    df = pd.read_csv(filepath, skiprows=skip_idx)
    df.columns = df.columns.str.strip()
    val_col = df.columns[1]
    
    df['time'] = pd.to_datetime(df['time'])
    df = df[['time', val_col]].rename(columns={val_col: 'Raw_Value'})
    
    filename = os.path.basename(filepath)
    parts = filename.split('.')
    if len(parts) >= 3:
        var_name = parts[2].split('_')[-1] 
    else:
        var_name = val_col 
        
    return df, var_name

def analyze_climate_trends(directory=".", top_n=5):
    # ==========================================
    # PREPARATION: FIGURE FOLDER MANAGEMENT
    # ==========================================
    figures_dir = os.path.join(directory, "Figures")
    if os.path.exists(figures_dir):
        for file in glob.glob(os.path.join(figures_dir, "*.png")):
            os.remove(file)
    else:
        os.makedirs(figures_dir)

    csv_files = glob.glob(os.path.join(directory, "g4.areaAvgTimeSeries*.csv"))
    if not csv_files:
        return {"error": f"No data files found in the directory: {directory}"}
    
    # ==========================================
    # PHASE 0: LOAD DATA & DERIVE VARIABLES
    # ==========================================
    loaded_data = {} 
    
    for file in csv_files:
        df, var_name = load_and_clean_nasa_csv(file)
        loaded_data[var_name] = df

    u_key = next((k for k in loaded_data.keys() if 'U10M' in k), None)
    v_key = next((k for k in loaded_data.keys() if 'V10M' in k), None)
    
    if u_key and v_key:
        df_u = loaded_data[u_key]
        df_v = loaded_data[v_key]
        
        df_wind = pd.merge(df_u, df_v, on='time', suffixes=('_u', '_v'))
        df_wind['Raw_Value'] = np.sqrt(df_wind['Raw_Value_u']**2 + df_wind['Raw_Value_v']**2)
        
        loaded_data['Wind_Speed'] = df_wind[['time', 'Raw_Value']]
        del loaded_data[u_key]
        del loaded_data[v_key]
        
    # ==========================================
    # PHASE 1: SCREENING (Extremes Delta)
    # ==========================================
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
    
    # ==========================================
    # PHASE 2: RIGOROUS STATISTICAL ANALYSIS & PLOTTING
    # ==========================================
    final_report = []
    
    for item in top_vars:
        var = item['variable']
        df = loaded_data[var]
        
        df['Smoothed_Value'] = df['Raw_Value'].rolling(window=12, center=True).mean()
        df_smoothed = df.dropna(subset=['Smoothed_Value']).copy()
        
        y_smooth = df_smoothed['Smoothed_Value'].values
        x_smooth = np.arange(len(y_smooth))
        y_raw = df['Raw_Value'].values
        
        time_raw = df['time']
        time_smooth = df_smoothed['time']
        
        # --- TESTS ---
        slope, intercept, _, p_value_ols, _ = stats.linregress(x_smooth, y_smooth)
        ols_sig = p_value_ols < 0.05
        
        if ols_sig:
            ols_trend = "Increasing" if slope > 0 else "Decreasing"
        else:
            ols_trend = "No Trend"
        
        mk_res = mk.original_test(y_smooth)
        mk_sig = abs(mk_res.z) > 1.96 and mk_res.p < 0.05
        if mk_sig:
            mk_trend = "Increasing" if mk_res.trend == 'increasing' else "Decreasing"
        else:
            mk_trend = "No Trend"
        
        smk_res = mk.seasonal_test(y_raw, period=12)
        smk_sig = smk_res.p < 0.05

        adf_res = adfuller(y_raw)
        is_stationary = adf_res[1] < 0.05

        # --- HUMAN CONCLUSION ---
        if mk_sig and ols_sig:
            conclusion = f"Strong evidence indicates a significant {mk_res.trend} trend in {var} over the selected period."
        elif mk_sig or smk_sig:
            conclusion = f"Moderate evidence suggests a {mk_res.trend} trend in {var}, mostly driven by seasonal shifts."
        else:
            conclusion = f"No statistically significant changes were detected for {var}. The variations are likely natural climate noise."

        # --- PLOTS ---
        plt.figure(figsize=(10, 5))
        plt.plot(time_raw, y_raw, label='Raw Data', color='lightgray', alpha=0.6)
        plt.plot(time_smooth, y_smooth, label='Smoothed (12-Month)', color='blue', linewidth=2)

        if ols_sig:
            trend_line = intercept + slope * x_smooth
            plt.plot(time_smooth, trend_line, color='red', linestyle='--', label='Linear Trend (OLS)')

        plt.title(f"Time Series Analysis: {var}")
        plt.xlabel("Year")
        plt.ylabel("Value")
        plt.legend()
        plt.grid(linestyle='--', alpha=0.5)
        plt.tight_layout()
        
        plot_filename = os.path.join(figures_dir, f"plot_{var}.png")
        plt.savefig(plot_filename)
        plt.close() 

        # --- PACKAGE RESULTS ---
        final_report.append({
            "variable": var,
            "overall_change_pct": round(item['change_pct'], 2),
            "human_conclusion": conclusion,
            "plot_saved_as": plot_filename,
            "expert_statistics": {
                "linear_regression": {
                    "slope": round(slope, 5), "p_value": round(p_value_ols, 5), "is_significant": bool(ols_sig), "direction": ols_trend
                },
                "mann_kendall": {
                    "z_score": round(mk_res.z, 4), "p_value": round(mk_res.p, 5), "is_significant": bool(mk_sig), "direction": mk_trend
                },
                "seasonal_mann_kendall": {
                    "z_score": round(smk_res.z, 4), "p_value": round(smk_res.p, 5), "is_significant": bool(smk_sig)
                },
                "unit_root_adf": {
                    "test_statistic": round(adf_res[0], 4), "p_value": round(adf_res[1], 5), "is_stationary": bool(is_stationary)
                }
            }
        })
        
    return final_report

if __name__ == "__main__":
    results = analyze_climate_trends(directory="./csv_data", top_n=5)
    print(json.dumps(results, indent=2, ensure_ascii=False))