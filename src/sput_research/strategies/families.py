"""Pre-registered strategy families. Each family maps (params, data) to a list
of Legs; the runner backtests each leg with the engine's next-open timing and
sums net returns. Families here must match docs/HYPOTHESES.md; do not add
variants that were not pre-registered without a DECISION_LOG entry."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
import yaml

from sput_research.backtest.engine import CostSpec, run_backtest
from sput_research.features.panel import load_yahoo
from sput_research.paths import CONFIG, RAW
from sput_research.strategies.signals import band_positions, rolling_beta, sma_filter, zscore
from sput_research.validation.checks import SPUT_START


@dataclass
class Leg:
    instrument: str
    prices: pd.DataFrame          # open/close indexed by date
    target_pos: pd.Series         # signed weight (of strategy NAV) by signal date
    is_short_capable: bool = False


def _cost_cfg() -> dict:
    return yaml.safe_load((CONFIG / "costs.yaml").read_text())


def cost_spec_for(instrument: str, multiplier: float = 1.0, fx_leg: bool = False) -> CostSpec:
    cfg = _cost_cfg()
    hs = cfg["half_spread_bps"].get(instrument, cfg["half_spread_bps"]["default"])
    br = cfg["borrow_bps_annual"].get(instrument, cfg["borrow_bps_annual"]["default"])
    return CostSpec(
        commission_bps=cfg["defaults"]["commission_bps"],
        half_spread_bps=hs,
        fx_spread_bps=cfg["defaults"]["fx_spread_bps"] if fx_leg else 0.0,
        borrow_bps_annual=br,
        multiplier=multiplier,
    )


def run_legs(legs: list[Leg], multiplier: float = 1.0, signal_lag: int = 0) -> pd.Series:
    parts = []
    for leg in legs:
        spec = cost_spec_for(leg.instrument, multiplier, fx_leg=leg.instrument.endswith(".L"))
        res = run_backtest(leg.prices, leg.target_pos, spec, signal_lag=signal_lag)
        parts.append(res.returns)
    total = parts[0]
    for p in parts[1:]:
        total = total.add(p, fill_value=0.0)
    return total


# ---------------------------------------------------------------- data access

def price_frame(symbol: str, usd: bool = False, start: pd.Timestamp = SPUT_START) -> pd.DataFrame:
    df = load_yahoo(symbol).set_index("date")[["open", "close", "volume"]]
    df = df[df.index >= start]
    if usd:
        fx = load_yahoo("CAD=X").set_index("date")["close"]  # CAD per USD
        fx = fx.reindex(df.index).ffill()
        if symbol.endswith(".TO"):
            df = df.div(fx, axis=0).drop(columns="volume").assign(volume=df["volume"])
        elif symbol.endswith(".L"):
            gbp = load_yahoo("GBPUSD=X").set_index("date")["close"].reindex(df.index).ffill()
            df[["open", "close"]] = df[["open", "close"]].mul(gbp, axis=0) / 100.0  # GBp -> USD
    return df.dropna(subset=["close"])


def sprott_frame() -> pd.DataFrame | None:
    pq = RAW / "sprott" / "fund_data.parquet"
    if not pq.exists():
        return None
    return pd.read_parquet(pq).assign(date=lambda d: pd.to_datetime(d["date"])).set_index("date").sort_index()


# ---------------------------------------------------------------- families

def premium_series() -> pd.Series | None:
    """Sprott-published premium/discount (U.U USD price vs USD NAV, same
    16:00-Toronto valuation stamp). NAV published in the evening -> next-open
    tradability is enforced by the engine; +1 lag stress in robustness runs."""
    s = sprott_frame()
    if s is None or "premium_discount_published" not in s.columns:
        return None
    prem = s["premium_discount_published"].dropna()
    return prem[prem.index >= SPUT_START].rename("premium")


def family_A(params: dict, side: str = "long") -> list[Leg]:
    prem = premium_series()
    if prem is None:
        return []
    z = zscore(prem, params["z_window"])
    pos = band_positions(z, params["entry_z"], params["exit_z"], side=side,
                         max_holding=params.get("holding_cap_days"))
    return [Leg("U-UN.TO", price_frame("U-UN.TO"), pos, is_short_capable=(side != "long"))]


def family_B(params: dict) -> list[Leg]:
    prem = premium_series()
    s = sprott_frame()
    if prem is None or s is None:
        return []
    nav = s["nav_usd"].reindex(prem.index).ffill()
    trend_ok = sma_filter(nav, params["trend_window"])
    z = zscore(prem, params["z_window"])
    z_gated = z.where(trend_ok, other=np.nan)  # entries only in non-downtrend
    pos = band_positions(z_gated.fillna(0.0), params["entry_z"], params["exit_z"], side="long",
                         max_holding=params.get("holding_cap_days"))
    # force exit when trend breaks
    pos = pos.where(trend_ok.reindex(pos.index).fillna(False), 0.0)
    return [Leg("U-UN.TO", price_frame("U-UN.TO"), pos)]


def family_F_spread() -> pd.DataFrame:
    """U.UN vs U.U FX-adjusted log spread with both closes at the same TSX
    16:00 stamp. Returns analysis frame; tradeability assessed vs round-trip
    costs rather than backtested as 'arbitrage'."""
    cad = price_frame("U-UN.TO")["close"]
    usd_line = price_frame("U-U.TO")["close"]
    fx = load_yahoo("CAD=X").set_index("date")["close"]
    aligned = pd.DataFrame({"uun": cad, "uu_usd": usd_line, "usdcad": fx}).dropna()
    aligned["uu_cad_equiv"] = aligned["uu_usd"] * aligned["usdcad"]
    aligned["spread"] = np.log(aligned["uun"]) - np.log(aligned["uu_cad_equiv"])
    return aligned


def family_F(params: dict) -> list[Leg]:
    a = family_F_spread()
    z = zscore(a["spread"], params["z_window"])
    pos = band_positions(z, params["entry_z"], params["exit_z"], side="both",
                         max_holding=params.get("holding_cap_days"))
    half = 0.5
    return [
        Leg("U-UN.TO", price_frame("U-UN.TO"), -pos * half, is_short_capable=True),
        Leg("U-U.TO", price_frame("U-U.TO"), pos * half, is_short_capable=True),
    ]


def family_G(params: dict) -> list[Leg]:
    sput = price_frame("U-UN.TO", usd=True)
    yca = price_frame("YCA.L", usd=True, start=SPUT_START)
    ratio = np.log(sput["close"]) - np.log(yca["close"].reindex(sput.index).ffill(limit=3))
    z = zscore(ratio.dropna(), params["z_window"])
    pos = band_positions(z, params["entry_z"], params["exit_z"], side="both",
                         max_holding=params.get("holding_cap_days"))
    half = 0.5
    return [
        Leg("U-UN.TO", price_frame("U-UN.TO"), pos * half, is_short_capable=True),
        Leg("YCA.L", yca, -pos.reindex(yca.index).ffill(limit=3).fillna(0.0) * half,
            is_short_capable=True),
    ]


def family_H(params: dict, hedged: bool = True) -> list[Leg]:
    sput = price_frame("U-UN.TO", usd=True)
    urnm = price_frame("URNM", start=SPUT_START)
    r_s = sput["close"].pct_change()
    r_u = urnm["close"].reindex(sput.index).ffill(limit=2).pct_change()
    beta = rolling_beta(r_s, r_u, window=120).clip(0.0, 3.0)
    resid = (r_s - beta * r_u).fillna(0.0)
    resid_cum = resid.rolling(params["z_window"], min_periods=max(10, params["z_window"] // 2)).sum()
    z = zscore(resid_cum, params["z_window"])
    pos = band_positions(z, params["entry_z"], params["exit_z"], side="long",
                         max_holding=params.get("holding_cap_days"))
    legs = [Leg("U-UN.TO", price_frame("U-UN.TO"), pos)]
    if hedged:
        hedge_pos = (-pos * beta.reindex(pos.index)).fillna(0.0).clip(-2.0, 0.0)
        legs.append(Leg("URNM", urnm, hedge_pos.reindex(urnm.index).fillna(0.0), is_short_capable=True))
    return legs


FAMILY_BUILDERS = {
    "A_long": lambda p: family_A(p, side="long"),
    "A_longshort": lambda p: family_A(p, side="both"),
    "B_trend": family_B,
    "F_crossline": family_F,
    "G_sput_yca": family_G,
    "H_hedged_resid": lambda p: family_H(p, hedged=True),
    "H_unhedged_resid": lambda p: family_H(p, hedged=False),
}
