"""Parse Numerco daily U3O8 indications and Cameco monthly assessed averages
from discovery captures into normalized parquet.

Numerco caveat (Tier 3): rows before 2018 were bulk-backloaded into their
database (createdAt 2018) — treat as historical reference, watch for
revisions; values are broker INDICATIONS, never executable fills.
Cameco caveat: republished UxC/TradeTech month-end averages; publication lag
~ first days of following month; we stamp availability month_end + 3bd.
"""

from __future__ import annotations

import json

import pandas as pd

from sput_research.paths import RAW

DISCOVERY = RAW / "discovery"


def write_numerco() -> pd.DataFrame:
    rows = []
    for f in sorted(DISCOVERY.glob("numerco_uhistory_skip*.json")):
        if f.name.endswith(".meta.json"):
            continue
        rows += json.loads(f.read_text())["results"]
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["Date"], format="%d-%b-%y")
    df = (df.rename(columns={"SpotPrice": "spot_usd", "ImpliedPrice": "implied_usd"})
            [["date", "spot_usd", "implied_usd"]]
            .dropna(subset=["date"]).drop_duplicates("date").sort_values("date").reset_index(drop=True))
    out = RAW / "numerco"
    out.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out / "spot.parquet", index=False)
    return df


def write_cameco() -> pd.DataFrame:
    d = json.loads((DISCOVERY / "cameco_monthly_uranium_prices.extracted.json").read_text())
    df = pd.DataFrame(d["rows"], columns=d["columns"])
    df["date"] = pd.to_datetime(df["month"])
    df = df.drop_duplicates("date").sort_values("date").reset_index(drop=True)
    df["available_at"] = df["date"] + pd.offsets.MonthEnd(0) + pd.offsets.BDay(3)
    out = RAW / "cameco"
    out.mkdir(parents=True, exist_ok=True)
    df[["date", "spot_usd_lb", "long_term_usd_lb", "available_at"]].to_parquet(
        out / "monthly.parquet", index=False)
    return df
