"""Risk stats and hedges for the trade as it would actually run.

#1 (up-day long overnight + 15/VIX) at $50k, fees + impact, ADV>=$20M, 15:30 signal where available.
Stats by period, and whether an overnight hedge (short SPY / GDX, beta-sized) helps.
Also #2 (LS) with vs without the long-SPY hedge at the same settings."""
import numpy as np
import pandas as pd

from overnight_audit import signal_1530, vix_scale
from overnight_postcost import leg_cost, run
from overnight_research import TAB, load_panel
from sput_research.overnight.data import CFG
from sput_research.overnight.strategy import members_from_scores, month_scores, up_day_tilt, weights

AUM, ADV = 50_000, 2e7
PER = {"2011-15": ("2011", "2015"), "2016-23": ("2016", "2023"), "2024-26": ("2024", "2026"), "full": ("2011", "2026")}

P = load_panel()  # module-level: built once, used by main()
vs = vix_scale(P["on"].index)
s = signal_1530(P)
sig = P["id"][s.columns].copy()
have = s.notna() & sig.notna()
sig[have] = s[have]

# rebuild #1 to get nightly gross exposure (same steps as run())
w = weights(P, members_from_scores(P, month_scores(P, CFG["final"]["lookback_months"], min_adv=ADV), CFG["final"]["top_k"]))
tilt = up_day_tilt(P, w, sig)
sc = vs.reindex(w.index).fillna(1.0)
on = P["on"][w.columns]
w_on = (w * tilt).mul(sc, axis=0).where(on.notna(), 0.0)
gross = w_on.sum(axis=1)
r1 = run(P, AUM, "upday_ON", vs, impact_on=True, min_adv=ADV, signal=sig)
assert np.allclose(r1, ((w_on * on.fillna(0)).sum(axis=1) - leg_cost(P, w_on, AUM)).loc[r1.index])
g = gross.reindex(r1.index)


def hedged(h, scale=1.0):
    """short beta*gross of h at the close, cover at the open; beta of the per-unit basket night, trailing 126d."""
    hon = P["on"][h].reindex(r1.index)
    unit = (r1 / g).where(g > 0)
    beta = unit.rolling(126, min_periods=60).cov(hon) / hon.rolling(126, min_periods=60).var()
    hw = (beta.shift(1).clip(0, 2).fillna(0) * g * scale).to_frame(h)
    cost = leg_cost(P, hw, AUM).reindex(r1.index).fillna(0)
    return r1 - hw[h] * hon.fillna(0) - cost, hw[h]


def stats(r):
    out = {}
    for nm, (a, b) in PER.items():
        x = r.loc[a:b]
        eq = (1 + x).cumprod()
        dd = eq / eq.cummax() - 1
        yrs = len(x) / 252
        cagr = eq.iloc[-1] ** (1 / yrs) - 1
        vol = x.std() * np.sqrt(252)
        down = x[x < 0].std() * np.sqrt(252)
        m = x.groupby(x.index.to_period("M")).apply(lambda v: (1 + v).prod() - 1)
        y = x.groupby(x.index.year).apply(lambda v: (1 + v).prod() - 1)
        spy = P["cc"]["SPY"].reindex(x.index)
        out[nm] = {"Sharpe": x.mean() / x.std() * np.sqrt(252), "Sortino": x.mean() * 252 / down,
                   "CAGR": cagr, "vol": vol, "max DD": dd.min(), "Calmar": cagr / -dd.min(),
                   "worst month": m.min(), "best month": m.max(), "months up": (m > 0).mean(),
                   "years up": f"{(y > 0).sum()}/{len(y)}", "beta SPY": x.cov(spy) / spy.var()}
    return pd.DataFrame(out)


def main():
    st = stats(r1)
    st.to_csv(TAB / "risk_50k.csv")
    print(st.to_string(float_format=lambda v: f"{v:.2f}"))
    print("nights invested:", f"{(g.loc['2011':] > 0).mean():.0%}")
    rows = [{"variant": "#1 unhedged", **stats(r1).loc["Sharpe"].to_dict(), "max_dd_full": stats(r1).at["max DD", "full"]}]
    for h in ["SPY", "GDX"]:
        for k in [0.5, 1.0]:
            rh, _ = hedged(h, k)
            st = stats(rh)
            rows.append({"variant": f"#1 + short {h} overnight, {k:g}x beta", **st.loc["Sharpe"].to_dict(),
                         "max_dd_full": st.at["max DD", "full"]})
    for hd in [False, True]:
        r2 = run(P, AUM, "upday_LS", vs, spy_beta_hedge=hd, impact_on=True, min_adv=ADV, signal=sig)
        st = stats(r2)
        rows.append({"variant": "#2 LS" + (" + long-SPY beta hedge" if hd else ", no hedge"),
                     **st.loc["Sharpe"].to_dict(), "max_dd_full": st.at["max DD", "full"]})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "hedges_50k.csv", index=False)
    print(df.round(2).to_string())


if __name__ == "__main__":
    main()
