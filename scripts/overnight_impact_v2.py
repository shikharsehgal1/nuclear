"""Impact model v2: real auction sizes instead of a flat share of ADV.

v1 (used so far): each auction = 1.1% of the trailing 63d median $ volume (measured on 2 days),
same size for open and close, impact = 0.1 * sigma * sqrt(order / auction).

v2: auction $ size from the NYSE Arca auction prints on the consolidated tape (Alpaca pull):
  - years pulled (2016, 2023, 2026): the actual size of the auction you trade into, open and close separately
  - other years: per-ETF median ratio (auction $ / daily $ volume) from the pulled years, x trailing ADV
  - impact coefficient: 0.1 both sides, or the imbalance-feed fit (open 0.145, close 0.055)
Then #1 (frozen ranking) and the overnight hit-rate ranking, by account size.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import overnight_ranking as rk
from overnight_audit import vix_scale
from overnight_research import TAB
from sput_research.overnight.data import CFG, RAW_DIR
from sput_research.overnight.strategy import members_from_scores, up_day_tilt, weights

P, stats, C = rk.P, rk.stats, CFG["costs"]


def auction_usd() -> tuple[pd.DataFrame, pd.DataFrame, list[int]]:
    a = pd.concat([pd.read_parquet(f) for f in sorted((RAW_DIR / "alpaca").glob("auctions_*.parquet"))])
    a = a.dropna(subset=["ticker"]).sort_values("time").drop_duplicates(["day", "ticker", "auction"])
    a["day"] = pd.to_datetime(a["day"])
    a["usd"] = a.price * a.shares                      # traded prices: $ size needs no split adjustment
    years = sorted(a.day.dt.year.unique())
    out = {}
    for kind in ["open", "close"]:
        x = a[a.auction == kind].pivot_table(index="day", columns="ticker", values="usd")
        out[kind] = x.reindex(index=P["on"].index, columns=P["on"].columns)
    return out["open"], out["close"], years


def sizes(op: pd.DataFrame, cl: pd.DataFrame, years: list[int]):
    """Actual size where pulled; else per-ETF median ratio to $ volume x trailing 63d median ADV (lagged).
    Also returns the lagged estimate alone (what you'd know before sending the order: used for the 10% cap)."""
    dv = P["dollar_vol"]
    adv = dv.rolling(63, min_periods=20).median().shift(1)
    pulled = pd.DataFrame(np.repeat(P["on"].index.year.isin(years)[:, None], dv.shape[1], 1),
                          index=dv.index, columns=dv.columns)
    actual, est, ratios = {}, {}, {}
    for kind, x in [("open", op), ("close", cl)]:
        ratios[kind] = (x / dv)[pulled].median()
        est[kind] = adv * ratios[kind]
        actual[kind] = x.where(pulled).fillna(est[kind])  # pulled day with no print -> estimate
    return actual, est, pd.DataFrame(ratios)


def cost(w: pd.DataFrame, aum: float, auc_open, auc_close, k_open: float, k_close: float) -> pd.Series:
    """Fees + impact, per night. Row t = the night ending at t's open: MOC buy at t-1's close, MOO sell at t's open."""
    cols = w.columns
    notional = w.abs() * aum
    sh = notional / P["price"][cols].shift(1)
    per_order = (np.maximum(C["min_commission_usd"], C["per_share_commission"] * sh)
                 + C["per_share_fees"] * sh).where(notional > 0, 0.0)
    sgm = P["cc"][cols].rolling(63, min_periods=20).std().shift(1)
    ac = auc_close[cols].shift(1)
    ao = auc_open[cols]
    imp = (k_close * sgm * np.sqrt(notional / ac) + k_open * sgm * np.sqrt(notional / ao)).fillna(0)
    c = 2 * per_order + (2 * C["auction_slippage_bps"] / 1e4 + imp) * notional + C["sec_fee_bps_on_sells"] / 1e4 * notional
    return c.sum(axis=1) / aum


def book(score: str, aum: float, model: str, actual: dict, est: dict) -> pd.Series:
    vs = vix_scale(P["on"].index)
    w = weights(P, members_from_scores(P, rk.scores(score, 24, aum), rk.K))
    w_on = (w * up_day_tilt(P, w, rk.sig.reindex(columns=w.columns))).mul(vs.reindex(w.index).fillna(1.0), axis=0)
    on = P["on"][w.columns]
    w_on = w_on.where(on.notna(), 0.0)
    cols = w.columns
    if model == "v1":
        ao = ac = P["dollar_vol"][cols].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
        cap = ao
        ko = kc = C["impact_coefficient"]
    else:
        ao, ac = actual["open"][cols], actual["close"][cols]
        cap = np.minimum(est["open"][cols], est["close"][cols].shift(1))  # known before the MOC order goes in
        ko, kc = (C["impact_coefficient"],) * 2 if model == "v2, k=0.1" else (0.145, 0.055)
    w_on = np.minimum(w_on, (0.10 * cap / aum).fillna(0))
    r = (w_on * on.fillna(0)).sum(axis=1) - cost(w_on, aum, ao, ac, ko, kc)
    return r.loc[r.ne(0).idxmax():]


def main():
    op, cl, years = auction_usd()
    actual, est, ratios = sizes(op, cl, years)
    ratios.to_csv(TAB / "auction_size_ratio.csv")
    v1_share = C["auction_share_of_adv"] / 2
    print(f"years with real auction sizes: {years}")
    print(f"median auction / daily $ volume across ETFs: open {ratios.open.median():.2%}, close {ratios.close.median():.2%}"
          f" (v1 assumed {v1_share:.2%} each)")
    rows = []
    for score in ["on_hit", "gap_sharpe"]:
        for aum in [10_000, 25_000, 50_000, 100_000, 250_000]:
            for model in ["v1", "v2, k=0.1", "v2, k fit"]:
                r = book(score, aum, model, actual, est)
                s = stats(r)
                yrs = r.groupby(r.index.year).apply(lambda x: (1 + x).prod() - 1)
                rows.append({"ranking": score, "aum": aum, "model": model,
                             **{f"sharpe_{p}": s.at["Sharpe", p] for p in s.columns},
                             "cagr_oos": s.at["CAGR", "2024-26"], "vol_oos": s.at["vol", "2024-26"],
                             "maxdd_oos": s.at["max DD", "2024-26"], "cagr_full": s.at["CAGR", "full"],
                             "maxdd_full": s.at["max DD", "full"], "years_up": s.at["years up", "full"],
                             **{f"ret_{y}": yrs.get(y, np.nan) for y in years}})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "impact_v2.csv", index=False)
    pd.set_option("display.width", 300)
    print(df.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
