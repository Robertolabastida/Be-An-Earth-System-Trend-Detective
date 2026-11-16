from pathlib import Path
import warnings
import numpy as np
import pandas as pd
import xarray as xr
from scipy import stats
import pymannkendall as mk
from statsmodels.tsa.stattools import adfuller, kpss, acf
from statsmodels.stats.multitest import multipletests
from statsmodels.stats.diagnostic import acorr_ljungbox
import matplotlib.pyplot as plt

warnings.filterwarnings("ignore")
plt.rcParams.update({
    "figure.dpi": 150,
    "savefig.dpi": 300,
    "font.size": 10,
    "axes.titlesize": 11,
    "axes.titleweight": "bold",
    "axes.grid": True,
    "grid.alpha": 0.25,
})


data_folder = Path("./Precipitation_data/gpm_imergm_v07")
exit_folder = Path("./Precipitation_data/gpm_ensenada_outputs")
csv_folder = exit_folder / "csv"
plots_folder = exit_folder / "plots"

csv_folder.mkdir(parents=True, exist_ok=True)
plots_folder.mkdir(parents=True, exist_ok=True)

files = sorted(data_folder.glob("*.HDF5"))
if not files:
    raise FileNotFoundError(f"No .HDF5 files found in: {data_folder}")

bbox = (-116.9, 30.8, -114.6, 32.35)  # Ensenada, Baja California, Mexico
time_range = ("2000-01-01", "2025-12-31")
clim_range = ("2001-01-01", "2020-12-31")  # Reference climatology (20 full years)

# Load and subset GPM IMERG V07
ds = xr.open_mfdataset(
    files,
    group="Grid",
    combine="by_coords",
    data_vars="minimal",
    coords="minimal",
    compat="override",
)
precip_rate = (
    ds["precipitation"]
    .sel(lon=slice(bbox[0], bbox[2]), lat=slice(bbox[1], bbox[3]))
    .compute()
)
ds.close()

# Standardize timestamps and slice to requested time range
precip_rate["time"] = pd.to_datetime([str(t) for t in precip_rate.time.values])
precip_rate = precip_rate.sel(time=slice(time_range[0], time_range[1]))
dates_dt = pd.to_datetime(precip_rate.time.values)

weights = np.cos(np.deg2rad(precip_rate.lat))

# --- VARIABLE 1: ACCUMULATED PRECIPITATION (mm/month and mm/year) ---
days_in_month = precip_rate.time.dt.days_in_month
accum_precip_3d = precip_rate * (days_in_month * 24)  # (time, lon, lat) in mm/month
accum_series = accum_precip_3d.weighted(weights).mean(dim=("lon", "lat"))

# 2001-2020 climatology and anomalies
clim_accum_2001_2020 = accum_series.sel(time=slice(*clim_range)).groupby("time.month").mean()
accum_anom = accum_series.groupby("time.month") - clim_accum_2001_2020

# Annual accumulation (only complete 12-month years: 2001–2025)
month_counts = accum_series.groupby("time.year").count()
complete_years = month_counts.year.where(month_counts == 12, drop=True)
annual_accum_series = accum_series.groupby("time.year").sum().sel(year=complete_years)
annual_clim_ref = float(annual_accum_series.sel(year=slice(2001, 2020)).mean().item())

# --- VARIABLE 2: PRECIPITATION INTENSITY (mm/h and mm/day eq.) ---
intensity_3d = precip_rate  # mm/h
mean_intensity_series = intensity_3d.weighted(weights).mean(dim=("lon", "lat"))
max_cell_intensity_series = intensity_3d.max(dim=("lon", "lat"))
p90_cell_intensity_series = intensity_3d.quantile(0.90, dim=("lon", "lat"))

clim_intensity_2001_2020 = mean_intensity_series.sel(time=slice(*clim_range)).groupby("time.month").mean()
intensity_anom = mean_intensity_series.groupby("time.month") - clim_intensity_2001_2020

# --- VARIABLE 3: SPATIAL DISTRIBUTION OF RAINFALL (per lon, lat grid cell) ---
spatial_monthly_mean = accum_precip_3d.mean(dim="time")
spatial_monthly_std = accum_precip_3d.std(dim="time")
spatial_cv = spatial_monthly_std / (spatial_monthly_mean + 1e-8)
spatial_p95 = accum_precip_3d.quantile(0.95, dim="time")
spatial_mean_intensity = intensity_3d.mean(dim="time")

spatial_annual_mean = (
    accum_precip_3d.groupby("time.year")
    .sum()
    .sel(year=complete_years)
    .mean(dim="year")
)

# Spatial trend per grid cell (Seasonal Mann-Kendall)
lons = accum_precip_3d.lon.values
lats = accum_precip_3d.lat.values
spatial_sen_decade = np.full((len(lons), len(lats)), np.nan)
spatial_smk_p = np.full((len(lons), len(lats)), np.nan)
spatial_smk_z = np.full((len(lons), len(lats)), np.nan)

for i in range(len(lons)):
    for j in range(len(lats)):
        pixel_ts = accum_precip_3d.values[:, i, j]
        if not np.isnan(pixel_ts).any() and np.std(pixel_ts) > 0:
            pixel_res = mk.seasonal_test(pixel_ts, period=12, alpha=0.05)
            spatial_sen_decade[i, j] = pixel_res.slope * 12.0 * 10.0  # mm/month per decade
            spatial_smk_p[i, j] = pixel_res.p
            spatial_smk_z[i, j] = pixel_res.z

# Benjamini-Hochberg FDR correction across spatial domain
valid_mask = ~np.isnan(spatial_smk_p)
_, p_fdr_flat, _, _ = multipletests(spatial_smk_p[valid_mask], alpha=0.05, method="fdr_bh")
spatial_smk_p_fdr = np.full_like(spatial_smk_p, np.nan)
spatial_smk_p_fdr[valid_mask] = p_fdr_flat

# --- VARIABLE 4: TEMPORAL VARIATION OF PRECIPITATION EVENTS ---
def pettitt_test(x: np.ndarray):
    """Detects a single structural change point (Pettitt 1979)."""
    n = len(x)
    sgn = np.sign(x[:, None] - x[None, :])
    u_stat = np.cumsum(np.sum(sgn, axis=1))[:-1]
    k_stat = np.max(np.abs(u_stat))
    change_idx = int(np.argmax(np.abs(u_stat)))
    p_val = float(min(1.0, 2.0 * np.exp((-6.0 * (k_stat ** 2)) / (n ** 3 + n ** 2))))
    return change_idx, float(k_stat), p_val, u_stat

accum_break_idx, accum_k, accum_pettitt_p, accum_pettitt_u = pettitt_test(accum_anom.values)
accum_break_date = dates_dt[accum_break_idx]
anom_cusum = np.cumsum(accum_anom.values - np.mean(accum_anom.values))
std_anom_z = (accum_anom.values - np.mean(accum_anom.values)) / np.std(accum_anom.values)
extreme_event_threshold = float(np.percentile(accum_series.values, 90))


def evaluate_statistics(series: np.ndarray, anomalies: np.ndarray, name: str, unit: str) -> dict:
    n = len(series)
    t_years = np.arange(n) / 12.0

    # 1. OLS Linear Regression + t-test + 95% CI
    ols = stats.linregress(t_years, series)
    t_crit = stats.t.ppf(0.975, df=n - 2)
    ols_ci_low = ols.slope - t_crit * ols.stderr
    ols_ci_high = ols.slope + t_crit * ols.stderr

    # 2. Standard Mann-Kendall + Sen's Slope + 95% CI
    mk_res = mk.original_test(series, alpha=0.05)
    sen_slope, _, sen_low, sen_high = stats.theilslopes(series, x=t_years, alpha=0.95)

    # 3. Seasonal Mann-Kendall (period = 12 months)
    smk_res = mk.seasonal_test(series, period=12, alpha=0.05)
    smk_annual_slope = smk_res.slope * 12.0

    # 4. Unit Root Tests (ADF + KPSS)
    _, adf_p, *_ = adfuller(series, autolag="AIC")
    _, kpss_p, *_ = kpss(series, regression="ct", nlags="auto")

    # 5. Structural Shift (Pettitt test on anomalies)
    break_idx, _, pettitt_p, _ = pettitt_test(anomalies)

    # 6. Temporal Memory / Autocorrelation on anomalies (Lag-1 & Ljung-Box lag 12)
    r1 = float(pd.Series(anomalies).autocorr(lag=1))
    lb = acorr_ljungbox(anomalies, lags=[1, 12], return_df=True)
    lb_p_lag1 = float(lb.loc[1, "lb_pvalue"])
    lb_p_lag12 = float(lb.loc[12, "lb_pvalue"])

    return {
        "Variable": name,
        "Unit": unit,
        "OLS_Slope_Decade": ols.slope * 10,
        "OLS_CI95_Low_Decade": ols_ci_low * 10,
        "OLS_CI95_High_Decade": ols_ci_high * 10,
        "OLS_p_value": ols.pvalue,
        "Sen_Slope_Decade": sen_slope * 10,
        "Sen_CI95_Low_Decade": sen_low * 10,
        "Sen_CI95_High_Decade": sen_high * 10,
        "MK_Z": mk_res.z,
        "MK_p_value": mk_res.p,
        "MK_Trend": mk_res.trend,
        "Seasonal_MK_Slope_Decade": smk_annual_slope * 10,
        "Seasonal_MK_Z": smk_res.z,
        "Seasonal_MK_p_value": smk_res.p,
        "Seasonal_MK_Trend": smk_res.trend,
        "ADF_p_value": adf_p,
        "KPSS_p_value": kpss_p,
        "Pettitt_Change_Date": str(dates_dt[break_idx])[:10],
        "Pettitt_p_value": pettitt_p,
        "Anom_Autocorr_Lag1": r1,
        "LjungBox_p_Lag1": lb_p_lag1,
        "LjungBox_p_Lag12": lb_p_lag12,
    }

stats_rows = [
    evaluate_statistics(accum_series.values, accum_anom.values, "Monthly Accumulated Precipitation", "mm/month"),
    evaluate_statistics(mean_intensity_series.values, intensity_anom.values, "Mean Precipitation Intensity", "mm/h"),
    evaluate_statistics(accum_anom.values, accum_anom.values, "Precipitation Anomalies (2001-2020)", "mm/month"),
]
df_stats = pd.DataFrame(stats_rows)

# Multiple-comparison corrections (Benjamini-Hochberg FDR and Bonferroni)
for p_col in ["OLS_p_value", "MK_p_value", "Seasonal_MK_p_value"]:
    _, p_fdr, _, _ = multipletests(df_stats[p_col], alpha=0.05, method="fdr_bh")
    _, p_bonf, _, _ = multipletests(df_stats[p_col], alpha=0.05, method="bonferroni")
    df_stats[f"{p_col}_FDR"] = p_fdr
    df_stats[f"{p_col}_Bonferroni"] = p_bonf


t_years_vec = np.arange(len(dates_dt)) / 12.0

# CSV 1A: Monthly accumulated precipitation
ols_accum = stats.linregress(t_years_vec, accum_series.values)
sen_accum_slope, sen_accum_intercept, _, _ = stats.theilslopes(accum_series.values, x=t_years_vec)

df_csv1 = pd.DataFrame({
    "date": dates_dt.strftime("%Y-%m-%d"),
    "year": dates_dt.year,
    "month": dates_dt.month,
    "days_in_month": days_in_month.values,
    "monthly_accum_precip_mm": accum_series.values,
    "spatial_min_accum_precip_mm": accum_precip_3d.min(dim=("lon", "lat")).values,
    "spatial_max_accum_precip_mm": accum_precip_3d.max(dim=("lon", "lat")).values,
    "spatial_std_accum_precip_mm": accum_precip_3d.std(dim=("lon", "lat")).values,
    "anomaly_clim_2001_2020_mm": accum_anom.values,
    "ols_linear_fit_mm": ols_accum.intercept + ols_accum.slope * t_years_vec,
    "sen_slope_fit_mm": sen_accum_intercept + sen_accum_slope * t_years_vec,
})
df_csv1.to_csv(csv_folder / "01_monthly_accumulated_precipitation.csv", index=False)

# CSV 1B: Annual accumulated precipitation (complete years 2001-2025)
df_csv1_annual = pd.DataFrame({
    "year": annual_accum_series.year.values.astype(int),
    "annual_accum_precip_mm": annual_accum_series.values,
    "climatology_annual_2001_2020_mm": annual_clim_ref,
    "annual_anomaly_mm": annual_accum_series.values - annual_clim_ref,
})
df_csv1_annual.to_csv(csv_folder / "01b_annual_accumulated_precipitation.csv", index=False)

# CSV 2: Precipitation intensity
df_csv2 = pd.DataFrame({
    "date": dates_dt.strftime("%Y-%m-%d"),
    "year": dates_dt.year,
    "month": dates_dt.month,
    "regional_mean_intensity_mm_h": mean_intensity_series.values,
    "daily_equiv_intensity_mm_day": mean_intensity_series.values * 24.0,
    "max_grid_cell_intensity_mm_h": max_cell_intensity_series.values,
    "spatial_p90_intensity_mm_h": p90_cell_intensity_series.values,
    "intensity_anomaly_2001_2020_mm_h": intensity_anom.values,
})
df_csv2.to_csv(csv_folder / "02_precipitation_intensity.csv", index=False)

# CSV 3: Spatial distribution of rainfall (lon x lat grid)
lon_grid, lat_grid = np.meshgrid(lons, lats, indexing="ij")
df_csv3 = pd.DataFrame({
    "lon": lon_grid.ravel(),
    "lat": lat_grid.ravel(),
    "mean_monthly_precip_mm": spatial_monthly_mean.values.ravel(),
    "mean_annual_precip_2001_2025_mm": spatial_annual_mean.values.ravel(),
    "std_monthly_precip_mm": spatial_monthly_std.values.ravel(),
    "coefficient_of_variation_cv": spatial_cv.values.ravel(),
    "p95_precip_mm": spatial_p95.values.ravel(),
    "mean_intensity_mm_h": spatial_mean_intensity.values.ravel(),
    "sen_slope_decade_mm_month": spatial_sen_decade.ravel(),
    "seasonal_mk_z": spatial_smk_z.ravel(),
    "seasonal_mk_p_value": spatial_smk_p.ravel(),
    "seasonal_mk_p_fdr": spatial_smk_p_fdr.ravel(),
    "sig_trend_95_uncorrected": (spatial_smk_p.ravel() < 0.05),
    "sig_trend_95_fdr": (spatial_smk_p_fdr.ravel() < 0.05),
})
df_csv3.to_csv(csv_folder / "03_spatial_rainfall_distribution.csv", index=False)

# CSV 4: Temporal variation of precipitation events
def classify_season(month: int) -> str:
    if month in (12, 1, 2):
        return "Winter (DJF)"
    elif month in (3, 4, 5):
        return "Spring (MAM)"
    elif month in (6, 7, 8):
        return "Summer (JJA)"
    return "Autumn (SON)"

monthly_clim_dict = dict(zip(clim_accum_2001_2020.month.values, clim_accum_2001_2020.values))
df_csv4 = pd.DataFrame({
    "date": dates_dt.strftime("%Y-%m-%d"),
    "year": dates_dt.year,
    "month": dates_dt.month,
    "season": [classify_season(m) for m in dates_dt.month],
    "monthly_accum_precip_mm": accum_series.values,
    "climatology_2001_2020_mm": [monthly_clim_dict[m] for m in dates_dt.month],
    "anomaly_mm": accum_anom.values,
    "standardized_anomaly_z": std_anom_z,
    "rolling_mean_12m_mm": pd.Series(accum_series.values).rolling(12, min_periods=1).mean().values,
    "cusum_anomalies_mm": anom_cusum,
    "extreme_event_p90": accum_series.values >= extreme_event_threshold,
    "pettitt_structural_regime": np.where(
        dates_dt <= accum_break_date,
        f"Pre-shift (<= {str(accum_break_date)[:7]})",
        f"Post-shift (> {str(accum_break_date)[:7]})",
    ),
})
df_csv4.to_csv(csv_folder / "04_temporal_event_variation.csv", index=False)

# CSV 5: Statistical tests summary
df_stats.to_csv(csv_folder / "05_statistical_tests_summary.csv", index=False)


# --- PLOT 1: Accumulated Precipitation (Monthly Series + Trend + Annual Bar) ---
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7.5))

ax1.plot(dates_dt, accum_series.values, color="#4a90d9", alpha=0.45, lw=1.0, label="Monthly (mm/month)")
ax1.plot(dates_dt, df_csv4["rolling_mean_12m_mm"], color="#1b4f72", lw=1.8, label="12-month moving average")
ax1.plot(dates_dt, df_csv1["ols_linear_fit_mm"], "--", color="#c0392b", lw=1.6,
         label=f"OLS ({df_stats.loc[0, 'OLS_Slope_Decade']:+.2f} mm/decade, p={df_stats.loc[0, 'OLS_p_value']:.3f})")
ax1.plot(dates_dt, df_csv1["sen_slope_fit_mm"], "-.", color="#117a65", lw=1.6,
         label=f"Sen ({df_stats.loc[0, 'Sen_Slope_Decade']:+.2f} mm/decade, MK p={df_stats.loc[0, 'MK_p_value']:.3f})")
ax1.set_title("1A. Monthly Accumulated Precipitation and Trends (Ensenada, B.C., 2000–2025)")
ax1.set_ylabel("Precipitation (mm/month)")
ax1.legend(loc="upper right", ncol=2, frameon=True)

annual_colors = ["#2e86c1" if v >= annual_clim_ref else "#d98880" for v in df_csv1_annual["annual_accum_precip_mm"]]
ax2.bar(df_csv1_annual["year"], df_csv1_annual["annual_accum_precip_mm"], color=annual_colors, edgecolor="#2c3e50", alpha=0.85)
ax2.axhline(annual_clim_ref, color="#117864", linestyle="--", lw=1.5,
            label=f"2001–2020 Climatology ({annual_clim_ref:.1f} mm/year)")
ax2.set_title("1B. Annual Accumulated Precipitation (Complete Years 2001–2025)")
ax2.set_xlabel("Year")
ax2.set_ylabel("Annual accumulation (mm/year)")
ax2.legend(loc="upper right")

plt.tight_layout()
plt.savefig(plots_folder / "01_plot_accumulated_precipitation.png")
plt.close()

# --- PLOT 2: Precipitation Intensity (Time Series + Monthly Boxplot) ---
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(13, 5.2), gridspec_kw={"width_ratios": [1.4, 1]})

ax1.plot(dates_dt, mean_intensity_series.values, color="#2874a6", lw=1.2, label="Regional mean intensity")
ax1.fill_between(dates_dt, 0, max_cell_intensity_series.values, color="#85c1e9", alpha=0.35, label="Regional grid-cell maximum")
ols_intensity = stats.linregress(t_years_vec, mean_intensity_series.values)
ax1.plot(dates_dt, ols_intensity.intercept + ols_intensity.slope * t_years_vec, "--", color="#c0392b", lw=1.5,
         label=f"OLS trend (p={df_stats.loc[1, 'OLS_p_value']:.3f})")
ax1.set_title("2A. Temporal Evolution of Precipitation Intensity (mm/h)")
ax1.set_ylabel("Intensity (mm/h)")
ax1.legend(loc="upper right")

monthly_data = [mean_intensity_series.values[dates_dt.month == m] for m in range(1, 13)]
bp = ax2.boxplot(monthly_data, patch_artist=True, tick_labels=["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"])
for patch in bp["boxes"]:
    patch.set_facecolor("#5dade2")
    patch.set_alpha(0.75)
ax2.set_title("2B. Intra-Annual Intensity Regime by Month")
ax2.set_xlabel("Month of year")
ax2.set_ylabel("Mean monthly intensity (mm/h)")

plt.tight_layout()
plt.savefig(plots_folder / "02_plot_precipitation_intensity.png")
plt.close()

# --- PLOT 3: Spatial Distribution (Annual Mean, CV, and Sen's Slope + Significance) ---
fig, axes = plt.subplots(1, 3, figsize=(15, 4.8))

im0 = axes[0].pcolormesh(lons, lats, spatial_annual_mean.values.T, shading="auto", cmap="YlGnBu")
plt.colorbar(im0, ax=axes[0], label="mm/year")
axes[0].set_title("3A. Mean Annual Precipitation")
axes[0].set_xlabel("Longitude (°)")
axes[0].set_ylabel("Latitude (°)")

im1 = axes[1].pcolormesh(lons, lats, spatial_cv.values.T, shading="auto", cmap="OrRd")
plt.colorbar(im1, ax=axes[1], label="CV (σ/μ)")
axes[1].set_title("3B. Spatial Coefficient of Variation")
axes[1].set_xlabel("Longitude (°)")

vmax_sen = np.nanmax(np.abs(spatial_sen_decade)) or 1.0
im2 = axes[2].pcolormesh(lons, lats, spatial_sen_decade.T, shading="auto", cmap="BrBG", vmin=-vmax_sen, vmax=vmax_sen)
plt.colorbar(im2, ax=axes[2], label="mm/month per decade")
sig_lon, sig_lat = np.where(spatial_smk_p < 0.05)
if len(sig_lon) > 0:
    axes[2].scatter(lons[sig_lon], lats[sig_lat], color="black", s=6, alpha=0.6, label="p < 0.05 (uncorrected)")
    axes[2].legend(loc="lower left", fontsize=8)
axes[2].set_title("3C. Sen's Slope (Seasonal MK)")
axes[2].set_xlabel("Longitude (°)")

plt.tight_layout()
plt.savefig(plots_folder / "03_plot_spatial_distribution.png")
plt.close()

# --- PLOT 4: Temporal Variation, Structural Shift (Pettitt/CUSUM), and Autocorrelation ---
fig, axes = plt.subplots(3, 1, figsize=(12, 9.5))

# Panel A: Anomalies + Pettitt change point
anom_colors = ["#2471a3" if a >= 0 else "#cb4335" for a in accum_anom.values]
axes[0].bar(dates_dt, accum_anom.values, width=25, color=anom_colors, alpha=0.8)
axes[0].axvline(accum_break_date, color="black", linestyle="--", lw=1.6,
                label=f"Potential Pettitt structural shift: {str(accum_break_date)[:7]} (p={accum_pettitt_p:.3f})")
axes[0].set_title("4A. Monthly Anomalies (relative to 2001–2020 Climatology)")
axes[0].set_ylabel("Anomaly (mm/month)")
axes[0].legend(loc="upper right")

# Panel B: CUSUM to visualize regime shifts
axes[1].plot(dates_dt, anom_cusum, color="#6c3483", lw=1.8)
axes[1].axvline(accum_break_date, color="black", linestyle="--", lw=1.5)
axes[1].axhline(0, color="gray", lw=0.8)
axes[1].set_title("4B. Cumulative Sum of Anomalies (CUSUM) - Regime Shift Detection")
axes[1].set_ylabel("CUSUM (mm)")

# Panel C: Autocorrelation Function (ACF) of anomalies
max_lags = 24
acf_vals, confint = acf(accum_anom.values, nlags=max_lags, alpha=0.05)
lags = np.arange(max_lags + 1)
axes[2].bar(lags, acf_vals, width=0.4, color="#1f618d", alpha=0.85)
axes[2].fill_between(lags, confint[:, 0] - acf_vals, confint[:, 1] - acf_vals, color="#aed6f1", alpha=0.45, label="95% white noise CI")
axes[2].axhline(0, color="black", lw=0.8)
axes[2].set_title(f"4C. Anomaly Autocorrelation (Temporal Memory: r1={df_stats.loc[2, 'Anom_Autocorr_Lag1']:.2f}, Ljung-Box p={df_stats.loc[2, 'LjungBox_p_Lag1']:.3f})")
axes[2].set_xlabel("Lag (months)")
axes[2].set_ylabel("Autocorrelation (ACF)")
axes[2].legend(loc="upper right")

plt.tight_layout()
plt.savefig(plots_folder / "04_plot_temporal_variation_memory.png")
plt.close()


print("=========================================================================")
print("CSV FILES AND PLOTS SUCCESSFULLY GENERATED AT:")
print(f"  -> CSVs:  {csv_folder}")
print(f"  -> Plots: {plots_folder}")
print("=========================================================================\n")

print(df_stats[[
    "Variable", "Sen_Slope_Decade", "MK_p_value", "MK_p_value_FDR",
    "Seasonal_MK_p_value", "Seasonal_MK_p_value_FDR", "Pettitt_Change_Date",
    "Pettitt_p_value", "Anom_Autocorr_Lag1", "LjungBox_p_Lag1"
]].to_string(index=False))

min_fdr_p = df_stats[["OLS_p_value_FDR", "MK_p_value_FDR", "Seasonal_MK_p_value_FDR"]].min().min()
sig_fdr_txt = (
    "survived multiple-comparison correction (FDR)"
    if min_fdr_p < 0.05
    else "none of the trends survived multiple-comparison correction (FDR)"
)
memory_txt = (
    f"retained significant autocorrelation (r1 = {df_stats.loc[2, 'Anom_Autocorr_Lag1']:.2f}, Ljung-Box p = {df_stats.loc[2, 'LjungBox_p_Lag1']:.3f})"
    if df_stats.loc[2, "LjungBox_p_Lag1"] < 0.05
    else f"exhibited low month-to-month persistence (r1 = {df_stats.loc[2, 'Anom_Autocorr_Lag1']:.2f}, Ljung-Box p = {df_stats.loc[2, 'LjungBox_p_Lag1']:.3f})"
)

print("\n--- SCIENTIFIC CONCLUSION DRAFT ---")
print(
    f"The analysis of GPM IMERG V07 precipitation for the Ensenada region during 2000–2025 "
    f"showed marked interannual variability and a pronounced spatial gradient between the Pacific coast and the eastern desert. "
    f"Both monthly accumulated precipitation (Sen = {df_stats.loc[0, 'Sen_Slope_Decade']:+.2f} mm/decade, p = {df_stats.loc[0, 'MK_p_value']:.3f}) "
    f"and mean intensity (Sen = {df_stats.loc[1, 'Sen_Slope_Decade']:+.4f} mm/h/decade, p = {df_stats.loc[1, 'MK_p_value']:.3f}) "
    f"were evaluated using parametric and non-parametric tests; however, {sig_fdr_txt}. "
    f"Furthermore, the Pettitt test identified a potential structural shift around {str(accum_break_date)[:7]} (p = {accum_pettitt_p:.3f}). "
    f"Finally, anomalies relative to the 2001–2020 climatology {memory_txt}, guiding the design of temporal windows for subsequent neural network modeling."
)
