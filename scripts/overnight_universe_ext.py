"""Out-of-universe test: add 25 commodity ETFs that were never in the study and rerun the
frozen rule (flat cost and post-cost). Also reports each new ETF's overnight/intraday split."""

from __future__ import annotations

import numpy as np
import pandas as pd

import overnight_postcost as pc
from overnight_research import TAB, load_panel
from sput_research.overnight.data import CFG, fetch_daily, load_daily, load_vix, split_returns, tradeable_universe
from sput_research.overnight.strategy import backtest, members_from_scores, month_scores, period, up_day_tilt, weights
from sput_research.statistics.metrics import sharpe

EXT = CFG["universe_extension"]
PERIODS = ["presample", "discovery", "oos"]


def extended_panel(P):
    fetch_daily(EXT)
    per = {t: split_returns(load_daily(t)) for t in EXT}
    return {k: P[k].join(pd.DataFrame({t: per[t][k] for t in per}), how="left") for k in P}


def main():
    P = extended_panel(load_panel())
    split = []
    for t in EXT:
        on, idr = P["on"][t].dropna(), P["id"][t].dropna()
        split.append({"ticker": t, "first": on.index.min().date(), "overnight_ann": on.mean() * 252,
                      "intraday_ann": idr.mean() * 252, "sharpe_on_minus_id": sharpe((on - idr).dropna()),
                      "adv_2026_M": P["dollar_vol"][t]["2026"].median() / 1e6})
    sp = pd.DataFrame(split).sort_values("sharpe_on_minus_id", ascending=False)
    sp.to_csv(TAB / "ext_ticker_split.csv", index=False)
    print(sp.round(2).to_string())

    vix = load_vix().reindex(P["on"].index).ffill().shift(2)
    vs = (15 / vix).clip(upper=1.0)
    rows = []
    for lab, uni in [("original 36", tradeable_universe()), ("36 + 25 new", tradeable_universe() + EXT)]:
        w = weights(P, members_from_scores(P, month_scores(P, 24, universe=uni), 5))
        r = backtest(P, w, "LS", "auction", tilt=up_day_tilt(P, w)).net
        r = r.loc[r.ne(0).idxmax():]
        rows.append({"universe": lab, "case": "up-day LS, flat 1.5bp", **{n: sharpe(period(r, n)) for n in PERIODS}})
        for cl, aum, imp, adv in [("fees only $25k", 25_000, False, None), ("+impact $100k", 100_000, True, None),
                                  ("+impact $100k, ADV>=$20M", 100_000, True, 2e7),
                                  ("+impact $300k, ADV>=$20M", 300_000, True, 2e7)]:
            for slab, kind, sc, hedge in [("#1 LS+VIX+SPY", "upday_LS", vs, True), ("#2 ON+VIX", "upday_ON", vs, False)]:
                r = pc.run(P, aum, kind, sc, hedge, impact_on=imp, universe=uni, min_adv=adv)
                rows.append({"universe": lab, "case": f"{slab}, {cl}", **{n: sharpe(period(r, n)) for n in PERIODS}})
        share = (w > 0).sum() / (w > 0).sum().sum()
        rows[-1]["new_names_share_of_slots"] = float(share.reindex(EXT).fillna(0).sum()) if lab != "original 36" else 0.0
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "ext_universe.csv", index=False)
    print(df.round(2).to_string())
    _ = np


if __name__ == "__main__":
    main()
