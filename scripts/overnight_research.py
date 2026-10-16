"""Overnight-drift study: grid, frozen strategies on pre-sample / discovery / OOS,
cost + capacity + robustness, exit-timing check, figures. Writes to reports/overnight/.

Optional: KIBOT_DIR=/path/to/KIBOT (licensed 5-min bars, not committed) adds the
2016-23 intraday exit-timing panel."""

from __future__ import annotations

import os
from pathlib import Path

import matplotlib
import matplotlib.ticker
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap

from sput_research.overnight.data import CFG, load_hourly, panel, tradeable_universe
from sput_research.overnight.strategy import backtest, final_strategy, period, select, up_day_tilt, weights
from sput_research.paths import PROCESSED, REPORTS
from sput_research.statistics.metrics import (
    cagr, deflated_sharpe, max_drawdown, sharpe, stationary_bootstrap_sharpe_ci,
)

OUT = REPORTS / "overnight"
FIG, TAB = OUT / "figures", OUT / "tables"
for p in (FIG, TAB):
    p.mkdir(parents=True, exist_ok=True)

# validated categorical order (blue, orange, aqua, yellow) + neutral
C1, C2, C3, C4, GREY = "#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#8a8984"
DIVERGE = LinearSegmentedColormap.from_list("div", [C2, "#e8e6e1", C1])
plt.rcParams.update({"figure.dpi": 130, "font.size": 8, "axes.grid": True, "grid.alpha": 0.25,
                     "axes.spines.top": False, "axes.spines.right": False, "figure.autolayout": True,
                     "lines.linewidth": 1.4})
STRATS = list(CFG["final"]["strategies"])
LABEL = {"core_ON": "core ON", "core_LS": "core LS", "upday_ON": "up-day ON", "upday_LS": "up-day LS"}
COLOR = {"core_ON": C1, "core_LS": C3, "upday_ON": C2, "upday_LS": C4}
PERIODS = ["presample", "discovery", "oos"]
N_TRIALS = CFG["final"]["n_trials_for_dsr"]


def save(fig, name):
    fig.savefig(FIG / name)
    plt.close(fig)
    print("wrote", name)


def end_labels(ax, items, min_gap=0.12):
    """Direct labels at line ends, nudged apart in log10 space so they never collide."""
    items = sorted(items, key=lambda x: x[1])
    ys = []
    for _, y, _ in items:
        ly = np.log10(y)
        ys.append(max(ly, ys[-1] + min_gap) if ys else ly)
    for (lab, _, x), ly in zip(items, ys):
        ax.annotate(lab, (x, 10 ** ly), xytext=(3, 0), textcoords="offset points",
                    fontsize=7, va="center", color="#52514e")


def shade(ax):
    for nm, col in [("presample", "#efeeea"), ("oos", "#e3edf9")]:
        a, b = CFG["periods"][nm]
        ax.axvspan(pd.Timestamp(a), pd.Timestamp(b), color=col, zorder=0, lw=0)
    ax.axvline(pd.Timestamp(CFG["periods"]["oos"][0]), color="#e34948", ls="--", lw=1)


def stats_row(r: pd.Series) -> dict:
    r = r.dropna()
    mdd, _ = max_drawdown(r)
    return {"sharpe": sharpe(r), "cagr": cagr(r), "ann_mean": r.mean() * 252,
            "vol": r.std() * np.sqrt(252), "max_dd": mdd, "n_days": len(r)}


def load_panel() -> dict:
    f = PROCESSED / "overnight_panel.pkl"
    if not f.exists():
        pd.to_pickle(panel(), f)
    return pd.read_pickle(f)


# ---------------------------------------------------------------------------
def ticker_split(P):
    rows = []
    for t in P["on"].columns:
        for nm in ["discovery", "oos"]:
            on, idr = period(P["on"][t], nm).dropna(), period(P["id"][t], nm).dropna()
            if len(on) < 100:
                continue
            ls = (on - idr).dropna()
            rows.append({"ticker": t, "period": nm, "overnight_ann": on.mean() * 252,
                         "intraday_ann": idr.mean() * 252, "sharpe_on_minus_id": sharpe(ls),
                         "traded": t in tradeable_universe()})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "ticker_split.csv", index=False)

    full = pd.DataFrame({t: {"on": P["on"][t]["2016":].mean() * 252, "id": P["id"][t]["2016":].mean() * 252}
                         for t in P["on"].columns}).T.sort_values("on")
    fig, ax = plt.subplots(figsize=(7, 7.5))
    y = np.arange(len(full))
    ax.barh(y + 0.2, full["on"] * 100, height=0.4, color=C1, label="overnight (close → open)")
    ax.barh(y - 0.2, full["id"] * 100, height=0.4, color=C2, label="intraday (open → close)")
    ax.set_yticks(y, full.index)
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("annualised return, 2016 – 2026-10 (%)")
    ax.set_title("where the return happens: overnight vs intraday, every ETF in the universe")
    ax.legend(loc="lower right")
    save(fig, "01_overnight_vs_intraday.png")

    fig, axs = plt.subplots(2, 2, figsize=(9, 5.5))
    for ax, t in zip(axs.flat, ["URNM", "COPX", "SIL", "GLD"]):
        start = max(pd.Timestamp("2016-01-01"), P["on"][t].first_valid_index())
        on, idr, cc = P["on"][t][start:], P["id"][t][start:], P["cc"][t][start:]
        ends = []
        for s, c, lab in [(cc, GREY, "buy & hold"), (on, C1, "overnight only"), (idr, C2, "intraday only")]:
            eq = np.exp(np.log1p(s.fillna(0)).cumsum())
            ax.plot(eq.index, eq, color=c, label=lab)
            ends.append((lab, eq.iloc[-1], eq.index[-1]))
        ax.set_yscale("log")
        ax.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"{v:g}"))
        ax.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
        end_labels(ax, ends)
        ax.set_title(t)
    axs[0, 0].legend(loc="upper left", fontsize=7)
    fig.suptitle("$1 held only overnight vs only during the session (gross, log scale)")
    save(fig, "02_cumulative_split.png")


def grid(P):
    rows = []
    for L in CFG["strategy"]["grid"]["lookback_months"]:
        for K in CFG["strategy"]["grid"]["top_k"]:
            w = weights(P, select(P, L, K))
            for v in ["ON", "LS"]:
                for sc in ["auction", "spread"]:
                    r = backtest(P, w, v, sc).net
                    for nm in PERIODS:
                        rows.append({"lookback_m": L, "top_k": K, "variant": v, "costs": sc,
                                     "period": nm, "sharpe": sharpe(period(r, nm))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "grid.csv", index=False)
    fig, axs = plt.subplots(2, 3, figsize=(9, 5))
    for i, v in enumerate(["ON", "LS"]):
        for j, nm in enumerate(PERIODS):
            m = df[(df.variant == v) & (df.costs == "auction") & (df.period == nm)].pivot(
                index="lookback_m", columns="top_k", values="sharpe")
            ax = axs[i, j]
            ax.imshow(m.values, cmap=DIVERGE, vmin=-2.5, vmax=2.5)
            ax.grid(False)
            ax.set_xticks(range(m.shape[1]), m.columns)
            ax.set_yticks(range(m.shape[0]), m.index)
            for (a, b), val in np.ndenumerate(m.values):
                ax.text(b, a, f"{val:.2f}", ha="center", va="center", fontsize=8,
                        weight="bold" if (m.index[a], m.columns[b]) == (24, 5) else "normal")
            ax.set_title(f"{v} · {nm}")
            ax.set_xlabel("top K")
            ax.set_ylabel("lookback (months)")
    fig.suptitle("net Sharpe across the whole pre-registered grid (auction costs). bold = frozen pick")
    save(fig, "04_param_surface.png")
    return df


def headline(P):
    rows, curves = [], {}
    for s in STRATS:
        for sc in ["auction", "spread", "spread_2x"]:
            r = final_strategy(P, s, sc)
            if sc == "auction":
                curves[s] = r
            for nm in PERIODS + ["full"]:
                x = r.net.loc[CFG["periods"]["presample"][0]:] if nm == "full" else period(r.net, nm)
                x = x.loc[x.ne(0).idxmax():] if nm in ("presample", "full") else x  # drop pre-first-trade zeros
                row = {"strategy": s, "costs": sc, "period": nm, **stats_row(x),
                       "exposure": period(r.exposure, nm).mean() if nm != "full" else r.exposure.mean()}
                if sc == "auction" and nm == "oos":
                    row["dsr"] = deflated_sharpe(x, N_TRIALS)
                    row["boot_lo"], row["boot_hi"] = stationary_bootstrap_sharpe_ci(x, n_boot=1000)
                rows.append(row)
    # benchmark: buy & hold the same names with the same weights, close to close
    w = weights(P, select(P, CFG["final"]["lookback_months"], CFG["final"]["top_k"]))
    bh = (w.shift(1) * P["cc"][w.columns].fillna(0)).sum(axis=1)
    for nm in PERIODS:
        rows.append({"strategy": "buy_hold_same_names", "costs": "none", "period": nm,
                     **stats_row(period(bh, nm))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "headline.csv", index=False)

    first = min(c.net.ne(0).idxmax() for c in curves.values())
    fig, ax = plt.subplots(figsize=(9, 4))
    shade(ax)
    ends = []
    for s, r in curves.items():
        eq = np.exp(np.log1p(r.net.loc[first:]).cumsum())
        ax.plot(eq.index, eq, color=COLOR[s], label=LABEL[s])
        ends.append((LABEL[s], eq.iloc[-1], eq.index[-1]))
    end_labels(ax, ends)
    eqb = np.exp(np.log1p(bh.loc[first:]).cumsum())
    ax.plot(eqb.index, eqb, color=GREY, ls=":", label="buy & hold same names")
    ax.set_yscale("log")
    ax.set_ylabel("growth of $1, net (log)")
    ax.legend(loc="upper left")
    ax.set_title("frozen strategies, net of auction costs. grey = pre-sample (never looked at), "
                 "blue = out-of-sample (red line)")
    save(fig, "03_equity_curves.png")

    fig, ax = plt.subplots(figsize=(9, 3.2))
    for s in ["upday_LS", "upday_ON"]:
        rs = curves[s].net.loc[first:].rolling(252).apply(lambda x: x.mean() / x.std() * np.sqrt(252))
        ax.plot(rs.index, rs, color=COLOR[s], label=LABEL[s])
    shade(ax)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_title("rolling 1-year net Sharpe")
    ax.legend()
    save(fig, "11_rolling_sharpe.png")

    yr = pd.DataFrame({LABEL[s]: curves[s].net.loc[first:].groupby(lambda d: d.year).sum()
                       for s in ["upday_LS", "upday_ON"]})
    yr["buy & hold same names"] = bh.loc[first:].groupby(lambda d: d.year).sum()
    yr.to_csv(TAB / "pnl_by_year.csv")
    fig, ax = plt.subplots(figsize=(9, 3.3))
    x = np.arange(len(yr))
    for i, (c, col) in enumerate(zip(yr.columns, [C4, C2, GREY])):
        ax.bar(x + (i - 1) * 0.27, yr[c] * 100, width=0.25, color=col, label=c)
    ax.set_xticks(x, yr.index)
    ax.axhline(0, color="k", lw=0.6)
    ax.set_ylabel("sum of daily net returns (%)")
    ax.set_title("P&L by calendar year (net, auction costs)")
    ax.legend()
    save(fig, "06_pnl_by_year.png")
    return df, curves


def cost_sensitivity(P):
    rows = []
    w = weights(P, select(P, CFG["final"]["lookback_months"], CFG["final"]["top_k"]))
    tilt = up_day_tilt(P, w)
    for s in STRATS:
        spec = CFG["final"]["strategies"][s]
        g = backtest(P, w, spec["variant"], "zero", tilt=tilt if spec["up_day"] else None)
        sides = 2 * g.exposure + (2 * w.sum(axis=1) if spec["variant"] == "LS" else 0)
        for nm in ["discovery", "oos"]:
            gg, ss = period(g.gross, nm), period(sides, nm)
            be = gg.sum() / ss.sum() * 1e4
            for c in np.arange(0, 15.5, 0.5):
                rows.append({"strategy": s, "period": nm, "cost_bps_side": c,
                             "sharpe": sharpe(gg - ss * c / 1e4), "breakeven_bps_side": be})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "cost_sensitivity.csv", index=False)
    fig, axs = plt.subplots(1, 2, figsize=(9, 3.3), sharey=True)
    for ax, nm in zip(axs, ["discovery", "oos"]):
        for s in STRATS:
            d = df[(df.strategy == s) & (df.period == nm)]
            ax.plot(d.cost_bps_side, d.sharpe, color=COLOR[s], label=LABEL[s])
        ax.axvline(1.5, color="k", ls="--", lw=0.8)
        ax.text(1.7, ax.get_ylim()[1] * 0.92 if ax.get_ylim()[1] > 0 else 0, "auction\n(1.5bp)", fontsize=7)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlabel("all-in cost per side (bps)")
        ax.set_title(nm)
    axs[0].set_ylabel("net Sharpe")
    axs[0].legend()
    fig.suptitle("cost sensitivity: this is an execution strategy")
    save(fig, "05_cost_sensitivity.png")
    return df


def selection_map(P):
    m = select(P, CFG["final"]["lookback_months"], CFG["final"]["top_k"])
    mm = m.resample("ME").last()
    mm = mm.loc[:, mm.sum() > 0]
    mm = mm[mm.sum(axis=1) > 0]
    mm = mm[mm.sum().sort_values(ascending=False).index]
    share = (mm.sum() / mm.sum().sum()).rename("share_of_slots")
    share.to_csv(TAB / "selection_share.csv")
    fig, ax = plt.subplots(figsize=(9, 4))
    ax.imshow(mm.T.values, aspect="auto", cmap=LinearSegmentedColormap.from_list("s", ["#f4f3f0", C1]),
              interpolation="nearest")
    ax.grid(False)
    ax.set_yticks(range(mm.shape[1]), mm.columns)
    yrs = [i for i, d in enumerate(mm.index) if d.month == 1]
    ax.set_xticks(yrs, [mm.index[i].year for i in yrs])
    ax.set_title("which ETFs the walk-forward rule held each month (no hindsight picks)")
    save(fig, "08_selection_map.png")


LIQUID_ADV = 2e7   # post-hoc capacity variant, reported as such


def capacity(P, curves):
    c = CFG["costs"]
    rows = []
    for s, min_adv in [("core_ON", None), ("upday_ON", None), ("upday_LS", None), ("upday_LS", LIQUID_ADV)]:
        w = weights(P, select(P, CFG["final"]["lookback_months"], CFG["final"]["top_k"], min_adv=min_adv))
        sig = P["cc"].rolling(63, min_periods=20).std().shift(1)[w.columns]
        auction_vol = (P["dollar_vol"].rolling(63, min_periods=20).median().shift(1)
                       * c["auction_share_of_adv"] / 2)[w.columns]
        spec = CFG["final"]["strategies"][s]
        tilt = up_day_tilt(P, w) if spec["up_day"] else 1.0
        w_on = w * tilt
        base = curves[s] if min_adv is None else final_strategy(P, s, min_adv=min_adv)
        label = s if min_adv is None else f"{s}_adv20m"
        for aum in [1e4, 1e5, 3e5, 1e6, 3e6, 1e7, 3e7]:
            q = (w_on * aum)
            part = q / auction_vol
            imp = c["impact_coefficient"] * sig * np.sqrt(part.clip(lower=0)) * 1e4  # bps per side
            extra = 2 * (w_on * imp.fillna(0)).sum(axis=1) / 1e4
            if spec["variant"] == "LS":
                imp_id = c["impact_coefficient"] * sig * np.sqrt((w * aum / auction_vol).clip(lower=0)) * 1e4
                extra = extra + 2 * (w * imp_id.fillna(0)).sum(axis=1) / 1e4
            net = base.net - extra
            r = period(net, "oos")
            rows.append({"strategy": label, "aum": aum, "oos_sharpe": sharpe(r), "oos_ann": r.mean() * 252,
                         "max_auction_participation_p95": float(period(part.max(axis=1), "oos").quantile(0.95))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "capacity.csv", index=False)
    fig, ax = plt.subplots(figsize=(6.5, 3.3))
    styles = {"core_ON": (C1, "-"), "upday_ON": (C2, "-"), "upday_LS": (C4, "-"), "upday_LS_adv20m": (C4, "--")}
    for s, (col, ls) in styles.items():
        d = df[(df.strategy == s) & (df.aum <= 3e6)]
        ax.plot(d.aum, d.oos_sharpe, marker="o", ms=4, color=col, ls=ls,
                label=LABEL.get(s, "up-day LS, ADV ≥ $20M"))
    ax.set_xscale("log")
    ax.set_ylim(-3, 3)
    ax.xaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(
        lambda v, _: f"${v/1e6:g}M" if v >= 1e6 else f"${v/1e3:g}k"))
    ax.axhline(0, color="k", lw=0.6)
    ax.set_xlabel("capital (USD, log)")
    ax.set_ylabel("OOS net Sharpe")
    ax.set_title("capacity: sqrt-impact against measured auction volume (~1.1% of ADV per auction)")
    ax.legend()
    save(fig, "09_capacity.png")
    return df


def robustness(P, curves):
    rows = []

    def add(name, r):
        for nm in PERIODS:
            rows.append({"test": name, "period": nm, "sharpe": sharpe(period(r, nm))})

    uni = tradeable_universe()
    for s in ["upday_LS", "core_LS", "core_ON", "upday_ON"]:
        add(f"{s} | as frozen", curves[s].net)
        add(f"{s} | ADV >= $20M (post-hoc)", final_strategy(P, s, min_adv=LIQUID_ADV).net)
        add(f"{s} | no uranium (URA/URNM/NLR)", final_strategy(
            P, s, universe=[t for t in uni if t not in ("URA", "URNM", "NLR")]).net)
        add(f"{s} | futures/physical ETFs only", final_strategy(
            P, s, universe=CFG["universe"]["physical_or_futures"]).net)
        add(f"{s} | miners/equity ETFs only", final_strategy(
            P, s, universe=CFG["universe"]["equities_miners_producers"]).net)
        r = curves[s].net.copy()
        for nm in PERIODS:
            x = period(r, nm)
            rows.append({"test": f"{s} | best 10 days removed", "period": nm,
                         "sharpe": sharpe(x.drop(x.nlargest(10).index))})
        add(f"{s} | crossing the spread", final_strategy(P, s, "spread").net)
    df = pd.DataFrame(rows).pivot(index="test", columns="period", values="sharpe")[PERIODS]
    df.to_csv(TAB / "robustness.csv")
    print(df.round(2).to_string())
    return df


def exit_timing(P):
    """Gross bps/night by exit time. Hourly Yahoo (Nov-2023 on) for the niche names;
    optional KIBOT 5-min (2016-23) for the futures ETFs."""
    rows = []
    niche = ["URNM", "URA", "COPX", "SIL", "REMX", "GDXJ", "SILJ"]
    liquid = ["GLD", "SLV", "USO", "SPY"]
    for t in niche + liquid:
        try:
            h = load_hourly(t)
        except FileNotFoundError:
            continue
        h = h[(h.index.time >= pd.Timestamp("09:30").time()) & (h.index.time < pd.Timestamp("16:00").time())]
        day = h.index.normalize()
        g = h.groupby(day)
        close = g["Close"].last()
        prev = close.shift()
        o = g["Open"].first()
        hrs = {"09:30 open": o}
        for k, lab in [(0, "10:30"), (1, "11:30"), (2, "12:30")]:
            hrs[lab] = g["Close"].apply(lambda x, k=k: x.iloc[k] if len(x) > k else np.nan)
        hrs["16:00 close"] = close
        for lab, px in hrs.items():
            r = (px / prev - 1).dropna()
            r = r[r.abs() < CFG["data"]["max_abs_overnight"]]
            rows.append({"source": "yahoo 1h 2023-11..2026-10", "ticker": t,
                         "group": "niche miners" if t in niche else "liquid", "exit": lab,
                         "bps_per_night": r.mean() * 1e4})
    kdir = os.environ.get("KIBOT_DIR")
    if kdir and Path(kdir).exists():
        for t in ["GLD", "SLV", "USO", "BNO", "PALL", "PPLT", "CPER", "SPY"]:
            k = pd.read_csv(Path(kdir) / f"{t}.txt", skiprows=1, header=None,
                            names=["d", "t", "o", "h", "l", "c", "v"])
            k.index = pd.to_datetime(k.d + " " + k.t, format="%m/%d/%Y %H:%M")
            day = k.index.normalize()
            close = k.c.groupby(day).last()
            prev = close.shift()
            o = k[k.t == "09:30"].o
            o.index = o.index.normalize()
            pts = {"09:30 open": o}
            for lab in ["09:35", "09:45", "10:00", "10:30"]:
                bar = (pd.Timestamp(lab) - pd.Timedelta(minutes=5)).strftime("%H:%M")
                x = k[k.t == bar].c
                x.index = x.index.normalize()
                pts[lab] = x
            pts["16:00 close"] = close
            for lab, px in pts.items():
                r = (px / prev.reindex(px.index) - 1).dropna()
                rows.append({"source": "kibot 5m 2016-2023", "ticker": t,
                             "group": "futures ETFs", "exit": lab, "bps_per_night": r.mean() * 1e4})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "exit_timing.csv", index=False)
    srcs = df.source.unique()
    fig, axs = plt.subplots(1, len(srcs), figsize=(4.6 * len(srcs), 3.3), squeeze=False)
    for ax, src in zip(axs[0], srcs):
        d = df[df.source == src]
        order = list(dict.fromkeys(d.exit))
        for grp, col in zip(d.group.unique(), [C1, C2, C3]):
            m = d[d.group == grp].groupby("exit").bps_per_night.mean().reindex(order)
            ax.plot(range(len(order)), m.values, marker="o", ms=4, color=col, label=grp)
        ax.set_xticks(range(len(order)), order, rotation=30)
        ax.axhline(0, color="k", lw=0.6)
        ax.set_ylabel("avg gross return from prior close (bps)")
        ax.set_title(src)
        ax.legend()
    fig.suptitle("bought at the close: how much is left if you sell later than the open?")
    save(fig, "07_exit_timing.png")
    return df


def main():
    P = load_panel()
    ticker_split(P)
    g = grid(P)
    print(g[(g.lookback_m == 24) & (g.top_k == 5)].to_string())
    h, curves = headline(P)
    print(h[h.costs == "auction"].round(3).to_string())
    print(h[h.costs != "auction"][["strategy", "costs", "period", "sharpe", "cagr"]].round(2).to_string())
    cost_sensitivity(P)
    selection_map(P)
    print(capacity(P, curves).round(3).to_string())
    robustness(P, curves)
    print(exit_timing(P).groupby(["source", "group", "exit"], sort=False).bps_per_night.mean().round(1))


if __name__ == "__main__":
    main()
