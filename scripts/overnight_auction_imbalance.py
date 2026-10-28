"""Auction theory check: NYSE Arca order-imbalance feed (free TAQ samples, 2026-07-01/02).

Arca's opening/closing auctions are uniform-price call auctions: every order crosses at one
price, the one that maximizes matched volume. Before each auction Arca publishes the paired
quantity, the unmatched (imbalance) quantity and its side, and an indicative match price.
In a call auction the price concession is set by the unmatched side (Kyle/Madhavan): who
has to be absorbed pays, who absorbs them gets paid. Three questions:

1. Which side is unmatched? If closes skew to SELL imbalance and opens to BUY, the
   overnight drift is (partly) the price of absorbing that flow, and a MOC buy / MOO sell
   is on the paid side.
2. How big is the concession? Final auction price vs the feed's last reference price,
   signed so + = price moved toward the imbalance side.
3. Calibrate the impact model: fit concession = k * sigma_daily * sqrt(imbalance $ / auction $)
   (same form as the backtest's sqrt impact, which assumes k = 0.1, uncalibrated).

Pillar imbalance message (type 105) fields: seq, time, symbol, symseq, ref price, paired qty,
total imbalance qty, market imbalance qty, auction time, auction type (M = open, C = close),
side (B/S), continuous-book clearing px, auction-interest clearing px, SSR px, indicative
match px, upper/lower collar (x1e6), ... Raw files cached under data/raw/overnight/nyse/.
"""

from __future__ import annotations

import gzip
import urllib.request

import numpy as np
import pandas as pd

from overnight_auction_ticks import DAYS, NYSE_DIR, fetch_trades
from overnight_research import TAB
from sput_research.overnight.data import CFG, all_tickers, load_daily

BASE = "https://ftp.nyse.com/Historical%20Data%20Samples/TAQ%20NYSE%20ARCA%20ORDER%20IMBALANCES"
COLS = ["msg", "seq", "time", "symbol", "symseq", "ref", "paired", "imb", "mkt_imb", "auc_time", "auc_type", "side",
        "cont_px", "auc_int_px", "ssr_px", "ind_px"]
HELD = ["URNM", "URA", "SILJ", "COPX", "NLR", "REMX", "SIL", "GDXJ"]


def fetch_imbalances(day: str, syms: set[str]) -> pd.DataFrame:
    f = NYSE_DIR / f"arca_imb_{day}.csv"
    if not f.exists():
        gz = NYSE_DIR / f"arca_imb_{day}.gz"
        if not gz.exists():
            urllib.request.urlretrieve(f"{BASE}/EQY_US_ARCA_REF_IMBALANCES_{day}.gz", gz)
        keep = []
        with gzip.open(gz, "rt", encoding="latin-1") as fh:
            for line in fh:
                p = line.rstrip("\n").split(",")
                if p[0] == "105" and len(p) >= 16 and p[3] in syms and p[10] in ("M", "C"):
                    keep.append(",".join(p[:16]))
        f.write_text("\n".join(keep) + "\n")
    d = pd.read_csv(f, header=None, names=COLS, dtype={"side": str, "auc_type": str}, keep_default_na=False)
    d["side"] = d.side.str.strip()
    return d


def snapshots(day: str, syms: set[str]) -> pd.DataFrame:
    imb = fetch_imbalances(day, syms)
    tr = fetch_trades(day, syms)
    rows = []
    for (s, typ), g in imb.groupby(["symbol", "auc_type"]):
        cut = "09:30" if typ == "M" else "16:00"
        g = g[(g.time < cut) & (g.ref > 0)]
        if g.empty:
            continue
        last = g.iloc[-1]
        t = tr[tr.symbol == s]
        prints = t[t.c2.str.strip() == ("O" if typ == "M" else "6")]
        if prints.empty:
            continue
        px = prints.price.iloc[0] if typ == "M" else prints.price.iloc[-1]
        sh = prints.shares.sum()
        sgn = {"B": 1, "S": -1}.get(last.side, 0)
        rows.append({"day": day, "ticker": s, "auction": "open" if typ == "M" else "close",
                     "side": last.side or "none", "ref": last.ref, "auction_px": px,
                     "auction_usd": px * sh, "paired_usd": last.paired * last.ref, "imb_usd": last.imb * last.ref,
                     "imb_share": last.imb / max(last.imb + last.paired, 1),
                     "concession_bps": sgn * (px / last.ref - 1) * 1e4,
                     "move_bps": (px / last.ref - 1) * 1e4})
    return pd.DataFrame(rows)


def main():
    syms = set(all_tickers() + CFG["universe_extension"])
    df = pd.concat([snapshots(d, syms) for d in DAYS], ignore_index=True)
    sig = {}
    for (day, s) in df[["day", "ticker"]].drop_duplicates().itertuples(index=False):
        try:
            c = load_daily(s).AdjClose.pct_change()
            sig[(day, s)] = c.loc[: pd.Timestamp(day) - pd.Timedelta(days=1)].tail(63).std()
        except FileNotFoundError:
            sig[(day, s)] = np.nan
    df["sigma_bps"] = [sig[(d, s)] * 1e4 for d, s in zip(df.day, df.ticker)]
    df["x"] = df.sigma_bps * np.sqrt(df.imb_usd / df.auction_usd.where(df.auction_usd > 0))
    df.to_csv(TAB / "auction_imbalance.csv", index=False)

    # 1. side of the unmatched flow
    side = df[df.side.isin(["B", "S"])].pivot_table(index="auction", columns="side", values="ticker",
                                                    aggfunc="count", fill_value=0)
    side["sell_share"] = side.S / (side.B + side.S)
    print("unmatched side at the last pre-auction message:\n", side.to_string())

    # 2/3. concession and calibrated sqrt-impact coefficient
    ok = df[np.isfinite(df.x) & (df.x > 0) & df.side.isin(["B", "S"]) & (df.auction_usd > 5e3)]
    k = (ok.concession_bps * ok.x).sum() / (ok.x ** 2).sum()
    rows = []
    for nm, g in [("all", ok), ("open", ok[ok.auction == "open"]), ("close", ok[ok.auction == "close"]),
                  ("held names", ok[ok.ticker.isin(HELD)])]:
        rows.append({"sample": nm, "n": len(g), "median_imb_share": g.imb_share.median(),
                     "median_concession_bps": g.concession_bps.median(),
                     "mean_concession_bps": g.concession_bps.mean(),
                     "share_toward_imbalance": (g.concession_bps > 0).mean(),
                     "k_fit": (g.concession_bps * g.x).sum() / (g.x ** 2).sum(),
                     "corr": g.concession_bps.corr(g.x)})
    summ = pd.DataFrame(rows)
    summ.to_csv(TAB / "auction_imbalance_summary.csv", index=False)
    print("\nconcession (+ = price moved toward the imbalance side) and fitted k:\n", summ.round(3).to_string())
    print(f"\npooled k = {k:.3f} (backtest assumes {CFG['costs']['impact_coefficient']})")
    print("\nheld names:\n", df[df.ticker.isin(HELD)].sort_values(["ticker", "day", "auction"])[
        ["day", "ticker", "auction", "side", "imb_share", "paired_usd", "imb_usd", "auction_usd", "move_bps",
         "concession_bps"]].round(2).to_string())


if __name__ == "__main__":
    main()
