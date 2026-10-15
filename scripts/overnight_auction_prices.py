"""Second source for the auction prints: Nasdaq.com official daily open/close vs Yahoo,
for the ETFs the strategy holds most. Saves raw Nasdaq bars (gitignored) and a match table."""

from __future__ import annotations

import json
import subprocess
import time

import numpy as np
import pandas as pd

from overnight_ingest import MINUTE
from overnight_research import TAB
from sput_research.overnight.data import RAW_DIR, load_daily


def fetch_nasdaq(t: str) -> pd.DataFrame:
    f = RAW_DIR / f"{t}_nasdaq.parquet"
    if f.exists():
        return pd.read_parquet(f)
    url = (f"https://api.nasdaq.com/api/quote/{t}/historical?assetclass=etf"
           "&fromdate=2014-01-01&todate=2026-10-14&limit=9999")
    out = subprocess.run(["curl", "-s", "-m", "60", "-A", "Mozilla/5.0", "-H", "Accept: application/json", url],
                         capture_output=True, text=True).stdout
    rows = json.loads(out)["data"]["tradesTable"]["rows"]

    def num(x):
        x = str(x).replace("$", "").replace(",", "")
        return float(x) if x not in ("N/A", "") else np.nan

    d = pd.DataFrame({"Open": [num(r["open"]) for r in rows], "Close": [num(r["close"]) for r in rows]},
                     index=pd.to_datetime([r["date"] for r in rows])).sort_index()
    d.to_parquet(f)
    time.sleep(1)
    return d


def main():
    rows = []
    for t in MINUTE:
        x = fetch_nasdaq(t).join(load_daily(t)[["Open", "Close"]], rsuffix="_yahoo", how="inner").dropna()
        for lab, a, b in [("2016-19", "2016", "2019"), ("2020-23", "2020", "2023"), ("2024-26", "2024", "2026")]:
            z = x.loc[a:b]
            if z.empty:
                continue
            do = (z.Open / z.Open_yahoo - 1).abs() * 1e4
            dc = (z.Close / z.Close_yahoo - 1).abs() * 1e4
            rows.append({"ticker": t, "period": lab, "days": len(z),
                         "open_identical_share": (do < 0.5).mean(), "open_p95_diff_bps": do.quantile(0.95),
                         "close_identical_share": (dc < 0.5).mean(), "close_p95_diff_bps": dc.quantile(0.95)})
    df = pd.DataFrame(rows)
    df.to_csv(TAB / "auction_price_check.csv", index=False)
    print(df.round(3).to_string())


if __name__ == "__main__":
    main()
