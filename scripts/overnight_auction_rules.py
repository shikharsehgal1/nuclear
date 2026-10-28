"""Auction-theory execution rules for #1, and where the Sharpe goes between 'fees only' and 'as traded'.

Base: #1 at $50k, fees + impact, ADV >= $20M, 15:30 up-day signal (overnight_risk.r1).

0. Waterfall: 2024-26 / full Sharpe from the fees-only $25k number down to the tradeable one.
1. Participation cap (rule: size against the auction, not ADV): order <= x% of the estimated
   auction ($ ADV x 1.1%, the measured per-auction share), by account size. Full history.
2. Limit-on-close buy capped at ref * (1 + c), ref = the 15:30 price (hourly bars, 2024-26).
   A name fills only if close * (1 + own impact) <= cap; unfilled = cash that night. In auction
   terms a close below 15:30 is the footprint of a sell imbalance (rule 1: buy into it).
   Equal-weighted those nights earn more overnight; weighted as the book holds them, less.
3. Limit-on-open sell floored f below the reference. No pre-open quotes, so the proxy is the
   gap: if the open is > f below the prior close, skip the open auction and sell at 10:30
   in the continuous market (pay the tiered half spread). 2024-26.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import overnight_risk as base
from overnight_audit import vix_scale
from overnight_postcost import run
from overnight_research import TAB
from sput_research.overnight.data import CFG, load_hourly

C = CFG["costs"]
P, w_on, sig, AUM, ADV, stats = base.P, base.w_on, base.sig, base.AUM, base.ADV, base.stats
on = P["on"][w_on.columns]
OOS = slice("2024", None)


def name_costs(w: pd.DataFrame, aum: float, extra_bps: pd.DataFrame | None = None) -> pd.DataFrame:
    """leg_cost() per name (fraction of AUM), plus optional extra bps on one side."""
    cols = w.columns
    notional = w.abs() * aum
    sh = notional / P["price"][cols]
    per_order = (np.maximum(C["min_commission_usd"], C["per_share_commission"] * sh)
                 + C["per_share_fees"] * sh).where(notional > 0, 0.0)
    sgm = P["cc"][cols].rolling(63, min_periods=20).std().shift(1)
    auc = P["dollar_vol"][cols].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
    imp = (C["impact_coefficient"] * sgm * np.sqrt((notional / auc).clip(lower=0))).fillna(0)
    cost = 2 * per_order + (C["auction_slippage_bps"] / 1e4 + imp) * 2 * notional + C["sec_fee_bps_on_sells"] / 1e4 * notional
    if extra_bps is not None:
        cost = cost + extra_bps.reindex_like(w).fillna(0) / 1e4 * notional
    return cost / aum


def impact_one_side(w: pd.DataFrame, aum: float) -> pd.DataFrame:
    cols = w.columns
    sgm = P["cc"][cols].rolling(63, min_periods=20).std().shift(1)
    auc = P["dollar_vol"][cols].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
    return (C["impact_coefficient"] * sgm * np.sqrt((w * aum / auc).clip(lower=0))).fillna(0)


def pnl(w, aum=AUM, ret=None, extra_bps=None) -> pd.Series:
    ret = on if ret is None else ret
    r = (w * ret.fillna(0)).sum(axis=1) - name_costs(w, aum, extra_bps).sum(axis=1)
    return r.loc[base.r1.index]


def row(lab, r, **kw):
    s = stats(r)
    return {"variant": lab, **kw, "sharpe_oos": s.at["Sharpe", "2024-26"], "cagr_oos": s.at["CAGR", "2024-26"],
            "maxdd_oos": s.at["max DD", "2024-26"], "sharpe_full": s.at["Sharpe", "full"],
            "cagr_full": s.at["CAGR", "full"], "maxdd_full": s.at["max DD", "full"]}


def hourly(at: str) -> pd.DataFrame:
    out = {}
    for t in w_on.columns:
        try:
            h = load_hourly(t)
        except FileNotFoundError:
            continue
        h = h[h.index.strftime("%H:%M") == at]
        out[t] = pd.Series(h.Open.values, index=h.index.normalize())
    return pd.DataFrame(out).reindex(index=on.index, columns=w_on.columns)


def main():
    assert np.allclose(pnl(w_on), base.r1), "per-name cost rebuild must match run()"
    vs = vix_scale(P["on"].index)

    # 0. waterfall
    wf = [("fees only, $25k, all names, signal at close", run(P, 25_000, "upday_ON", vs, impact_on=False)),
          ("same at $50k", run(P, AUM, "upday_ON", vs, impact_on=False)),
          ("+ price impact of own orders", run(P, AUM, "upday_ON", vs, impact_on=True)),
          ("+ ADV >= $20M filter", run(P, AUM, "upday_ON", vs, impact_on=True, min_adv=ADV)),
          ("+ 15:30 signal (as traded)", base.r1)]
    wf = pd.DataFrame([row(lab, r) for lab, r in wf])
    wf.to_csv(TAB / "sharpe_waterfall.csv", index=False)
    print(wf.round(3).to_string(), "\n")

    rows = []
    # 1. participation cap
    auc = P["dollar_vol"][w_on.columns].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
    for aum in [50_000, 100_000, 250_000]:
        for x in [None, 0.20, 0.10, 0.05]:
            w = w_on if x is None else np.minimum(w_on, (x * auc / aum).reindex_like(w_on).fillna(0))
            rows.append(row("participation cap", pnl(w, aum), aum=aum, param="none" if x is None else f"{x:.0%}",
                            avg_gross=w.sum(axis=1)[w.sum(axis=1) > 0].mean()))

    # 2. limit-on-close buy
    p1530 = hourly("15:30")
    move = P["price"][w_on.columns] / p1530 - 1                  # close vs 15:30, on the night-start day
    imp = impact_one_side(w_on, AUM)
    held = w_on > 0
    ex = []
    for c in [None, 0.005, 0.0025, 0.001, 0.0]:
        mv = move.shift(1)
        fill = held.copy() if c is None else (((mv + imp) <= c) | mv.isna()) & held  # no hourly bars before 2024: MOC
        w = w_on.where(fill, 0.0)
        rows.append(row("limit-on-close buy", pnl(w), aum=AUM, param="MOC" if c is None else f"cap +{c * 1e4:g} bp",
                        fill_rate=fill.loc[OOS].sum().sum() / held.loc[OOS].sum().sum()))
    # auction-theory check: nights bought into weakness vs strength
    m = move.shift(1)[held].loc[OOS]
    o = on[held].loc[OOS]
    for lab, mask in [("close below 15:30 (sell-imbalance footprint)", m < 0), ("close above 15:30", m > 0)]:
        wm = w_on.loc[OOS][held.loc[OOS]][mask]
        ex.append({"nights": lab, "n": int(mask.sum().sum()), "mean_overnight_bps": o[mask].stack().mean() * 1e4,
                   "median_overnight_bps": o[mask].stack().median() * 1e4,
                   "weighted_mean_overnight_bps": (wm * o[mask]).sum().sum() / wm.sum().sum() * 1e4})

    # 3. limit-on-open sell (gap proxy)
    p1030 = hourly("10:30")
    late = p1030 / P["price"][w_on.columns].shift(1) - 1           # prior close -> 10:30
    gap = on
    hs = P["half_spread_bps"][w_on.columns]
    for f in [None, 0.01, 0.005, 0.0025]:
        skip = (gap < -f) & held & late.notna() if f is not None else held & False
        ret = on.where(~skip, late)
        rows.append(row("limit-on-open sell (gap proxy)", pnl(w_on, ret=ret, extra_bps=hs.where(skip)), aum=AUM,
                        param="MOO" if f is None else f"floor −{f * 1e4:g} bp",
                        fill_rate=1 - skip.loc[OOS].sum().sum() / held.loc[OOS].sum().sum()))
        if f is not None:
            ex.append({"nights": f"gap down > {f * 1e4:g} bp: sell at open", "n": int(skip.loc[OOS].sum().sum()),
                       "mean_overnight_bps": on[skip].loc[OOS].stack().mean() * 1e4})
            ex.append({"nights": f"gap down > {f * 1e4:g} bp: sell at 10:30", "n": int(skip.loc[OOS].sum().sum()),
                       "mean_overnight_bps": late[skip].loc[OOS].stack().mean() * 1e4})

    df = pd.DataFrame(rows)
    df.to_csv(TAB / "auction_rules.csv", index=False)
    print(df.round(3).to_string(), "\n")
    ex = pd.DataFrame(ex)
    ex.to_csv(TAB / "auction_rules_nights.csv", index=False)
    print(ex.round(1).to_string())


if __name__ == "__main__":
    main()
