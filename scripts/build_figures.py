"""Generate the report figure set into reports/figures/. Full ranges, no
cherry-picking; structural break and missing data marked explicitly."""

from __future__ import annotations

import json

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import yaml

from sput_research.nav.synthetic import build_returns_frame
from sput_research.paths import CONFIG, FIGURES, PROCESSED, TABLES
from sput_research.statistics.metrics import sharpe
from sput_research.statistics.walkforward import holdout_split
from sput_research.strategies.families import (
    FAMILY_BUILDERS, family_F_spread, price_frame, run_legs, sprott_frame,
)

CFG = yaml.safe_load((CONFIG / "preregistered_parameters.yaml").read_text())
plt.rcParams.update({"figure.dpi": 130, "font.size": 8, "axes.grid": True,
                     "grid.alpha": 0.3, "figure.autolayout": True})


def save(fig, name):
    fig.savefig(FIGURES / name)
    plt.close(fig)
    print("wrote", name)


def main() -> int:
    s = sprott_frame()
    prem = s["premium_discount_published"].dropna()
    nav = s["nav_usd"]
    price = s["price_usd_published"]

    # 1. price vs NAV
    fig, ax = plt.subplots(figsize=(9, 3.5))
    ax.plot(nav.index, nav, label="Published NAV (USD)", lw=0.9)
    ax.plot(price.index, price, label="U.U market price (USD)", lw=0.9)
    ax.axvline(pd.Timestamp("2021-07-26"), color="k", ls=":", lw=0.8)
    ax.set_title("SPUT market price vs published NAV (structural break dotted)")
    ax.legend()
    save(fig, "01_price_vs_nav.png")

    # 2-4. premium history, distribution, rolling stats
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.fill_between(prem.index, prem * 100, 0, alpha=0.6)
    ax.set_title("Premium/discount to NAV (%)")
    save(fig, "02_premium_history.png")

    fig, ax = plt.subplots(figsize=(5, 3))
    ax.hist(prem * 100, bins=60)
    ax.axvline(0, color="k", lw=0.8)
    ax.set_title("Premium/discount distribution (%)")
    save(fig, "03_premium_distribution.png")

    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(prem.rolling(60).mean() * 100, label="60d mean")
    ax.plot(prem.rolling(60).std() * 100, label="60d std")
    ax.set_title("Rolling premium mean and volatility (%)")
    ax.legend()
    save(fig, "04_premium_rolling.png")

    # 5. autocorrelation / half-life
    dp = prem.dropna()
    ac = [dp.autocorr(k) for k in range(1, 61)]
    rho1 = ac[0]
    halflife = np.log(0.5) / np.log(rho1) if 0 < rho1 < 1 else np.nan
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(range(1, 61), ac)
    ax.set_title(f"Premium autocorrelation (AR1={rho1:.3f}, level half-life≈{halflife:.0f}d)")
    save(fig, "05_premium_autocorr.png")

    # 6-7. forward returns by discount decile, and conditioned on NAV trend
    px_uun = price_frame("U-UN.TO")["close"]
    fwd20 = px_uun.pct_change(20).shift(-20)
    dec = pd.qcut(prem.reindex(px_uun.index), 10, labels=False)
    by_dec = fwd20.groupby(dec).mean() * 100
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(by_dec.index.astype(int), by_dec.values)
    ax.set_title("Mean 20d forward U.UN return (%) by premium decile (0=deepest discount)\n"
                 "NOTE: overlapping windows; indicative only")
    save(fig, "06_fwd_by_decile.png")

    trend_ok = nav >= nav.rolling(120, min_periods=60).mean()
    grp = pd.DataFrame({"fwd": fwd20, "dec": (prem.reindex(px_uun.index) <= prem.quantile(0.2)),
                        "trend": trend_ok.reindex(px_uun.index)}).dropna()
    tbl = grp.groupby(["dec", "trend"])["fwd"].mean() * 100
    fig, ax = plt.subplots(figsize=(5, 3))
    tbl.unstack().plot.bar(ax=ax)
    ax.set_title("20d fwd return (%): deep discount x NAV trend")
    ax.legend(["downtrend", "uptrend"], title="NAV>=120d SMA")
    save(fig, "07_fwd_discount_x_trend.png")

    # 8. lead-lag: market price vs next NAV change
    rf = build_returns_frame()
    lags = range(-5, 6)
    cc = [rf["price_ret"].corr(rf["nav_ret"].shift(-k)) for k in lags]
    fig, ax = plt.subplots(figsize=(6, 3))
    ax.bar(list(lags), cc)
    ax.set_title("corr(price return t, NAV return t+k) — positive k: price leads NAV")
    save(fig, "08_price_nav_leadlag.png")

    # 9-10. holdings & acquisitions vs premium (units outstanding UNAVAILABLE - noted)
    fig, axes = plt.subplots(2, 1, figsize=(9, 5), sharex=True)
    axes[0].plot(s["u3o8_lbs"].dropna() / 1e6, marker=".", ms=2, lw=0.7)
    axes[0].set_title("U3O8 held (Mlbs, weekly) — units-outstanding history NOT published")
    acq = s["lbs_acquired"].dropna()
    axes[1].bar(acq.index, acq / 1e6, width=3)
    ax2 = axes[1].twinx()
    ax2.plot(prem * 100, color="C1", lw=0.7)
    ax2.set_ylabel("premium %")
    axes[1].set_title("Uranium acquisitions (Mlbs) vs premium/discount")
    save(fig, "09_holdings_acquisitions.png")

    # 11. SPUT vs YCA relative spread
    sput_usd = price_frame("U-UN.TO", usd=True)["close"]
    yca_usd = price_frame("YCA.L", usd=True)["close"]
    ratio = np.log(sput_usd) - np.log(yca_usd.reindex(sput_usd.index).ffill(limit=3))
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(ratio)
    ax.set_title("log(SPUT USD) - log(YCA USD) relative-value spread")
    save(fig, "11_sput_yca_spread.png")

    # 12. cross-line residual
    a = family_F_spread()
    fig, ax = plt.subplots(figsize=(9, 3))
    ax.plot(a["spread"] * 1e4)
    ax.set_title("U.UN vs FX-adjusted U.U log spread (bps) — not tradeable net of costs")
    save(fig, "12_crossline_spread.png")

    # 13-15. equity curves / drawdown / rolling sharpe for holdout-evaluated families
    hold = pd.read_csv(TABLES / "holdout_results.csv")
    fig1, ax1 = plt.subplots(figsize=(9, 3.5))
    fig2, ax2 = plt.subplots(figsize=(9, 3))
    fig3, ax3 = plt.subplots(figsize=(9, 3))
    for _, h in hold.iterrows():
        legs = FAMILY_BUILDERS[h["family"]](json.loads(h["params"]))
        r = run_legs(legs, 1.0, 0)
        dev_idx, hold_idx = holdout_split(r.index, CFG["sample"]["holdout_frac"])
        eq = (1 + r.fillna(0)).cumprod()
        ax1.plot(eq, label=h["family"], lw=0.9)
        dd = eq / eq.cummax() - 1
        ax2.plot(dd, label=h["family"], lw=0.8)
        ax3.plot(r.rolling(126).mean() / r.rolling(126).std() * np.sqrt(252),
                 label=h["family"], lw=0.8)
    for ax in (ax1, ax2, ax3):
        ax.axvline(hold_idx[0], color="r", ls="--", lw=1)
        ax.legend(fontsize=7)
    ax1.set_title("Net equity curves (frozen modal params; red dashes = untouched holdout start)")
    ax2.set_title("Drawdown")
    ax3.set_title("Rolling 6m Sharpe")
    save(fig1, "13_equity_curves.png")
    save(fig2, "14_drawdowns.png")
    save(fig3, "15_rolling_sharpe.png")

    # 16. parameter sensitivity surface for G (z_window x entry_z), dev sample only
    from sput_research.strategies.families import family_G
    zs, es = CFG["grids"]["z_window"], CFG["grids"]["entry_z"]
    surf = np.zeros((len(zs), len(es)))
    for i, zw in enumerate(zs):
        for j, ez in enumerate(es):
            r = run_legs(family_G({"z_window": zw, "entry_z": ez, "exit_z": 0.5,
                                   "holding_cap_days": 10}), 1.0, 0)
            didx, _ = holdout_split(r.index, CFG["sample"]["holdout_frac"])
            surf[i, j] = sharpe(r.loc[didx])
    fig, ax = plt.subplots(figsize=(5, 3.5))
    im = ax.imshow(surf, cmap="RdYlGn", vmin=-1, vmax=2.5)
    ax.set_xticks(range(len(es)), es)
    ax.set_yticks(range(len(zs)), zs)
    ax.set_xlabel("entry_z")
    ax.set_ylabel("z_window")
    for i in range(len(zs)):
        for j in range(len(es)):
            ax.text(j, i, f"{surf[i, j]:.1f}", ha="center", va="center", fontsize=7)
    fig.colorbar(im)
    ax.set_title("G_sput_yca dev-sample net Sharpe surface")
    save(fig, "16_param_surface_G.png")

    # 17. cost sensitivity
    rob = pd.read_csv(TABLES / "robustness_results.csv")
    rob = rob[rob["status"] == "tested"].set_index("family")
    fig, ax = plt.subplots(figsize=(6, 3))
    for fam in rob.index:
        ys = [rob.loc[fam, "sharpe_0.5x_cost"], rob.loc[fam, "dev_sharpe_1x"],
              rob.loc[fam, "sharpe_2.0x_cost"], rob.loc[fam, "sharpe_3.0x_cost"]]
        ax.plot([0.5, 1, 2, 3], ys, marker="o", label=fam)
    ax.set_xlabel("cost multiplier")
    ax.set_ylabel("dev net Sharpe")
    ax.legend(fontsize=7)
    ax.set_title("Cost sensitivity")
    save(fig, "17_cost_sensitivity.png")

    # 18. capacity curves
    cap = pd.read_csv(TABLES / "capacity_results.csv")
    fig, ax = plt.subplots(figsize=(6, 3))
    for fam, g in cap.groupby("family"):
        ax.plot(g["capital_usd"] / 1e6, g["net_sharpe_with_impact"], marker="o", label=fam)
    ax.set_xscale("log")
    ax.set_xlabel("capital ($M)")
    ax.set_ylabel("net Sharpe incl. impact")
    ax.legend(fontsize=7)
    ax.set_title("Capacity (full-sample, sqrt impact, 5% ADV cap)")
    save(fig, "18_capacity.png")

    # 19-20. PnL by year and best-trades-removed for G
    legs = FAMILY_BUILDERS["G_sput_yca"](json.loads(hold.set_index("family").loc["G_sput_yca", "params"]))
    r = run_legs(legs, 1.0, 0)
    fig, ax = plt.subplots(figsize=(6, 3))
    (r.groupby(r.index.year).sum() * 100).plot.bar(ax=ax)
    ax.set_title("G_sput_yca net PnL by year (%, full sample)")
    save(fig, "19_pnl_by_year.png")

    pos = legs[0].target_pos.reindex(r.index).ffill().fillna(0.0).shift(1).fillna(0.0)
    blocks, cur, start = [], 0.0, None
    for d in r.index:
        if pos.loc[d] != 0:
            if start is None:
                start = d
            cur += float(r.get(d, 0.0))
        elif start is not None:
            blocks.append((start, d, cur))
            cur, start = 0.0, None
    blocks.sort(key=lambda b: -b[2])
    fig, ax = plt.subplots(figsize=(6, 3))
    for n in [0, 1, 3, 5]:
        drop = {b[0] for b in blocks[:n]}
        mask = pd.Series(True, index=r.index)
        for b in blocks[:n]:
            mask.loc[b[0]:b[1]] = False
        rr = r.where(mask, 0.0)
        ax.plot((1 + rr).cumprod(), lw=0.9, label=f"drop best {n} trades (SR {sharpe(rr):.2f})")
    ax.legend(fontsize=7)
    ax.set_title("G_sput_yca: equity after removing best trades")
    save(fig, "20_best_trades_removed.png")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
