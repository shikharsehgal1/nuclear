"""Synthetic NAV in RETURNS space, plus staleness/lead-lag diagnostics.

Units-outstanding history is not published (docs/DATA_ENDPOINTS.md), so
per-unit synthetic NAV cannot be built from holdings levels. It also isn't
needed: ATM issuance occurs only at >=100% of NAV (MECHANICS.md), so per-unit
NAV returns decompose as

    r_NAV(t) ~= w_U(t) * r_spot(t) + cash/fee drag + issuance accretion (small)

with w_U ~= 0.95-1.0. We therefore (a) nowcast published-NAV returns from
contemporaneous observables, (b) measure how stale the NAV's spot input is
vs Numerco, and (c) build a 'live' synthetic premium for H-D.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from sput_research.paths import RAW
from sput_research.strategies.families import price_frame, sprott_frame
from sput_research.validation.checks import SPUT_START


def numerco() -> pd.DataFrame:
    df = pd.read_parquet(RAW / "numerco" / "spot.parquet")
    return df.assign(date=pd.to_datetime(df["date"])).set_index("date").sort_index()


def build_returns_frame() -> pd.DataFrame:
    s = sprott_frame()
    nm = numerco()
    urnm = price_frame("URNM", start=SPUT_START)["close"]
    uu = price_frame("U-U.TO")["close"]

    idx = s.index[s.index >= SPUT_START]
    df = pd.DataFrame(index=idx)
    df["nav_ret"] = s["nav_usd"].pct_change().reindex(idx)
    df["numerco_ret"] = nm["spot_usd"].reindex(idx).ffill(limit=5).pct_change()
    df["urnm_ret"] = urnm.reindex(idx).ffill(limit=2).pct_change()
    df["price_ret"] = uu.reindex(idx).ffill(limit=2).pct_change()
    df["premium"] = s["premium_discount_published"].reindex(idx)
    df["nav_usd"] = s["nav_usd"].reindex(idx)
    df["spot_numerco"] = nm["spot_usd"].reindex(idx).ffill(limit=5)
    return df


def staleness_diagnostics(df: pd.DataFrame) -> dict:
    """Cross-correlations of NAV returns with leads/lags of Numerco spot and
    uranium equity returns; positive coefficients at NAV lag k>0 mean NAV
    incorporates the information k days late."""
    out = {}
    for k in range(-3, 4):
        sub = pd.DataFrame({"nav": df["nav_ret"], "x": df["numerco_ret"].shift(k)}).dropna()
        out[f"corr_nav_vs_numerco_shift{k}"] = float(sub["nav"].corr(sub["x"]))
    for k in range(0, 4):
        sub = pd.DataFrame({"nav": df["nav_ret"], "x": df["urnm_ret"].shift(k)}).dropna()
        out[f"corr_nav_vs_urnm_shift{k}"] = float(sub["nav"].corr(sub["x"]))
    return out


def nav_nowcast_models(df: pd.DataFrame, train_end: pd.Timestamp | None = None) -> dict:
    """Forecast NEXT-day published NAV return from today's observables
    (all available by the evening of day t). OLS with HAC errors."""
    d = df.copy()
    d["y"] = d["nav_ret"].shift(-1)
    feats = ["price_ret", "urnm_ret", "numerco_ret", "premium"]
    d = d.dropna(subset=["y"] + feats)
    if train_end is not None:
        d = d[d.index <= train_end]
    X = sm.add_constant(d[feats])
    model = sm.OLS(d["y"], X).fit(cov_type="HAC", cov_kwds={"maxlags": 5})
    return {
        "n": int(model.nobs), "r2": float(model.rsquared),
        "coef": model.params.to_dict(),
        "tstat": model.tvalues.to_dict(),
    }


def synthetic_premium(df: pd.DataFrame, w_uranium: float = 0.98) -> pd.Series:
    """'Live' premium vs a Numerco-marked NAV: rebase published NAV to today's
    Numerco spot instead of the (possibly staler) assessed input embedded in it.
    NAV_syn(t) = NAV_pub(t) * (1 + w * (Numerco(t)/NumercoImplied(t) - 1)) where
    NumercoImplied uses a 5d trailing regression-free proxy: the ratio of
    cumulated NAV returns to cumulated Numerco returns is near 1, so we
    approximate the embedded spot with a 3-day trailing mean of Numerco."""
    embedded_spot = df["spot_numerco"].rolling(3).mean()
    nav_syn = df["nav_usd"] * (1 + w_uranium * (df["spot_numerco"] / embedded_spot - 1))
    price = df["nav_usd"] * (1 + df["premium"])  # published price recovered exactly
    return (price / nav_syn - 1).rename("premium_synthetic")


def reconstruction_error(df: pd.DataFrame) -> dict:
    """How well does w*Numerco explain published NAV returns? Residual std by
    regime; bias; error around big spot moves."""
    sub = df.dropna(subset=["nav_ret", "numerco_ret"])
    X = sm.add_constant(sub[["numerco_ret"]])
    m = sm.OLS(sub["nav_ret"], X).fit()
    resid = m.resid
    big_spot = sub["numerco_ret"].abs() > sub["numerco_ret"].abs().quantile(0.9)
    vol = sub["numerco_ret"].rolling(20).std()
    hi_vol = vol > vol.median()
    return {
        "beta_nav_on_numerco": float(m.params.iloc[1]),
        "r2": float(m.rsquared),
        "resid_std_daily": float(resid.std()),
        "bias_daily": float(resid.mean()),
        "resid_std_big_spot_days": float(resid[big_spot].std()),
        "resid_std_hi_vol": float(resid[hi_vol.reindex(resid.index).fillna(False)].std()),
        "mean_abs_err_daily_bps": float(resid.abs().mean() * 1e4),
    }
