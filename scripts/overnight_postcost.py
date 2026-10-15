"""Execution checks (MOO/MOC) on recent 1-minute data, and every strategy/overlay
re-run after realistic costs at a given account size:

  per order: max(min_commission, commission/share) + fees/share   (USD, from shares at that day's price)
           + SEC fee on sells/short sales + auction slippage + sqrt impact vs auction volume
  each leg trades twice a day (overnight: MOC buy, MOO sell; intraday short: MOO short, MOC cover).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from overnight_ingest import MINUTE
from overnight_research import C1, C2, C3, C4, GREY, TAB, load_panel, plt, save  # noqa: F401
from sput_research.overnight.data import CFG, load_daily, load_minute, load_vix
from sput_research.overnight.strategy import members_from_scores, month_scores, period, up_day_tilt, weights
from sput_research.statistics.metrics import cagr, max_drawdown, sharpe

C = CFG["costs"]
PERIODS = ["presample", "discovery", "oos"]
AUMS = [25_000, 100_000, 300_000]


def execution_checks() -> pd.DataFrame:
    rows = []
    for t in MINUTE:
        m, d = load_minute(t), load_daily(t)
        day = m.index.normalize()
        at = lambda hhmm, col: m[m.index.strftime("%H:%M") == hhmm].groupby(  # noqa: E731
            day[m.index.strftime("%H:%M") == hhmm])[col].last()
        x = pd.DataFrame({"o1": at("09:30", "Open"), "c0930": at("09:30", "Close"),
                          "c1549": at("15:49", "Close"), "c1559": at("15:59", "Close")}).join(
            d[["Open", "Close"]], how="inner")
        rows.append({
            "ticker": t, "days": len(x), "price": x.Close.mean(),
            "official_open_vs_first_trade_bps": ((x.Open / x.o1 - 1).abs() * 1e4).median(),
            "move_open_to_0931_bps": ((x.c0930 / x.Open - 1).abs() * 1e4).median(),
            "close_vs_1559_bps": ((x.Close / x.c1559 - 1).abs() * 1e4).median(),
            "close_vs_1550_bps": ((x.Close / x.c1549 - 1).abs() * 1e4).median(),
            "fee_bps_per_side": (C["per_share_commission"] + C["per_share_fees"]) / x.Close.mean() * 1e4,
        })
    df = pd.DataFrame(rows).set_index("ticker")
    df.to_csv(TAB / "execution_checks.csv")
    return df


def leg_cost(P, w: pd.DataFrame, aum: float, sells_per_day: int = 1, impact_on: bool = True) -> pd.Series:
    """Daily cost (fraction of AUM) of trading |w| in and out once (2 sides)."""
    cols = w.columns
    notional = w.abs() * aum
    shares = notional / P["price"][cols]
    per_order = np.maximum(C["min_commission_usd"], C["per_share_commission"] * shares) + C["per_share_fees"] * shares
    per_order = per_order.where(notional > 0, 0.0)
    sig = P["cc"][cols].rolling(63, min_periods=20).std().shift(1)
    auction = P["dollar_vol"][cols].rolling(63, min_periods=20).median().shift(1) * C["auction_share_of_adv"] / 2
    impact = C["impact_coefficient"] * sig * np.sqrt((notional / auction).clip(lower=0)) * float(impact_on)
    var_bps = (C["auction_slippage_bps"] / 1e4 + impact.fillna(0)) * 2 * notional
    sec = C["sec_fee_bps_on_sells"] / 1e4 * notional * sells_per_day
    return ((2 * per_order + var_bps + sec).sum(axis=1)) / aum


def run(P, aum: float, kind: str, vix_scale=None, spy_beta_hedge=False, impact_on=True,
        min_adv=None, universe=None) -> pd.Series:
    w = weights(P, members_from_scores(
        P, month_scores(P, CFG["final"]["lookback_months"], universe=universe, min_adv=min_adv),
        CFG["final"]["top_k"]))
    tilt = up_day_tilt(P, w) if kind.startswith("upday") else 1.0
    s = vix_scale.reindex(w.index).fillna(1.0) if vix_scale is not None else pd.Series(1.0, index=w.index)
    on, idr = P["on"][w.columns], P["id"][w.columns]
    w_on = (w * tilt).mul(s, axis=0).where(on.notna(), 0.0)
    w_id = w.mul(s, axis=0).where(idr.notna(), 0.0)
    gross, cost = pd.Series(0.0, index=w.index), pd.Series(0.0, index=w.index)
    if kind != "short_only":
        gross += (w_on * on.fillna(0)).sum(axis=1)
        cost += leg_cost(P, w_on, aum, impact_on=impact_on)
    if kind.endswith("LS") or kind == "short_only":
        gross -= (w_id * idr.fillna(0)).sum(axis=1)
        cost += leg_cost(P, w_id, aum, impact_on=impact_on)
    r = gross - cost
    r = r.loc[r.ne(0).idxmax():]
    if spy_beta_hedge:
        spy = P["cc"]["SPY"].reindex(r.index)
        beta = r.rolling(126, min_periods=60).cov(spy) / spy.rolling(126, min_periods=60).var()
        hold = (-beta).shift(1).clip(0, 1).fillna(0)
        trade = hold.diff().abs().fillna(0)
        r = r + hold * spy.fillna(0) - trade * (C["commission_bps"] + C["auction_slippage_bps"]) / 1e4
    return r


def main():
    print(execution_checks().round(2).to_string())
    P = load_panel()
    vix = load_vix().reindex(P["on"].index).ffill().shift(2)
    vs = (15 / vix).clip(upper=1.0)
    specs = [
        ("up-day LS + 15/VIX + long-SPY hedge", "upday_LS", vs, True),
        ("up-day LS (headline)", "upday_LS", None, False),
        ("up-day long overnight + 15/VIX", "upday_ON", vs, False),
        ("up-day long overnight only", "upday_ON", None, False),
        ("short-only (intraday leg)", "short_only", None, False),
    ]
    cases = [("fees only", 25_000, False, None), ("fees + impact", 25_000, True, None),
             ("fees + impact", 100_000, True, None), ("fees + impact", 300_000, True, None),
             ("fees + impact, ADV>=$20M", 100_000, True, 2e7), ("fees + impact, ADV>=$20M", 300_000, True, 2e7),
             ("fees + impact, ADV>=$50M", 300_000, True, 5e7)]
    rows = []
    for cost_lab, aum, imp, adv in cases:
        for lab, kind, sc, hedge in specs:
            r = run(P, aum, kind, sc, hedge, impact_on=imp, min_adv=adv)
            y = r.groupby(r.index.year).sum()
            rows.append({"costs": cost_lab, "aum": aum, "strategy": lab,
                         **{nm: sharpe(period(r, nm)) for nm in PERIODS},
                         "sharpe_full": sharpe(r), "cagr_full": cagr(r), "max_dd_full": max_drawdown(r)[0],
                         "vol_full": r.std() * np.sqrt(252), "years_green": f"{(y > 0).sum()}/{len(y)}",
                         "oos_cagr": cagr(period(r, "oos"))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "postcost.csv", index=False)
    print(df.round(2).to_string())

    fig, axs = plt.subplots(1, 3, figsize=(12, 4.3), sharey=True, layout="constrained")
    labs = [sp[0] for sp in specs]
    show = [("fees only", 25_000), ("fees + impact", 25_000), ("fees + impact", 100_000),
            ("fees + impact, ADV>=$20M", 100_000), ("fees + impact, ADV>=$20M", 300_000)]
    cols = [GREY, C1, C4, C3, C2]
    for ax, nm in zip(axs, PERIODS):
        y = np.arange(len(labs))
        for i, ((cl, aum), col) in enumerate(zip(show, cols)):
            d = df[(df.costs == cl) & (df.aum == aum)].set_index("strategy").reindex(labs)
            lab = f"{cl}, ${aum/1e3:g}k account".replace("$", r"\$")
            ax.barh(y + (i - 2) * 0.16, d[nm], height=0.15, color=col, label=lab)
        ax.set_yticks(y, labs)
        ax.invert_yaxis()
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(nm)
        ax.set_xlabel("net Sharpe")
    h, lb = axs[0].get_legend_handles_labels()
    fig.legend(h, lb, loc="outside lower center", ncol=5, fontsize=7, frameon=False)
    fig.suptitle("everything post-costs: per-share fees + SEC + auction slippage (+ sqrt impact), by account size")
    fig.set_layout_engine("constrained")
    save(fig, "19_postcost.png")


if __name__ == "__main__":
    main()
