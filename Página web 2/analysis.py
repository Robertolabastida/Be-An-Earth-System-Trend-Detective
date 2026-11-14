"""Trend statistics: seasonal anomalies, OLS (autocorrelation-adjusted), seasonal and annual Mann-Kendall, Sen's slope."""
import numpy as np
from scipy import stats

ALPHA = 0.05


class AnalysisError(Exception):
    pass


def _mk(x):
    """Mann-Kendall S and its variance (with tie correction)."""
    x = np.asarray(x, float)
    n = len(x)
    if n < 3:
        return 0.0, 0.0
    s = sum(np.sign(x[i + 1:] - x[i]).sum() for i in range(n - 1))
    _, c = np.unique(x, return_counts=True)
    var = (n * (n - 1) * (2 * n + 5) - (c * (c - 1) * (2 * c + 5)).sum()) / 18
    return float(s), float(var)


def _p(s, var):
    if var <= 0:
        return 1.0
    z = (s - np.sign(s)) / np.sqrt(var)  # continuity correction
    return float(2 * stats.norm.sf(abs(z)))


def _sen(t, y):
    i, j = np.triu_indices(len(t), 1)
    dt = t[j] - t[i]
    ok = dt > 0
    return float(np.median((y[j] - y[i])[ok] / dt[ok]))


def _ols(t, y):
    n = len(t)
    sxx = ((t - t.mean()) ** 2).sum()
    b = ((t - t.mean()) * (y - y.mean())).sum() / sxx
    a = y.mean() - b * t.mean()
    res = y - (a + b * t)
    ss_tot = ((y - y.mean()) ** 2).sum()
    if ss_tot < 1e-20:
        return {"slope": 0.0, "intercept": float(y.mean()), "ci": [0.0, 0.0],
                "p": 1.0, "r2": 1.0, "lag1": 0.0, "n_eff": float(n)}
    if (res ** 2).sum() < 1e-20:
        return {"slope": float(b), "intercept": float(a), "ci": [float(b), float(b)],
                "p": 0.0 if b != 0 else 1.0, "r2": 1.0, "lag1": 0.0, "n_eff": float(n)}
    if np.std(res[:-1]) < 1e-12 or np.std(res[1:]) < 1e-12:
        r1 = 0.0
    else:
        r1 = float(np.clip(np.corrcoef(res[:-1], res[1:])[0, 1], 0, 0.99))
    neff = max(n * (1 - r1) / (1 + r1), 3.1)  # effective sample size for AR(1) residuals
    se = np.sqrt((res ** 2).sum() / (n - 2) / sxx) * np.sqrt(n / neff)
    df = neff - 2
    tc = stats.t.ppf(0.975, df)
    return {"slope": float(b), "intercept": float(a), "ci": [float(b - tc * se), float(b + tc * se)],
            "p": float(2 * stats.t.sf(abs(b / se), df)), "r2": float(1 - (res ** 2).sum() / ss_tot),
            "lag1": r1, "n_eff": float(neff)}


def analyze(data):
    keys = sorted(data)
    if len(keys) < 60:
        raise AnalysisError("Fewer than 60 valid monthly observations here; a trend cannot be estimated reliably.")
    yrs = np.array([k[0] for k in keys])
    mos = np.array([k[1] for k in keys])
    t = yrs + (mos - 0.5) / 12
    v = np.array([data[k] for k in keys], float)
    clim = {m: v[mos == m].mean() for m in np.unique(mos)}
    anom = v - np.array([clim[m] for m in mos])

    ols = _ols(t, anom)

    S = VAR = 0.0
    for m in clim:  # seasonal Mann-Kendall (Hirsch et al. 1982): one test per calendar month, then summed
        s, var = _mk(anom[mos == m])
        S += s
        VAR += var
    p_smk = _p(S, VAR)
    sen = _sen(t, anom) 
    sen_b = float(np.median(anom - sen * t))

    ann = [(int(y), float(anom[yrs == y].mean())) for y in np.unique(yrs) if (yrs == y).sum() >= 10]
    annual = None
    if len(ann) >= 8:
        ay, av = np.array([a[0] for a in ann], float), np.array([a[1] for a in ann])
        s, var = _mk(av)
        annual = {"p": _p(s, var), "sen": _sen(ay, av)}

    p_main = annual["p"] if annual else p_smk  # annual means reduce autocorrelation
    t0, t1 = float(t[0]), float(t[-1])
    span = t1 - t0
    return {
        "t": t.round(4).tolist(), "values": v.round(4).tolist(), "anomalies": anom.round(4).tolist(),
        "annual": [[a, round(b, 4)] for a, b in ann],
        "trend_ols": [[t0, ols["intercept"] + ols["slope"] * t0], [t1, ols["intercept"] + ols["slope"] * t1]],
        "trend_sen": [[t0, sen_b + sen * t0], [t1, sen_b + sen * t1]],
        "stats": {
            "n_months": len(keys), "first": [int(yrs[0]), int(mos[0])], "last": [int(yrs[-1]), int(mos[-1])],
            "ols_slope_per_year": ols["slope"], "ols_slope_per_decade": ols["slope"] * 10,
            "ols_total_change": ols["slope"] * span, "ols_ci_per_decade": [c * 10 for c in ols["ci"]],
            "ols_p": ols["p"], "r2": ols["r2"], "lag1_autocorr": ols["lag1"], "n_effective": ols["n_eff"],
            "sen_per_decade": sen * 10, "sen_total_change": sen * span,
            "seasonal_mk_p": p_smk, "annual_mk_p": annual["p"] if annual else None,
            "significant": bool(p_main < ALPHA), "alpha": ALPHA,
            "direction": "increasing" if sen > 0 else "decreasing" if sen < 0 else "flat",
        },
    }