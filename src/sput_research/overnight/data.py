"""Daily/hourly ETF bars for the overnight-drift study, and the close->open /
open->close return split. Raw Yahoo bars are cached under data/raw/overnight/
(gitignored, re-pulled by `make overnight`)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import yaml

from sput_research.paths import CONFIG, RAW

CFG = yaml.safe_load((CONFIG / "overnight.yaml").read_text())
RAW_DIR = RAW / "overnight"
RAW_DIR.mkdir(parents=True, exist_ok=True)


def tradeable_universe() -> list[str]:
    u = CFG["universe"]
    return u["physical_or_futures"] + u["equities_miners_producers"]


def all_tickers() -> list[str]:
    return tradeable_universe() + CFG["controls"]


def fetch_daily(tickers: list[str] | None = None, force: bool = False) -> None:
    import yfinance as yf
    for t in tickers or all_tickers():
        f = RAW_DIR / f"{t}_1d.parquet"
        if f.exists() and not force:
            continue
        d = yf.Ticker(t).history(start=CFG["data"]["start"], end=CFG["data"]["end"],
                                 interval="1d", auto_adjust=False, actions=False)
        d.index = d.index.tz_localize(None).normalize()
        d = d.rename(columns={"Adj Close": "AdjClose"})[["Open", "High", "Low", "Close", "AdjClose", "Volume"]]
        d.to_parquet(f)
        print(f"{t}: {len(d)} days {d.index.min().date()}..{d.index.max().date()}")


def fetch_hourly(tickers: list[str], force: bool = False) -> None:
    import yfinance as yf
    for t in tickers:
        f = RAW_DIR / f"{t}_1h.parquet"
        if f.exists() and not force:
            continue
        d = yf.Ticker(t).history(period="730d", interval="1h", auto_adjust=False, actions=False)
        d.index = d.index.tz_convert("America/New_York").tz_localize(None)
        d[["Open", "High", "Low", "Close", "Volume"]].to_parquet(f)


def load_daily(t: str) -> pd.DataFrame:
    return pd.read_parquet(RAW_DIR / f"{t}_1d.parquet")


def load_hourly(t: str) -> pd.DataFrame:
    return pd.read_parquet(RAW_DIR / f"{t}_1h.parquet")


def split_returns(d: pd.DataFrame) -> pd.DataFrame:
    """Overnight (prev close -> open) and intraday (open -> close) returns.

    Dividends: the open is scaled by the same day's AdjClose/Close factor, so an
    ex-date drop lands in the overnight leg with the dividend credited (you held
    the share through the ex-date). Days with zero volume, a non-positive open,
    a flat stale bar, or |overnight| > max_abs_overnight are invalidated, and so
    is the next day's overnight leg (its reference close is unreliable)."""
    f = d["AdjClose"] / d["Close"]
    o = d["Open"] * f
    c = d["AdjClose"]
    stale = (d["Open"] == d["High"]) & (d["High"] == d["Low"]) & (d["Low"] == d["Close"])
    bad = (d["Volume"] <= 0) | (d["Open"] <= 0) | stale
    on = o / c.shift() - 1
    idr = c / o - 1
    bad_on = bad | bad.shift(fill_value=True) | (on.abs() > CFG["data"]["max_abs_overnight"])
    out = pd.DataFrame({
        "on": on.mask(bad_on),
        "id": idr.mask(bad),
        "cc": c.pct_change(fill_method=None).mask(bad | bad.shift(fill_value=True)),
        "dollar_vol": d["Close"] * d["Volume"],
        "price": d["Close"],
        "half_spread_bps": tiered_half_spread_bps(d),
    })
    return out


def tiered_half_spread_bps(d: pd.DataFrame) -> pd.Series:
    """Half-spread assumption by trailing 63d median dollar volume (config
    spread_tiers), floored at half a tick, lagged one day. A daily-bar spread
    estimator (Abdi-Ranaldo) was tried first and rejected: it put GLD at ~30bp.
    Tiers were sanity-checked against 1-minute high-low ranges (an upper bound)."""
    adv = (d["Close"] * d["Volume"]).rolling(63, min_periods=20).median()
    hs = pd.Series(np.nan, index=d.index)
    for lo, bps in sorted(CFG["costs"]["spread_tiers"].items(), key=lambda kv: -float(kv[0])):
        hs = hs.where(hs.notna() | (adv < float(lo)), bps)
    floor = CFG["costs"]["spread_floor_cents"] / 100 / d["Close"] * 1e4
    return np.maximum(hs, floor).shift(1)


def panel() -> dict[str, pd.DataFrame]:
    """Wide frames (dates x tickers) of on / id / cc / dollar_vol / price / half_spread_bps."""
    per = {t: split_returns(load_daily(t)) for t in all_tickers() if (RAW_DIR / f"{t}_1d.parquet").exists()}
    cols = next(iter(per.values())).columns
    return {k: pd.DataFrame({t: per[t][k] for t in per}).sort_index() for k in cols}
