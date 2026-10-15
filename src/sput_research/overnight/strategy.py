"""Walk-forward overnight-drift basket.

Each month start: score every eligible ETF by the trailing-L-month Sharpe of its
(overnight - intraday) return, using only data before that month. Hold the top
K (positive scores only) every night that month, inverse-vol weighted.

  ON: buy at the close auction, sell at the next open auction.
  LS: ON plus a short from the open to the close with the same capital, so gross
      exposure is never above 1x at any moment.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from sput_research.overnight.data import CFG, tradeable_universe

ANN = 252


def month_starts(idx: pd.DatetimeIndex) -> pd.DatetimeIndex:
    s = pd.Series(idx, index=idx)
    return pd.DatetimeIndex(s.groupby([idx.year, idx.month]).first().values)


def select(P: dict, lookback_m: int, top_k: int, universe: list[str] | None = None,
           min_adv: float | None = None) -> pd.DataFrame:
    """Daily 0/1 membership frame. Row for date t depends only on data < month start of t."""
    uni = [t for t in (universe or tradeable_universe()) if t in P["on"]]
    ls = (P["on"][uni] - P["id"][uni])
    adv = P["dollar_vol"][uni].rolling(63, min_periods=40).median()
    idx = P["on"].index
    member = pd.DataFrame(0.0, index=idx, columns=uni)
    starts = month_starts(idx)
    min_obs = int(0.8 * lookback_m * 21)
    for i, m in enumerate(starts):
        hist = ls[(ls.index < m) & (ls.index >= m - pd.DateOffset(months=lookback_m))]
        n = hist.count()
        sr = hist.mean() / hist.std() * np.sqrt(ANN)
        prev = adv[adv.index < m]
        if prev.empty:
            continue
        liquid = prev.iloc[-1] >= (min_adv or CFG["data"]["min_dollar_adv"])
        ok = sr[(n >= min_obs) & liquid & (sr > 0)].sort_values(ascending=False)
        picks = ok.index[:top_k]
        end = starts[i + 1] if i + 1 < len(starts) else idx[-1] + pd.Timedelta(days=1)
        member.loc[(idx >= m) & (idx < end), picks] = 1.0
    return member


def weights(P: dict, member: pd.DataFrame) -> pd.DataFrame:
    """Inverse 63d overnight vol, lagged one day, normalised to 1 across members."""
    vol = P["on"][member.columns].rolling(63, min_periods=40).std().shift(1)
    w = member / vol
    w = w.where(np.isfinite(w), 0.0)
    return w.div(w.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def cost_bps(P: dict, cols, scenario: str) -> pd.DataFrame:
    c = CFG["costs"]
    hs = P["half_spread_bps"][cols]
    base = pd.DataFrame(c["commission_bps"], index=hs.index, columns=cols)
    if scenario == "auction":
        return base + c["auction_slippage_bps"]
    if scenario == "spread":
        return base + hs
    if scenario == "spread_2x":
        return base + c["stress_multiplier"] * hs
    if scenario == "zero":
        return base * 0
    raise ValueError(scenario)


def backtest(P: dict, w: pd.DataFrame, variant: str = "ON", scenario: str = "auction",
             tilt: pd.DataFrame | None = None) -> pd.DataFrame:
    """Daily P&L of a weight frame. A leg with a missing return is not traded that day
    (zero P&L, zero cost). `tilt` optionally rescales overnight weights (known at the close)."""
    cols = w.columns
    on, idr = P["on"][cols], P["id"][cols]
    w_on = w * (tilt[cols] if tilt is not None else 1.0)
    traded_on = w_on.where(on.notna(), 0.0)
    gross = (traded_on * on.fillna(0)).sum(axis=1)
    cb = cost_bps(P, cols, scenario) / 1e4
    cost = 2 * (traded_on.abs() * cb).sum(axis=1)
    if variant == "LS":
        traded_id = w.where(idr.notna(), 0.0)
        gross = gross - (traded_id * idr.fillna(0)).sum(axis=1)
        cost = cost + 2 * (traded_id.abs() * cb).sum(axis=1)
    return pd.DataFrame({"gross": gross, "cost": cost, "net": gross - cost,
                         "exposure": traded_on.abs().sum(axis=1)})


def period(r: pd.Series | pd.DataFrame, name: str):
    a, b = CFG["periods"][name]
    return r.loc[a:b]


def up_day_tilt(P: dict, w: pd.DataFrame) -> pd.DataFrame:
    """Overnight weights only on selected names that were up open->close on the day
    the night starts, renormalised to the original gross. Returned as a multiplier on `w`.

    Alignment: P["on"] dated t is the night ENDING at t's open, so the signal for it
    is the intraday return of t-1 (hence the shift)."""
    up = (P["id"][w.columns].shift(1) > 0).astype(float)
    wu = w * up
    wu = wu.div(wu.sum(axis=1).replace(0, np.nan), axis=0).mul(w.sum(axis=1), axis=0).fillna(0.0)
    return (wu / w).replace([np.inf, -np.inf], 0.0).fillna(0.0)


def final_strategy(P: dict, name: str, scenario: str = "auction", universe: list[str] | None = None,
                   lookback_m: int | None = None, top_k: int | None = None,
                   min_adv: float | None = None) -> pd.DataFrame:
    f = CFG["final"]
    spec = f["strategies"][name]
    w = weights(P, select(P, lookback_m or f["lookback_months"], top_k or f["top_k"], universe, min_adv))
    tilt = up_day_tilt(P, w) if spec["up_day"] else None
    return backtest(P, w, spec["variant"], scenario, tilt=tilt)
