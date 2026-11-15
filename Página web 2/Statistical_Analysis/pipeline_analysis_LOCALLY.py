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
    df['Year'] = df['time'].dt.year
    
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
    figures_dir = os.path.join(directory, "Figures_API")
    if os.path.exists(figures_dir):
        for file in glob.glob(os.path.join(figures_dir, "*.*")):
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
        df_wind['Year'] = df_wind['time'].dt.year
        
        loaded_data['Wind_Speed'] = df_wind[['time', 'Raw_Value', 'Year']]
        del loaded_data[u_key]
        del loaded_data[v_key]
        
    # ==========================================
    # PHASE 1: SCREENING
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
        y_raw = df['Raw_Value'].dropna().values

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
                    "slope": round(slope, 5), "p_value": round(p_value_ols, 5), "is_significant": bool(ols_sig), "direction": ols_trend
                },
                "annual_mann_kendall": {
                    "z_score": round(mk_res.z, 4), "p_value": round(mk_res.p, 5), "is_significant": bool(mk_sig), "direction": mk_trend
                },
                "monthly_seasonal_mann_kendall": {
                    "z_score": round(smk_res.z, 4), "p_value": round(smk_res.p, 5), "is_significant": bool(smk_sig), "direction": smk_trend
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
