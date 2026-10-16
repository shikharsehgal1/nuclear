"""Real auction prints from NYSE's free TAQ sample files (NYSE Arca trades, 2026-07-01/02).

Arca is the listing exchange for these ETFs, so its opening/closing auction prints ARE the
official open/close. Pillar trade messages (type 220) carry condition codes:
  cond2 'O' = opening auction print, '6' = closing auction print,
  cond4 'Q' = official open marker,  'M' = official close marker.

Measures, per ETF/day: auction price vs Yahoo open/close, auction size in shares and $,
and auction share of consolidated daily volume (calibrates the impact model, which assumed
each auction = 4% of ADV). Raw filtered trades are cached under data/raw/overnight/nyse/.
"""

from __future__ import annotations

import gzip
import io
import urllib.request

import pandas as pd

from overnight_research import TAB
from sput_research.overnight.data import CFG, RAW_DIR, all_tickers, load_daily

BASE = "https://ftp.nyse.com/Historical%20Data%20Samples/TAQ%20NYSE%20ARCA%20TRADES"
DAYS = ["20260701", "20260702"]
NYSE_DIR = RAW_DIR / "nyse"
NYSE_DIR.mkdir(parents=True, exist_ok=True)
COLS = ["msg", "seq", "time", "symbol", "symseq", "trade_id", "price", "shares", "c1", "c2", "c3", "c4"]


def fetch_trades(day: str, syms: set[str]) -> pd.DataFrame:
    f = NYSE_DIR / f"arca_trades_{day}.csv"
    if not f.exists():
        keep = []
        for k in range(1, 15):
            with urllib.request.urlopen(f"{BASE}/EQY_US_TAQ_ARCA_TRADES_{k}_{day}.gz", timeout=600) as r:
                for line in io.TextIOWrapper(gzip.GzipFile(fileobj=r), encoding="latin-1"):
                    p = line.rstrip("\n").split(",")
                    if p[0] == "220" and len(p) >= 12 and p[3] in syms:
                        keep.append(",".join(p[:12]))
        f.write_text("\n".join(keep) + "\n")
    d = pd.read_csv(f, header=None, names=COLS, dtype={"c1": str, "c2": str, "c3": str, "c4": str},
                    keep_default_na=False)
    d["day"] = pd.Timestamp(day)
    return d


def main():
    syms = set(all_tickers() + CFG["universe_extension"])
    rows = []
    for day in DAYS:
        t = fetch_trades(day, syms)
        for s, g in t.groupby("symbol"):
            op, cl = g[g.c2.str.strip() == "O"], g[g.c2.str.strip() == "6"]
            if op.empty and cl.empty:
                continue
            try:
                y = load_daily(s).loc[pd.Timestamp(day)]
            except (FileNotFoundError, KeyError):
                continue
            rows.append({
                "day": day, "ticker": s,
                "open_auction_px": op.price.iloc[0] if len(op) else float("nan"),
                "open_auction_shares": op.shares.sum(),
                "close_auction_px": cl.price.iloc[-1] if len(cl) else float("nan"),
                "close_auction_shares": cl.shares.sum(),
                "yahoo_open": y.Open, "yahoo_close": y.Close, "consolidated_volume": y.Volume,
                "arca_volume": g.shares.sum(),
            })
    df = pd.DataFrame(rows)
    df["open_px_diff_bps"] = (df.open_auction_px / df.yahoo_open - 1) * 1e4
    df["close_px_diff_bps"] = (df.close_auction_px / df.yahoo_close - 1) * 1e4
    df["open_auction_share"] = df.open_auction_shares / df.consolidated_volume
    df["close_auction_share"] = df.close_auction_shares / df.consolidated_volume
    df["open_auction_usd_k"] = df.open_auction_shares * df.open_auction_px / 1e3
    df["close_auction_usd_k"] = df.close_auction_shares * df.close_auction_px / 1e3
    df.to_csv(TAB / "auction_ticks.csv", index=False)
    by = df.groupby("ticker")[["open_px_diff_bps", "close_px_diff_bps", "open_auction_share", "close_auction_share",
                               "open_auction_usd_k", "close_auction_usd_k"]].mean()
    by.to_csv(TAB / "auction_ticks_by_ticker.csv")
    print(by.round(3).to_string())
    print("\nmedian across ETFs:", by.median().round(4).to_dict())


if __name__ == "__main__":
    main()
