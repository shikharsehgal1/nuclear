"""Shared signal utilities. All rolling stats use only past data (pandas
rolling windows end at the current observation; the engine then delays
execution to the next open, so no lookahead)."""

from __future__ import annotations

import numpy as np
import pandas as pd


def zscore(x: pd.Series, window: int, min_periods: int | None = None) -> pd.Series:
    mp = min_periods or max(10, window // 2)
    mu = x.rolling(window, min_periods=mp).mean()
    sd = x.rolling(window, min_periods=mp).std(ddof=1)
    return (x - mu) / sd.replace(0.0, np.nan)


def rolling_percentile(x: pd.Series, window: int) -> pd.Series:
    return x.rolling(window, min_periods=max(10, window // 2)).rank(pct=True)


def sma_filter(x: pd.Series, window: int) -> pd.Series:
    """True where x is at/above its SMA (uptrend-or-flat)."""
    return x >= x.rolling(window, min_periods=max(10, window // 2)).mean()


def rolling_beta(y: pd.Series, x: pd.Series, window: int = 120) -> pd.Series:
    mp = max(30, window // 2)
    cov = y.rolling(window, min_periods=mp).cov(x)
    var = x.rolling(window, min_periods=mp).var()
    return cov / var.replace(0.0, np.nan)


def band_positions(z: pd.Series, entry: float, exit_: float, side: str = "long",
                   max_holding: int | None = None) -> pd.Series:
    """Mean-reversion band logic on a z-scored series. side='long' buys z<=-entry
    and exits z>=-exit_; side='short' shorts z>=+entry, exits z<=+exit_;
    side='both' combines. Stateful, vectorized via loop (small data)."""
    zv = z.to_numpy()
    pos = np.zeros(len(zv))
    holding = 0
    for i in range(1, len(zv)):
        p = pos[i - 1]
        if np.isnan(zv[i]):
            pos[i] = p
            continue
        if p != 0:
            holding += 1
        if p > 0 and (zv[i] >= -exit_ or (max_holding and holding >= max_holding)):
            p, holding = 0.0, 0
        elif p < 0 and (zv[i] <= exit_ or (max_holding and holding >= max_holding)):
            p, holding = 0.0, 0
        if p == 0:
            if side in ("long", "both") and zv[i] <= -entry:
                p, holding = 1.0, 0
            elif side in ("short", "both") and zv[i] >= entry:
                p, holding = -1.0, 0
        pos[i] = p
    return pd.Series(pos, index=z.index)
