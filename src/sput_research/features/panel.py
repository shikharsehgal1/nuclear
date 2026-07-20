"""Canonical point-in-time daily panel construction.

One row per (instrument, TSX/exchange trading day). Sprott fund data (NAV,
holdings, units, spot) joins onto SPUT rows by valuation date with explicit
`nav_published_at` and `signal_available_at` columns. All prices unadjusted
closes; `adj_close` retained for return calculation on distributing funds.
"""

from __future__ import annotations

import pandas as pd

from sput_research.paths import PROCESSED, RAW
from sput_research.validation.checks import SPUT_START

YAHOO_RAW = RAW / "yahoo"

# NAV valuation at 16:00 America/Toronto; published same evening. We stamp
# availability conservatively at 23:00 Toronto (03:00/04:00 UTC next day).
NAV_PUBLISH_HOUR_LOCAL = 23


def load_yahoo(symbol: str) -> pd.DataFrame:
    safe = symbol.replace("^", "_").replace("=", "_")
    df = pd.read_parquet(YAHOO_RAW / f"{safe}.parquet")
    df["date"] = pd.to_datetime(df["date"])
    return df.sort_values("date").reset_index(drop=True)


def fx_usdcad() -> pd.Series:
    """USD/CAD daily close (CAD per USD), indexed by date. Yahoo FX closes are
    stamped on their session date; we treat the value as available at that
    date's TSX close for same-day currency translation of closes."""
    fx = load_yahoo("CAD=X").set_index("date")["close"]
    return fx.rename("usdcad")


def build_instrument_frame(symbol: str) -> pd.DataFrame:
    df = load_yahoo(symbol).copy()
    df["dollar_volume"] = df["close"] * df["volume"]
    if symbol == "U-UN.TO":
        df = df[df["date"] >= SPUT_START].reset_index(drop=True)  # UPC regime excluded
    return df


def attach_sprott(panel: pd.DataFrame, sprott: pd.DataFrame | None) -> pd.DataFrame:
    """sprott frame schema (from ingestion.sprott):
    date, nav_usd, nav_cad, total_nav_usd, units_outstanding, u3o8_lbs,
    uranium_value_usd, cash_and_other_usd, premium_discount_published, spot_usd
    """
    if sprott is None or sprott.empty:
        return panel
    s = sprott.copy()
    s["date"] = pd.to_datetime(s["date"])
    s["nav_valuation_at"] = s["date"] + pd.Timedelta(hours=16)          # local wall time
    s["nav_published_at"] = s["date"] + pd.Timedelta(hours=NAV_PUBLISH_HOUR_LOCAL)
    merged = panel.merge(s, on="date", how="left")
    return merged


def build_panel(sprott: pd.DataFrame | None = None) -> pd.DataFrame:
    frames = []
    for symbol in ["U-UN.TO", "U-U.TO", "SRUUF", "YCA.L", "URNM", "URA", "CCJ",
                   "PHYS", "PSLV", "CEF", "SPPP", "COP-UN.TO", "NLR", "GLD", "SLV"]:
        try:
            frames.append(build_instrument_frame(symbol))
        except FileNotFoundError:
            continue
    panel = pd.concat(frames, ignore_index=True)

    fx = fx_usdcad()
    panel = panel.merge(fx.rename("usdcad").reset_index(), on="date", how="left")
    panel["usdcad"] = panel["usdcad"].astype(float)

    sput_mask = panel["instrument"].isin(["U-UN.TO", "U-U.TO", "SRUUF"])
    if sprott is not None:
        sput_rows = attach_sprott(panel[sput_mask].copy(), sprott)
        panel = pd.concat([sput_rows, panel[~sput_mask]], ignore_index=True)

    # premium/discount vs published NAV in matching currency
    if "nav_usd" in panel.columns:
        cad = panel["instrument"] == "U-UN.TO"
        usd = panel["instrument"].isin(["U-U.TO", "SRUUF"])
        panel.loc[cad, "premium_discount"] = panel.loc[cad, "close"] / panel.loc[cad, "nav_cad"] - 1
        panel.loc[usd, "premium_discount"] = panel.loc[usd, "close"] / panel.loc[usd, "nav_usd"] - 1
        # availability stamps for NAV-derived signals
        panel.loc[sput_mask, "signal_available_at"] = panel.loc[sput_mask, "nav_published_at"]
    # close-derived signals available at the close itself
    panel["close_available_at"] = panel["date"] + pd.Timedelta(hours=16)
    panel["next_tradable_at"] = panel["date"] + pd.tseries.offsets.BDay(1) + pd.Timedelta(hours=9, minutes=30)

    panel = panel.sort_values(["instrument", "date"]).reset_index(drop=True)
    return panel


def save_panel(panel: pd.DataFrame) -> None:
    out = PROCESSED / "panel.parquet"
    panel.to_parquet(out, index=False)
