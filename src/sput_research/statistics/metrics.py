"""Performance and overfitting statistics: Sharpe machinery, probabilistic and
deflated Sharpe ratios (Bailey & López de Prado), stationary block bootstrap CIs,
and drawdown analytics. All functions operate on daily return Series."""

from __future__ import annotations

import numpy as np
import pandas as pd
from scipy import stats as sps

ANN = 252.0


def sharpe(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20 or r.std(ddof=1) == 0:
        return float("nan")
    return float(r.mean() / r.std(ddof=1) * np.sqrt(ANN))


def sortino(r: pd.Series) -> float:
    r = r.dropna()
    dd = r[r < 0].std(ddof=1)
    if len(r) < 20 or not dd or np.isnan(dd) or dd == 0:
        return float("nan")
    return float(r.mean() / dd * np.sqrt(ANN))


def cagr(r: pd.Series) -> float:
    r = r.dropna()
    if not len(r):
        return float("nan")
    growth = float((1 + r).prod())
    if growth <= 0:
        return -1.0
    return growth ** (ANN / len(r)) - 1


def max_drawdown(r: pd.Series) -> tuple[float, int]:
    eq = (1 + r.fillna(0)).cumprod()
    peak = eq.cummax()
    dd = eq / peak - 1
    mdd = float(dd.min())
    underwater = dd < 0
    dur = longest = 0
    for u in underwater:
        dur = dur + 1 if u else 0
        longest = max(longest, dur)
    return mdd, longest


def probabilistic_sharpe(r: pd.Series, sr_benchmark: float = 0.0) -> float:
    """P(true SR > benchmark) accounting for skew/kurtosis (Bailey-LdP 2012)."""
    r = r.dropna()
    n = len(r)
    if n < 30:
        return float("nan")
    sr_daily = r.mean() / r.std(ddof=1)
    sk, ku = float(sps.skew(r)), float(sps.kurtosis(r, fisher=False))
    sr_b_daily = sr_benchmark / np.sqrt(ANN)
    denom = np.sqrt(max(1e-12, (1 - sk * sr_daily + (ku - 1) / 4 * sr_daily**2) / (n - 1)))
    return float(sps.norm.cdf((sr_daily - sr_b_daily) / denom))


def deflated_sharpe(r: pd.Series, n_trials: int, sr_variance_across_trials: float | None = None) -> float:
    """DSR: PSR against the expected max Sharpe from n_trials independent tries."""
    r = r.dropna()
    if len(r) < 30 or n_trials < 1:
        return float("nan")
    var_sr = sr_variance_across_trials if sr_variance_across_trials is not None else 0.5 / ANN
    emc, e1 = 0.5772156649, np.e
    max_z = ((1 - emc) * sps.norm.ppf(1 - 1.0 / n_trials)
             + emc * sps.norm.ppf(1 - 1.0 / (n_trials * e1))) if n_trials > 1 else 0.0
    sr0_daily = np.sqrt(var_sr) * max_z
    return probabilistic_sharpe(r, sr_benchmark=sr0_daily * np.sqrt(ANN))


def stationary_bootstrap_sharpe_ci(
    r: pd.Series, n_boot: int = 2000, avg_block: int = 20,
    alpha: float = 0.05, seed: int = 7,
) -> tuple[float, float]:
    """Politis-Romano stationary bootstrap CI for annualized Sharpe."""
    x = r.dropna().to_numpy()
    n = len(x)
    if n < 60:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(seed)
    p = 1.0 / avg_block
    srs = np.empty(n_boot)
    for b in range(n_boot):
        idx = np.empty(n, dtype=np.int64)
        idx[0] = rng.integers(n)
        restart = rng.random(n) < p
        for i in range(1, n):
            idx[i] = rng.integers(n) if restart[i] else (idx[i - 1] + 1) % n
        xb = x[idx]
        s = xb.std(ddof=1)
        srs[b] = xb.mean() / s * np.sqrt(ANN) if s > 0 else 0.0
    lo, hi = np.quantile(srs, [alpha / 2, 1 - alpha / 2])
    return float(lo), float(hi)


def summarize(r: pd.Series, name: str = "") -> dict:
    r = r.dropna()
    mdd, ddur = max_drawdown(r)
    hit = float((r[r != 0] > 0).mean()) if (r != 0).any() else float("nan")
    return {
        "name": name, "n_days": len(r),
        "cagr": cagr(r), "vol": float(r.std(ddof=1) * np.sqrt(ANN)) if len(r) > 2 else float("nan"),
        "sharpe": sharpe(r), "sortino": sortino(r),
        "max_dd": mdd, "dd_days": ddur,
        "calmar": cagr(r) / abs(mdd) if mdd else float("nan"),
        "skew": float(sps.skew(r)) if len(r) > 2 else float("nan"),
        "kurtosis": float(sps.kurtosis(r)) if len(r) > 2 else float("nan"),
        "hit_rate": hit,
        "psr": probabilistic_sharpe(r),
        "time_in_market": float((r != 0).mean()),
    }
