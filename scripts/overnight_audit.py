"""Audit of the headline strategy (#1: up-day long overnight + 15/VIX) before trusting it.

1. Independent re-implementation straight from the raw Yahoo bars (own return split,
   ranking, weights, costs, day-by-day loop) must reproduce the library P&L.
2. Decision time: the up-day signal used the official close, which is not known when a
   MOC order must be in. Re-run 2024-26 with the signal at 15:30 (hourly bars).
3. Lookahead: scrambling every price after a cutoff must not change P&L before it.
4. Data hygiene: how often a held name's night is dropped by the stale/|on|>30% filters.
5. What $50k would have made, year by year.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from overnight_postcost import run
from overnight_research import TAB, load_panel
from sput_research.overnight.data import CFG, load_daily, load_hourly, load_vix, tradeable_universe
from sput_research.statistics.metrics import max_drawdown, sharpe

C, F = CFG["costs"], CFG["final"]
AUM = 50_000


def vix_scale(idx):
    return (15 / load_vix().reindex(idx).ffill().shift(2)).clip(upper=1.0)


# ---------------------------------------------------------------- 1. independent re-implementation
def independent(aum: float, min_adv: float) -> pd.Series:
    on, idr, dv, px, cc = {}, {}, {}, {}, {}
    for t in tradeable_universe():
        d = load_daily(t)
        adj_open = d.Open * d.AdjClose / d.Close
        flat = (d.Open == d.High) & (d.High == d.Low) & (d.Low == d.Close)
        bad = (d.Volume <= 0) | (d.Open <= 0) | flat
        o = adj_open / d.AdjClose.shift() - 1
        o[bad | bad.shift(fill_value=True) | (o.abs() > CFG["data"]["max_abs_overnight"])] = np.nan
        i = d.Close / d.Open - 1
        i[bad] = np.nan
        c = d.AdjClose.pct_change(fill_method=None)
        c[bad | bad.shift(fill_value=True)] = np.nan
        on[t], idr[t], dv[t], px[t], cc[t] = o, i, d.Close * d.Volume, d.Close, c
    on, idr, dv, px, cc = (pd.DataFrame(x).sort_index() for x in (on, idr, dv, px, cc))
    days = on.index
    vs = vix_scale(days)
    adv63 = dv.rolling(63, min_periods=40).median()
    vol63 = on.rolling(63, min_periods=40).std()
    sig63 = cc.rolling(63, min_periods=20).std()
    auction = dv.rolling(63, min_periods=20).median() * C["auction_share_of_adv"] / 2
    L, K = F["lookback_months"], F["top_k"]
    picks, month = {}, None
    pnl = pd.Series(0.0, index=days)
    for k, t in enumerate(days):
        if (t.year, t.month) != month:  # month start: rank on data strictly before t
            month = (t.year, t.month)
            win = (days < t) & (days >= t - pd.DateOffset(months=L))
            x = (on - idr)[win]
            sc = x.mean() / x.std() * np.sqrt(252)
            ok = (x.count() >= int(0.8 * L * 21)) & (adv63[days < t].iloc[-1] >= min_adv) if k else None
            sc = sc[ok].dropna() if k else pd.Series(dtype=float)
            picks = list(sc[sc > 0].sort_values(ascending=False).index[:K])
        if not picks or k < 2:
            continue
        prev = days[k - 1]
        iv = 1 / vol63.loc[prev, picks]
        iv = iv[np.isfinite(iv)]
        if iv.empty:
            continue
        w = iv / iv.sum()
        up = w[idr.loc[prev, w.index] > 0]
        if up.empty:
            continue
        w = up / up.sum() * vs.loc[t] if np.isfinite(vs.loc[t]) else up / up.sum()
        r = on.loc[t, w.index]
        w = w[r.notna()]
        if w.empty:
            continue
        notional = w * aum
        sh = notional / px.loc[t, w.index]
        per_order = np.maximum(C["min_commission_usd"], C["per_share_commission"] * sh) + C["per_share_fees"] * sh
        imp = (C["impact_coefficient"] * sig63.loc[prev, w.index]
               * np.sqrt(notional / auction.loc[prev, w.index])).fillna(0)
        cost = (2 * per_order + (C["auction_slippage_bps"] / 1e4 + imp) * 2 * notional
                + C["sec_fee_bps_on_sells"] / 1e4 * notional).sum()
        pnl.loc[t] = (w * r[w.index]).sum() - cost / aum
    return pnl.loc[pnl.ne(0).idxmax():]


# ---------------------------------------------------------------- 2. decision-time signal
def signal_1530(P) -> pd.DataFrame:
    """open -> 15:30 return (open of the last hourly bar) where hourly bars exist, else NaN."""
    out = {}
    for t in tradeable_universe():
        h = load_hourly(t)
        h = h[h.index.strftime("%H:%M") == "15:30"]
        p1530 = pd.Series(h.Open.values, index=h.index.normalize())
        out[t] = p1530 / P["price"][t].reindex(p1530.index) * (1 + P["id"][t].reindex(p1530.index)) - 1
    return pd.DataFrame(out).reindex(P["id"].index)


def main():
    P = load_panel()
    vs = vix_scale(P["on"].index)
    rows = []

    # 1
    for lab, adv in [("all names", CFG["data"]["min_dollar_adv"]), ("ADV>=$20M", 2e7)]:
        lib = run(P, AUM, "upday_ON", vs, impact_on=True, min_adv=adv)
        ind = independent(AUM, adv)
        j = pd.concat([lib, ind], axis=1, keys=["lib", "ind"]).fillna(0)
        rows.append({"check": f"re-implementation, {lab}", "days": len(j),
                     "corr": j.corr().iloc[0, 1], "max_abs_diff_bps": (j.lib - j.ind).abs().max() * 1e4,
                     "sharpe_lib": sharpe(j.lib), "sharpe_ind": sharpe(j.ind)})

    # 2
    s = signal_1530(P)
    sig = P["id"][s.columns].copy()
    have = s.notna() & sig.notna()
    sig[have] = s[have]  # 15:30 signal wherever hourly bars exist (all of 2024-26)
    agree = ((s > 0) == (P["id"][s.columns] > 0))[have].stack().mean()
    for lab, adv in [("all names", None), ("ADV>=$20M", 2e7)]:
        for sl, sg in [("close (as published)", None), ("15:30 (tradeable)", sig)]:
            r = run(P, AUM, "upday_ON", vs, impact_on=True, min_adv=adv, signal=sg).loc["2024":]
            rows.append({"check": f"signal at {sl}, {lab}, 2024-26", "sharpe": sharpe(r),
                         "ann_return": np.expm1(np.log1p(r).mean() * 252), "max_dd": max_drawdown(r)[0],
                         "signal_agreement": agree})

    # 3
    cut = pd.Timestamp("2021-06-15")
    Q = {k: v.copy() for k, v in P.items()}
    rng = np.random.default_rng(0)
    for k in ["on", "id", "cc", "dollar_vol"]:
        late = Q[k].index > cut
        Q[k].loc[late] = Q[k].loc[late].values[rng.permutation(late.sum())]
    a = run(P, AUM, "upday_ON", vs, impact_on=True).loc[:cut]
    b = run(Q, AUM, "upday_ON", vs, impact_on=True).loc[:cut]
    rows.append({"check": "future scrambled after 2021-06-15", "max_abs_diff_bps": (a - b).abs().max() * 1e4})

    # 4
    w = run.__globals__["weights"](P, run.__globals__["members_from_scores"](
        P, run.__globals__["month_scores"](P, F["lookback_months"]), F["top_k"]))
    held = w > 0
    dropped = (held & P["on"][w.columns].isna()).sum().sum() / held.sum().sum()
    rows.append({"check": "held-name nights dropped by data filters", "share": dropped})

    pd.DataFrame(rows).to_csv(TAB / "audit.csv", index=False)
    print(pd.DataFrame(rows).round(4).to_string())

    # 5
    yr = {}
    for lab, adv in [("all names", None), ("ADV>=$20M", 2e7)]:
        for cl, imp in [("fees only", False), ("fees + impact", True)]:
            r = run(P, AUM, "upday_ON", vs, impact_on=imp, min_adv=adv)
            yr[f"{lab}, {cl}"] = r.groupby(r.index.year).apply(lambda x: np.expm1(np.log1p(x).sum()))
    r = run(P, AUM, "upday_ON", vs, impact_on=True, min_adv=2e7, signal=sig)
    yr["ADV>=$20M, fees + impact, 15:30 signal"] = r.groupby(r.index.year).apply(
        lambda x: np.expm1(np.log1p(x).sum())).loc[2024:]
    yr = pd.DataFrame(yr)
    yr.to_csv(TAB / "audit_50k_by_year.csv")
    print((yr * 100).round(1).to_string())


if __name__ == "__main__":
    main()
