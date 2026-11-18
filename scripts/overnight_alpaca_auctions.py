"""Official NYSE Arca opening/closing auction prints, 2016 onward, from Alpaca's consolidated tape (SIP).

Free Alpaca market-data plan: full SIP history since 2016 (only the last 15 minutes are off-limits).
On the tape the listing exchange's auction prints carry their own condition codes:
  exchange 'P' (NYSE Arca), condition 'O' = opening print, '6' = closing print
  ('Q' / 'M' are the official open / close markers that repeat the same print).
Pulls a few seconds around 09:30 and 16:00 ET for every ETF in the universe, every day, and keeps
the auction print (price, shares). Cached per year under data/raw/overnight/alpaca/ so it resumes.

Needs ALPACA_KEY / ALPACA_SECRET in the environment (nuclear/.env, gitignored).
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

import pandas as pd

from sput_research.overnight.data import RAW_DIR, load_daily, tradeable_universe

OUT = RAW_DIR / "alpaca"
OUT.mkdir(parents=True, exist_ok=True)
URL = "https://data.alpaca.markets/v2/stocks/trades"
WINDOWS = {"open": ("09:29:59", "09:30:10", "O"), "close": ("16:00:00", "16:00:10", "6")}


def _env():
    if "ALPACA_KEY" not in os.environ:
        f = RAW_DIR.parents[2] / ".env"
        for line in f.read_text().splitlines() if f.exists() else []:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    return {"APCA-API-KEY-ID": os.environ["ALPACA_KEY"], "APCA-API-SECRET-KEY": os.environ["ALPACA_SECRET"]}


def _get(params: dict, headers: dict) -> dict:
    url = URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(8):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=60) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            if e.code in (429, 500, 502, 503, 504):
                time.sleep(2 ** attempt)
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 ** attempt)
    raise RuntimeError(f"failed: {url}")


def auction_prints(day: pd.Timestamp, syms: list[str], headers: dict) -> list[dict]:
    rows = []
    for kind, (a, b, cond) in WINDOWS.items():
        start = pd.Timestamp(f"{day.date()} {a}", tz="America/New_York").isoformat()
        end = pd.Timestamp(f"{day.date()} {b}", tz="America/New_York").isoformat()
        q = {"symbols": ",".join(syms), "start": start, "end": end, "feed": "sip", "limit": 10000}
        while True:
            d = _get(q, headers)
            for s, trades in (d.get("trades") or {}).items():
                for t in trades:
                    if t["x"] == "P" and cond in t["c"]:
                        rows.append({"day": day, "ticker": s, "auction": kind, "time": t["t"], "price": t["p"],
                                     "shares": t["s"]})
            if not d.get("next_page_token"):
                break
            q["page_token"] = d["next_page_token"]
            time.sleep(0.31)
        time.sleep(0.31)  # free plan: 200 requests/minute
    return rows


def main(years: list[int] | None = None, start: str = "2016-01-01"):
    headers = _env()
    syms = tradeable_universe()
    days = load_daily("SPY").index
    days = days[days >= start]
    for yr in years or sorted(set(days.year)):
        f = OUT / f"auctions_{yr}.parquet"
        done = pd.read_parquet(f) if f.exists() else pd.DataFrame(columns=["day"])
        have = set(pd.to_datetime(done["day"]))
        todo = [d for d in days[days.year == yr] if d not in have]
        rows = []
        for i, d in enumerate(todo):
            rows += auction_prints(d, syms, headers) or [{"day": d, "ticker": None, "auction": None}]
            if rows and (i % 20 == 19 or i == len(todo) - 1):  # checkpoint
                done = pd.concat([done, pd.DataFrame(rows)], ignore_index=True)
                done.to_parquet(f)
                rows = []
                print(f"{yr}: {d.date()} ({i + 1}/{len(todo)})", flush=True)
    print("done")


if __name__ == "__main__":
    import sys

    main([int(y) for y in sys.argv[1:]] or None)  # e.g. 2016 2019 2023 2026; default all years
