"""Post-freeze sensitivity of up-day LS: ranking lookback x top-K, ranking score,
random-selection Monte Carlo (does the ranking matter?), block-bootstrap Monte Carlo
(Sharpe / drawdown ranges), and volatility history + a vol-targeted variant.
Nothing here changes the frozen rule; it shows how much the result depends on it."""

from __future__ import annotations

import numpy as np
import pandas as pd

from overnight_research import C1, C2, C3, C4, DIVERGE, GREY, TAB, load_panel, plt, save, shade
from sput_research.overnight.data import CFG, load_vix
from sput_research.overnight.strategy import (
    backtest, members_from_scores, month_scores, period, up_day_tilt, weights,
)
from sput_research.statistics.metrics import max_drawdown, sharpe

PERIODS = ["presample", "discovery", "oos"]
LOOKBACKS = [1, 2, 3, 6, 9, 12, 18, 24, 36, 48]
TOPK = [1, 2, 3, 4, 5, 6, 8, 10, 15]
FROZEN = (CFG["final"]["lookback_months"], CFG["final"]["top_k"])
RNG = np.random.default_rng(11)


def upday_ls(P, member, scenario="auction"):
    w = weights(P, member)
    return backtest(P, w, "LS", scenario, tilt=up_day_tilt(P, w)).net


def trimmed(r):
    return r.loc[r.ne(0).idxmax():]


def per_period(r):
    r = trimmed(r)
    return {nm: sharpe(period(r, nm)) for nm in PERIODS}


def lookback_topk(P):
    rows = []
    for L in LOOKBACKS:
        sc = month_scores(P, L)
        for K in TOPK:
            rows.append({"lookback_m": L, "top_k": K, **per_period(upday_ls(P, members_from_scores(P, sc, K)))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "sens_lookback_topk.csv", index=False)
    fig, axs = plt.subplots(1, 3, figsize=(11, 4.2))
    for ax, nm in zip(axs, PERIODS):
        m = df.pivot(index="lookback_m", columns="top_k", values=nm)
        ax.imshow(m.values, cmap=DIVERGE, vmin=-2.5, vmax=2.5, aspect="auto")
        ax.grid(False)
        ax.set_xticks(range(len(TOPK)), TOPK)
        ax.set_yticks(range(len(LOOKBACKS)), LOOKBACKS)
        for (a, b), v in np.ndenumerate(m.values):
            ax.text(b, a, f"{v:.1f}", ha="center", va="center", fontsize=6.5,
                    weight="bold" if (m.index[a], m.columns[b]) == FROZEN else "normal")
        ax.set_xlabel("top K")
        ax.set_ylabel("ranking lookback (months)")
        ax.set_title(nm)
    fig.suptitle("up-day LS net Sharpe: ranking lookback × number of names (bold = frozen 24m / top 5)")
    save(fig, "12_lookback_topk.png")
    return df


def score_variants(P):
    rows = []
    for score in ["sharpe_ls", "mean_ls", "sharpe_on"]:
        for L in [3, 6, 12, 24, 36]:
            m = members_from_scores(P, month_scores(P, L, score), FROZEN[1])
            rows.append({"score": score, "lookback_m": L, **per_period(upday_ls(P, m))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "sens_score_variants.csv", index=False)
    lab = {"sharpe_ls": "Sharpe of (overnight − intraday)  [frozen]", "mean_ls": "mean of (overnight − intraday)",
           "sharpe_on": "Sharpe of overnight only"}
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2), sharey=True)
    for ax, nm in zip(axs, PERIODS):
        for score, col in zip(lab, [C1, C2, C3]):
            d = df[df.score == score]
            ax.plot(d.lookback_m, d[nm], marker="o", ms=4, color=col, label=lab[score])
        ax.axhline(0, color="k", lw=0.6)
        ax.set_xlabel("ranking lookback (months)")
        ax.set_title(nm)
    axs[0].set_ylabel("net Sharpe (top 5)")
    axs[0].legend(fontsize=7)
    fig.suptitle("ranking score variants")
    save(fig, "13_score_variants.png")
    return df


def random_selection_mc(P, actual, n=500):
    """Same up-day LS mechanics, but each month pick K names at random from the
    eligible (liquid, enough history) set. Answers: does the ranking add anything?"""
    sc = month_scores(P, FROZEN[0])
    elig = {m: s.index.to_numpy() for m, s in sc.items() if len(s)}
    rows = []
    for i in range(n):
        rand = {m: pd.Series(1.0, index=RNG.choice(e, size=min(FROZEN[1], len(e)), replace=False))
                for m, e in elig.items()}
        rows.append(per_period(upday_ls(P, members_from_scores(P, rand, FROZEN[1]))))
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "mc_random_selection.csv", index=False)
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2))
    summary = {}
    for ax, nm in zip(axs, PERIODS):
        ax.hist(df[nm], bins=30, color=GREY, alpha=0.8, label="random 5 names")
        ax.axvline(actual[nm], color=C4, lw=2, label="ranked top 5")
        pct = (df[nm] < actual[nm]).mean()
        summary[nm] = {"actual": actual[nm], "random_median": df[nm].median(), "pctile_of_actual": pct}
        ax.set_title(f"{nm}: ranked beats {pct:.0%} of random")
        ax.set_xlabel("net Sharpe")
    axs[0].legend(fontsize=7)
    fig.suptitle(f"Monte Carlo: {n} runs picking the 5 names at random each month (same up-day LS mechanics)")
    save(fig, "14_random_selection_mc.png")
    pd.DataFrame(summary).T.to_csv(TAB / "mc_random_selection_summary.csv")
    return summary


def bootstrap_mc(r, n=5000, block=20):
    """Stationary block bootstrap of daily net returns: 1-year and full-length paths."""
    x = trimmed(r).to_numpy()
    T = len(x)

    def path(length):
        idx = np.empty(length, dtype=np.int64)
        idx[0] = RNG.integers(T)
        restart = RNG.random(length) < 1 / block
        jumps = RNG.integers(T, size=length)
        for i in range(1, length):
            idx[i] = jumps[i] if restart[i] else (idx[i - 1] + 1) % T
        return x[idx]

    rows = []
    for horizon, length in [("1y", 252), ("full", T)]:
        for _ in range(n if horizon == "1y" else n // 5):
            p = path(length)
            eq = np.cumprod(1 + p)
            mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
            rows.append({"horizon": horizon, "sharpe": p.mean() / p.std() * np.sqrt(252),
                         "ret": eq[-1] ** (252 / length) - 1, "max_dd": mdd})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "mc_bootstrap_paths.csv", index=False)
    q = df.groupby("horizon").quantile([0.05, 0.5, 0.95]).unstack()
    one = df[df.horizon == "1y"]
    probs = {"p_losing_year": float((one.ret < 0).mean()), "p_1y_dd_worse_20": float((one.max_dd < -0.2).mean()),
             "p_1y_dd_worse_30": float((one.max_dd < -0.3).mean()),
             "p_full_dd_worse_40": float((df[df.horizon == "full"].max_dd < -0.4).mean())}
    q.to_csv(TAB / "mc_bootstrap_quantiles.csv")
    pd.Series(probs).to_csv(TAB / "mc_bootstrap_probs.csv")
    fig, axs = plt.subplots(1, 3, figsize=(11, 3.2))
    for ax, (col, lab) in zip(axs, [("sharpe", "Sharpe"), ("ret", "annual return"), ("max_dd", "max drawdown")]):
        v = one[col] * (100 if col != "sharpe" else 1)
        ax.hist(v, bins=50, color=C4, alpha=0.85)
        ax.axvline(np.median(v), color="k", lw=1)
        ax.set_title(f"1-year {lab}: 5–95% [{np.percentile(v, 5):.1f}, {np.percentile(v, 95):.1f}]")
        ax.set_xlabel(lab + (" (%)" if col != "sharpe" else ""))
    fig.suptitle(f"Monte Carlo: {n} one-year paths block-resampled from up-day LS daily returns (2011–2026)")
    save(fig, "15_bootstrap_mc.png")
    return q, probs


def vol_history(P, r):
    r = trimmed(r)
    vol = r.rolling(63).std() * np.sqrt(252)
    target = 0.20
    scale = (target / vol.shift(1)).clip(upper=1.0).fillna(1.0)   # de-risk only, never lever up
    rv = r * scale
    yearly = pd.DataFrame({"vol": r.groupby(r.index.year).std() * np.sqrt(252),
                           "vol_targeted": rv.groupby(rv.index.year).std() * np.sqrt(252)})
    yearly.to_csv(TAB / "vol_by_year.csv")
    rows = []
    for nm in PERIODS + ["full"]:
        for lab, x in [("as frozen", r), ("vol-target 20% (de-risk only)", rv)]:
            xx = x if nm == "full" else period(x, nm)
            rows.append({"variant": lab, "period": nm, "sharpe": sharpe(xx), "max_dd": max_drawdown(xx)[0],
                         "ann": xx.mean() * 252, "vol": xx.std() * np.sqrt(252)})
    vt = pd.DataFrame(rows)
    vt.to_csv(TAB / "vol_target.csv", index=False)
    fig, ax = plt.subplots(figsize=(9, 3.2))
    shade(ax)
    ax.plot(vol.index, vol * 100, color=C4, label="up-day LS, 63-day realised vol")
    v2 = rv.rolling(63).std() * np.sqrt(252)
    ax.plot(v2.index, v2 * 100, color=C1, lw=1, label="vol-targeted (20%, de-risk only)")
    ax.axhline(target * 100, color="k", ls=":", lw=0.8)
    ax.set_ylabel("annualised vol (%)")
    ax.set_title("volatility history")
    ax.legend(loc="upper left")
    save(fig, "16_vol_history.png")
    return yearly, vt


def blend(P):
    """Average the top-5 membership of several lookbacks instead of betting on one."""
    rows = []
    for lbs in [(24,), (6, 12, 24), (3, 12, 36), (6, 12, 18, 24)]:
        m = sum(members_from_scores(P, month_scores(P, L), FROZEN[1]) for L in lbs)
        m = m.fillna(0) / len(lbs)
        rows.append({"lookbacks": "+".join(map(str, lbs)), **per_period(upday_ls(P, m)),
                     "avg_names": float((m > 0).sum(axis=1)[m.sum(axis=1) > 0].mean())})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "sens_lookback_blend.csv", index=False)
    return df


def exposures_and_hedges(P):
    """How much market/sector beta is left, and does an explicit overnight hedge help?
    Hedge: short h * beta of SPY or GDX at the close, cover at the open (auction costs),
    beta = trailing 126d overnight-leg beta, lagged one day, clipped to [0, 2]."""
    member = members_from_scores(P, month_scores(P, FROZEN[0]), FROZEN[1])
    w = weights(P, member)
    tilt = up_day_tilt(P, w)
    ls = trimmed(backtest(P, w, "LS", "auction", tilt=tilt).net)
    on_leg = backtest(P, w, "ON", "auction", tilt=tilt).net.reindex(ls.index)
    cost = (CFG["costs"]["commission_bps"] + CFG["costs"]["auction_slippage_bps"]) / 1e4
    expo = []
    for h in ["SPY", "GDX"]:
        for nm in PERIODS:
            x, y = period(ls, nm), period(P["cc"][h].reindex(ls.index), nm)
            ok = x.notna() & y.notna()
            expo.append({"vs": f"{h} close-to-close", "period": nm, "corr": x[ok].corr(y[ok]),
                         "beta": np.cov(x[ok], y[ok])[0, 1] / y[ok].var()})
    pd.DataFrame(expo).to_csv(TAB / "hedge_exposure.csv", index=False)
    rows = [{"variant": "unhedged", **per_period(ls),
             "maxdd_full": max_drawdown(ls)[0], "corr_spy": ls.corr(P["cc"]["SPY"].reindex(ls.index))}]
    for h in ["SPY", "GDX"]:
        hon = P["on"][h].reindex(ls.index)
        beta = (on_leg.rolling(126, min_periods=60).cov(hon) / hon.rolling(126, min_periods=60).var())
        beta = beta.shift(1).clip(0, 2).fillna(0)
        hedged = ls - beta * hon.fillna(0) - 2 * beta * cost
        rows.append({"variant": f"overnight leg hedged with {h}", **per_period(hedged),
                     "maxdd_full": max_drawdown(hedged)[0],
                     "corr_spy": hedged.corr(P["cc"]["SPY"].reindex(ls.index)),
                     "avg_hedge_ratio": beta.mean()})
    for h in ["SPY", "GDX"]:
        hcc = P["cc"][h].reindex(ls.index)
        beta = (ls.rolling(126, min_periods=60).cov(hcc) / hcc.rolling(126, min_periods=60).var())
        hold = (-beta).shift(1).clip(0, 1).fillna(0)          # long |beta| when strategy beta < 0
        hedged = ls + hold * hcc.fillna(0) - hold.diff().abs().fillna(0) * cost
        rows.append({"variant": f"beta-neutral: hold long {h} (trailing beta)", **per_period(hedged),
                     "maxdd_full": max_drawdown(hedged)[0],
                     "corr_spy": hedged.corr(P["cc"]["SPY"].reindex(ls.index)),
                     "avg_hedge_ratio": hold.mean()})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "hedges.csv", index=False)
    return pd.DataFrame(expo), df


def universe_subsample_mc(P, n=300, keep=0.7):
    """Randomly drop 30% of the ETF universe, rerun the whole ranked strategy."""
    from sput_research.overnight.data import tradeable_universe
    uni = tradeable_universe()
    rows = []
    for _ in range(n):
        sub = list(RNG.choice(uni, size=int(keep * len(uni)), replace=False))
        m = members_from_scores(P, month_scores(P, FROZEN[0], universe=sub), FROZEN[1])
        rows.append({**per_period(upday_ls(P, m)), "has_uranium": any(t in sub for t in ("URA", "URNM"))})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "mc_universe_subsample.csv", index=False)
    return df


def random_windows(r, n=1000):
    """Sharpe / return of randomly placed 1y and 2y windows over 2011-2026."""
    r = trimmed(r)
    rows = []
    for yrs in (1, 2):
        L = 252 * yrs
        for s0 in RNG.integers(0, len(r) - L, size=n):
            x = r.iloc[s0:s0 + L]
            rows.append({"years": yrs, "sharpe": sharpe(x), "ret": (1 + x).prod() - 1,
                         "max_dd": max_drawdown(x)[0]})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "mc_random_windows.csv", index=False)
    return df


def randomized_fig(sub, win):
    fig, axs = plt.subplots(1, 4, figsize=(12, 3.2))
    for ax, nm in zip(axs[:3], PERIODS):
        ax.hist(sub[nm], bins=30, color=C4, alpha=0.85)
        ax.axvline(0, color="k", lw=0.6)
        ax.set_title(f"{nm}: {(sub[nm] > 0).mean():.0%} of runs > 0")
        ax.set_xlabel("net Sharpe")
    axs[0].set_ylabel("runs (random 70% of ETFs)")
    ax = axs[3]
    for yrs, col in [(1, C4), (2, C1)]:
        v = win[win.years == yrs].ret * 100
        ax.hist(v, bins=40, color=col, alpha=0.6, label=f"{yrs}y windows: {(v > 0).mean():.0%} positive")
    ax.axvline(0, color="k", lw=0.6)
    ax.set_xlabel("window return (%)")
    ax.legend(fontsize=7)
    ax.set_title("random start dates")
    fig.suptitle("randomized sampling: drop 30% of the universe at random (300 runs) · random 1y/2y windows (1000 each)")
    save(fig, "18_randomized_sampling.png")


def vix_sizing(r):
    """Scale the whole book by VIX. Night dated t starts at close t-1; its size uses the
    VIX close of t-2 (fully published before the t-1 MOC cutoff). Costs scale with size,
    so scaling daily net returns == scaling positions."""
    r = trimmed(r)
    vix = load_vix().reindex(r.index).ffill().shift(2)
    variants = {
        "as frozen (1x)": pd.Series(1.0, index=r.index),
        "15/VIX, max 1x": (15 / vix).clip(upper=1.0),
        "15/VIX, max 2x": (15 / vix).clip(upper=2.0),
        "half size when VIX > 25": pd.Series(np.where(vix > 25, 0.5, 1.0), index=r.index),
    }
    rows, curves = [], {}
    for lab, sc in variants.items():
        x = r * sc.fillna(1.0)
        curves[lab] = x
        for nm in PERIODS + ["full"]:
            xx = x if nm == "full" else period(x, nm)
            rows.append({"variant": lab, "period": nm, "sharpe": sharpe(xx), "max_dd": max_drawdown(xx)[0],
                         "ann": xx.mean() * 252, "vol": xx.std() * np.sqrt(252),
                         "avg_size": (sc if nm == "full" else period(sc, nm)).mean()})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "vix_sizing.csv", index=False)
    bucket = pd.cut(vix, [0, 15, 20, 25, 35, 100], labels=["<15", "15-20", "20-25", "25-35", ">35"])
    by = r.groupby(bucket, observed=True).agg(
        days="count", ann_return=lambda x: x.mean() * 252, ann_vol=lambda x: x.std() * np.sqrt(252),
        sharpe=lambda x: x.mean() / x.std() * np.sqrt(252))
    by.to_csv(TAB / "vix_buckets.csv")
    fig, axs = plt.subplots(1, 2, figsize=(11, 3.4), gridspec_kw={"width_ratios": [2.2, 1]})
    ax = axs[0]
    for lab, col in [("as frozen (1x)", C4), ("15/VIX, max 1x", C1)]:
        eq = (1 + curves[lab]).cumprod()
        ax.plot(eq.index, (eq / eq.cummax() - 1) * 100, color=col, lw=1, label=lab)
    shade(ax)
    ax.set_ylabel("drawdown (%)")
    ax.set_title("drawdowns under VIX sizing")
    ax.legend(fontsize=7, loc="lower left")
    ax = axs[1]
    ax.bar(range(len(by)), by.sharpe, color=C4, width=0.6)
    for i, (sr, n) in enumerate(zip(by.sharpe, by.days)):
        ax.text(i, sr + 0.05, f"{sr:.1f}\n{n}d", ha="center", fontsize=7, color="#52514e")
    ax.set_ylim(0, by.sharpe.max() * 1.2)
    ax.set_xticks(range(len(by)), by.index)
    ax.set_xlabel("VIX (2 days before)")
    ax.set_ylabel("net Sharpe")
    ax.set_title("up-day LS by VIX regime")
    save(fig, "17_vix_sizing.png")
    return df, by


def main():
    P = load_panel()
    print(lookback_topk(P).round(2).to_string())
    print(score_variants(P).round(2).to_string())
    print(blend(P).round(2).to_string())
    for d in exposures_and_hedges(P):
        print(d.round(3).to_string())
    sc = month_scores(P, FROZEN[0])
    r = upday_ls(P, members_from_scores(P, sc, FROZEN[1]))
    print(pd.DataFrame(random_selection_mc(P, per_period(r))).T.round(3))
    q, probs = bootstrap_mc(r)
    print(q.round(3).to_string())
    print(probs)
    sub, win = universe_subsample_mc(P), random_windows(r)
    randomized_fig(sub, win)
    print(sub.describe().round(2).to_string())
    print(win.groupby("years").agg(p_pos=("ret", lambda x: (x > 0).mean()), sr_p05=("sharpe", lambda x: x.quantile(.05)),
                                   sr_med=("sharpe", "median"), dd_p05=("max_dd", lambda x: x.quantile(.05))).round(3))
    yearly, vt = vol_history(P, r)
    print(yearly.round(3).T.to_string())
    print(vt.round(3).to_string())
    df, by = vix_sizing(r)
    print(df.round(3).to_string())
    print(by.round(2).to_string())


if __name__ == "__main__":
    import sys
    if "--hedge-only" in sys.argv:
        for d in exposures_and_hedges(load_panel()):
            print(d.round(3).to_string())
    elif "--blend-only" in sys.argv:
        print(blend(load_panel()).round(2).to_string())
    elif "--vix-only" in sys.argv:
        P = load_panel()
        r = upday_ls(P, members_from_scores(P, month_scores(P, FROZEN[0]), FROZEN[1]))
        df, by = vix_sizing(r)
        print(df.round(3).to_string())
        print(by.round(2).to_string())
    else:
        main()
