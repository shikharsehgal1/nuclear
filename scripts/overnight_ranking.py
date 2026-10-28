"""Which ranking picks the ETFs best? #1 as traded, only the monthly selection score changes.

Base: #1 at $50k, fees + impact, ADV >= $20M, 15:30 up-day signal, 15/VIX, 10% auction cap.
Each score is computed at month start on data strictly before it, over the trailing L months;
the top 5 positive scores are held (inverse-vol weights, as in the frozen rule).

Scores (x = daily series over the lookback):
  gap_sharpe     Sharpe of (overnight - intraday)              [frozen rule]
  gap_mean       mean of (overnight - intraday)
  on_sharpe      Sharpe of overnight
  on_mean        mean of overnight
  on_hit         share of nights up, minus 50%
  id_neg_sharpe  -Sharpe of intraday (worst day-session first)
  id_neg_mean    -mean of intraday
  upnight_sharpe Sharpe of overnight on nights after an up day (the nights #1 actually holds)
  on_net_sharpe  (mean overnight - est. round-trip cost at this account size) / std: cost-aware
  all_equal      no ranking: every liquid ETF with positive gap_sharpe, equal score (top 5 by ADV)

Pick rule: best 2016-23 Sharpe ("discovery") only; 2024-26 is reported, never used to choose.
Also run with no costs at all, to separate picking skill from cost.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

import overnight_risk as base
from overnight_auction_rules import name_costs
from overnight_audit import vix_scale
from overnight_research import TAB
from sput_research.overnight.data import CFG, tradeable_universe
from sput_research.overnight.strategy import members_from_scores, month_starts, up_day_tilt, weights

P, sig, AUM, ADV, stats = base.P, base.sig, base.AUM, base.ADV, base.stats
C = CFG["costs"]
K = CFG["final"]["top_k"]
SCORES = ["gap_sharpe", "gap_mean", "on_sharpe", "on_mean", "on_hit", "id_neg_sharpe", "id_neg_mean",
          "upnight_sharpe", "on_net_sharpe", "all_equal"]


def est_cost(uni, aum: float) -> pd.DataFrame:
    """Round-trip cost estimate (fraction) per name per day for a 1/K slot of the account."""
    px = P["price"][uni]
    sgm = P["cc"][uni].rolling(63, min_periods=20).std()
    auc = P["dollar_vol"][uni].rolling(63, min_periods=20).median() * C["auction_share_of_adv"] / 2
    q = aum / K
    imp = C["impact_coefficient"] * sgm * np.sqrt(q / auc)
    fee = (np.maximum(C["min_commission_usd"], C["per_share_commission"] * q / px) + C["per_share_fees"] * q / px) / q
    return 2 * (C["auction_slippage_bps"] / 1e4 + imp + fee) + C["sec_fee_bps_on_sells"] / 1e4


def scores(score: str, L: int, aum: float = AUM) -> dict:
    uni = [t for t in tradeable_universe() if t in P["on"]]
    on, idr = P["on"][uni], P["id"][uni]
    x = {"gap_sharpe": on - idr, "gap_mean": on - idr, "on_sharpe": on, "on_mean": on, "on_hit": on,
         "id_neg_sharpe": idr, "id_neg_mean": idr, "upnight_sharpe": on.where(idr.shift(1) > 1e-9),
         "on_net_sharpe": on, "all_equal": on - idr}[score]
    cost = est_cost(uni, aum) if score == "on_net_sharpe" else None
    adv = P["dollar_vol"][uni].rolling(63, min_periods=40).median()
    min_obs = int(0.8 * L * 21 * (0.5 if score == "upnight_sharpe" else 1))
    out = {}
    for m in month_starts(on.index):
        win = (x.index < m) & (x.index >= m - pd.DateOffset(months=L))
        h = x[win]
        prev = adv[adv.index < m]
        if prev.empty:
            continue
        mu, sd = h.mean(), h.std()
        sc = {"gap_sharpe": mu / sd, "gap_mean": mu, "on_sharpe": mu / sd, "on_mean": mu,
              "on_hit": (h > 0).sum() / h.count() - 0.5, "id_neg_sharpe": -mu / sd, "id_neg_mean": -mu,
              "upnight_sharpe": mu / sd, "all_equal": mu / sd}.get(score)
        if score == "on_net_sharpe":
            c = cost[cost.index < m].iloc[-1] if (cost.index < m).any() else np.nan
            sc = (mu - c) / sd
        if score == "all_equal":  # every positive name, ranked by liquidity instead of score
            sc = prev.iloc[-1].where(sc > 0)
        ok = (h.count() >= min_obs) & (prev.iloc[-1] >= ADV)
        out[m] = sc[ok].dropna()
    return out


def book(score: str, L: int, aum: float = AUM, costs: bool = True) -> pd.Series:
    vs = vix_scale(P["on"].index)
    w = weights(P, members_from_scores(P, scores(score, L, aum), K))
    tilt = up_day_tilt(P, w, sig.reindex(columns=w.columns) if set(w.columns) <= set(sig.columns) else None)
    on = P["on"][w.columns]
    w_on = (w * tilt).mul(vs.reindex(w.index).fillna(1.0), axis=0).where(on.notna(), 0.0)
    auc = P["dollar_vol"][w.columns].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
    w_on = np.minimum(w_on, (0.10 * auc / aum).reindex_like(w_on).fillna(0))
    r = (w_on * on.fillna(0)).sum(axis=1)
    if costs:
        r = r - name_costs(w_on, aum).sum(axis=1)
    return r.loc[r.ne(0).idxmax():]


def main():
    rows = []
    for score in SCORES:
        for L in [6, 12, 24, 36]:
            for costs in [True, False]:
                s = stats(book(score, L, costs=costs))
                rows.append({"score": score, "lookback_m": L, "costs": "fees+impact" if costs else "none",
                             **{f"sharpe_{p}": s.at["Sharpe", p] for p in s.columns},
                             "cagr_oos": s.at["CAGR", "2024-26"], "maxdd_full": s.at["max DD", "full"]})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "ranking_scores.csv", index=False)
    pd.set_option("display.width", 250)
    for c in ["fees+impact", "none"]:
        d = df[df.costs == c].sort_values("sharpe_2016-23", ascending=False)
        print(f"\n== {c}, sorted by 2016-23 (the pick period) ==")
        print(d.drop(columns="costs").round(2).to_string(index=False))
    # the frozen score vs the overnight-based scores, by account size
    size = []
    for aum in [10_000, 25_000, 50_000, 100_000, 250_000]:
        for sc, L in [("gap_sharpe", 24), ("on_net_sharpe", 24), ("on_mean", 12), ("on_mean", 24), ("on_hit", 24)]:
            s = stats(book(sc, L, aum))
            size.append({"aum": aum, "score": f"{sc} {L}m", **s.loc["Sharpe"].to_dict(),
                         "cagr_oos": s.at["CAGR", "2024-26"], "dd_full": s.at["max DD", "full"],
                         "dd_oos": s.at["max DD", "2024-26"]})
    size = pd.DataFrame(size)
    size.to_csv(TAB / "ranking_scores_size.csv", index=False)
    print("\n", size.round(2).to_string(index=False))

if __name__ == "__main__":
    main()
