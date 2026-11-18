"""Are Yahoo's open/close the real auction prices? Rerun the trade on the official NYSE Arca prints.

Input: data/raw/overnight/alpaca/auctions_*.parquet (scripts/overnight_alpaca_auctions.py).
1. Signed gap, auction print vs Yahoo open/close, per ETF and per year, 2016 onward.
2. The same gap on the nights the trade actually holds (open = your MOO sell, close = your MOC buy),
   signed so negative = your fill is worse than the backtest assumed.
3. Rerun #1 (frozen ranking) and the overnight hit-rate ranking with Open/Close replaced by the
   auction prints wherever one exists (Yahoo elsewhere; share of held nights without a print reported).
"""

from __future__ import annotations

import json

import pandas as pd

import overnight_ranking as rk
from overnight_research import TAB
from sput_research.overnight.data import RAW_DIR, load_daily, split_returns, tradeable_universe
from sput_research.overnight.strategy import members_from_scores, up_day_tilt, weights

P, stats = rk.P, rk.stats


def splits(tickers) -> dict[str, pd.Series]:
    """Split ratios by date (Yahoo). The tape is in traded prices, Yahoo's bars are split-adjusted."""
    f = RAW_DIR / "alpaca" / "splits.json"
    if not f.exists():
        import yfinance as yf
        f.write_text(json.dumps({t: {str(d.date()): float(r) for d, r in yf.Ticker(t).splits.items()} for t in tickers}))
    return {t: pd.Series(v, dtype=float).rename(index=pd.Timestamp) for t, v in json.loads(f.read_text()).items()}


def prints() -> pd.DataFrame:
    a = pd.concat([pd.read_parquet(f) for f in sorted((RAW_DIR / "alpaca").glob("auctions_*.parquet"))])
    a = a.dropna(subset=["ticker"]).sort_values("time").drop_duplicates(["day", "ticker", "auction"])
    a["day"] = pd.to_datetime(a["day"])
    sp = splits(sorted(a.ticker.unique()))
    for t, s in sp.items():
        for d, r in s.items():  # prices before a split are divided by its ratio (reverse splits: ratio < 1)
            m = (a.ticker == t) & (a.day < d)
            a.loc[m, "price"] = a.loc[m, "price"] / r
    return a.pivot_table(index=["day", "ticker"], columns="auction", values="price").reset_index()


def main():
    a = prints()
    rows = []
    for t, g in a.groupby("ticker"):
        y = load_daily(t)[["Open", "Close", "Volume"]]
        g = g.set_index("day").join(y, how="inner")
        g["open_gap_bps"] = (g["open"] / g.Open - 1) * 1e4
        g["close_gap_bps"] = (g["close"] / g.Close - 1) * 1e4
        g["ticker"] = t
        rows.append(g.reset_index())
    g = pd.concat(rows)
    g.to_parquet(RAW_DIR / "alpaca" / "auction_vs_yahoo.parquet")

    def summ(x):
        out = {}
        for side in ["open", "close"]:
            v = x[f"{side}_gap_bps"].dropna()
            out |= {f"{side}_n": len(v), f"{side}_mean_bps": v.mean(), f"{side}_median_bps": v.median(),
                    f"{side}_abs_median_bps": v.abs().median(), f"{side}_exact_%": 100 * (v.abs() < 0.5).mean(),
                    f"{side}_over10bp_%": 100 * (v.abs() > 10).mean()}
        return out

    by_t = pd.DataFrame({t: summ(x) for t, x in g.groupby("ticker")}).T
    by_y = pd.DataFrame({y: summ(x) for y, x in g.groupby(g.day.dt.year)}).T
    by_t.to_csv(TAB / "auction_vs_yahoo_by_ticker.csv")
    by_y.to_csv(TAB / "auction_vs_yahoo_by_year.csv")
    pd.set_option("display.width", 250)
    print(by_y.round(1).to_string())
    print(by_t.round(1).sort_values("open_abs_median_bps", ascending=False).to_string())

    # 2 + 3: rerun on auction prints
    yahoo = {k: v.copy() for k, v in P.items()}
    per = {}
    for t in tradeable_universe():
        d = load_daily(t).copy()
        x = a[a.ticker == t].set_index("day")
        o, c = x["open"].reindex(d.index), x["close"].reindex(d.index) if "close" in x else None
        d["Open"] = o.fillna(d.Open)
        if c is not None:
            f = d.AdjClose / d.Close
            d["Close"] = c.fillna(d.Close)
            d["AdjClose"] = d.Close * f
        per[t] = (split_returns(d),)
    auc = {k: pd.DataFrame({t: per[t][0][k] for t in per}).reindex_like(yahoo[k][list(per)]) for k in ["on", "id", "cc", "price"]}

    years = sorted(g.day.dt.year.unique())
    res = []
    fixed = {(sc, aum): rk.book_weights(sc, 24, aum) for sc in ["gap_sharpe", "on_hit"] for aum in [25_000, 50_000]}
    for lab, src in [("yahoo", None), ("auction", auc)]:
        if src is not None:
            for k, v in src.items():
                P[k].loc[:, v.columns] = v
        for (sc, aum), w in fixed.items():
            for how, r in [("same picks", rk.book(sc, 24, aum, w_on=w)), ("re-ranked", rk.book(sc, 24, aum))]:
                if lab == "yahoo" and how == "re-ranked":
                    continue
                for yr in years:
                    x = r.loc[str(yr)]
                    res.append({"year": yr, "ranking": sc, "aum": aum, "prices": lab if lab == "yahoo" else f"auction, {how}",
                                "return": (1 + x).prod() - 1, "sharpe": x.mean() / x.std() * 252 ** 0.5})
    for k in yahoo:
        P[k] = yahoo[k]
    res = pd.DataFrame(res).pivot_table(index=["year", "ranking", "aum"], columns="prices", values=["return", "sharpe"])
    res.columns = [f"{a}: {b}" for a, b in res.columns]
    res.to_csv(TAB / "auction_rerun.csv")
    print("\nreturn and Sharpe by year: Yahoo prices vs NYSE Arca auction prints"
          "\n(same picks = only fills change; re-ranked = picks also recomputed from auction prices)\n",
          res.round(3).to_string())

    # gap on the nights the trade holds, signed so + = your fill beat the backtest price
    nxt = P["on"].index.to_series().shift(-1)
    closes = g[["day", "ticker", "close_gap_bps"]].assign(day=lambda x: x.day.map(nxt))  # MOC buy the evening before
    held = []
    for sc in ["gap_sharpe", "on_hit"]:
        ww = weights(P, members_from_scores(P, rk.scores(sc, 24, 50_000), rk.K))
        ww = ww * up_day_tilt(P, ww, rk.sig.reindex(columns=ww.columns))
        h = (ww > 0).loc["2016":].stack()
        z = h[h].reset_index().iloc[:, :2]
        z.columns = ["day", "ticker"]
        z = z[z.day.dt.year.isin(years)]
        z = z.merge(g[["day", "ticker", "open_gap_bps"]], on=["day", "ticker"], how="left")
        z = z.merge(closes, on=["day", "ticker"], how="left")
        z["sell_vs_yahoo"] = z.open_gap_bps     # MOO sell above Yahoo's open: better for you
        z["buy_vs_yahoo"] = -z.close_gap_bps    # MOC buy above Yahoo's close: worse for you
        for yr in years:
            q = z[z.day.dt.year == yr]
            held.append({"ranking": sc, "year": yr, "nights": len(q),
                         "no_open_print_%": 100 * q.sell_vs_yahoo.isna().mean(),
                         "sell_vs_yahoo_mean_bps": q.sell_vs_yahoo.mean(),
                         "buy_vs_yahoo_mean_bps": q.buy_vs_yahoo.mean(),
                         "round_trip_mean_bps": (q.sell_vs_yahoo + q.buy_vs_yahoo).mean()})
    held = pd.DataFrame(held)
    held.to_csv(TAB / "auction_vs_yahoo_held.csv", index=False)
    print("\n(+ = better than the backtest assumed)\n", held.round(2).to_string(index=False))


if __name__ == "__main__":
    main()
