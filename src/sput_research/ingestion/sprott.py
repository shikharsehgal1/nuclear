"""Parse Sprott fund-page captures (data/raw/discovery/) into normalized
Sprott SPUT datasets. Provenance: the fund page server-renders full history as
inline Highcharts arrays; see docs/DATA_ENDPOINTS.md.

Outputs
-------
data/raw/sprott/fund_data.parquet: date, nav_usd, price_usd_published,
    premium_discount_published (fraction), u3o8_lbs (weekly, as-of stamps only
    on report dates), lbs_acquired, lbs_cumulative
data/raw/sprott/meta.json

Known gaps (do NOT interpolate): units_outstanding and total NAV history are
not published; CAD NAV history is not published.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pandas as pd

from sput_research.paths import RAW

DISCOVERY = RAW / "discovery"
OUT = RAW / "sprott"


def parse_fund_data() -> pd.DataFrame:
    src = DISCOVERY / "sprott_uranium_inline_series.extracted.json"
    d = json.loads(src.read_text())

    def series(key: str, col: str) -> pd.DataFrame:
        return pd.DataFrame(d[key], columns=["date", col]).assign(
            date=lambda x: pd.to_datetime(x["date"]))

    nav = series("Net Asset Value", "nav_usd")
    px = series("Share Price", "price_usd_published")
    prem = series("Premium/Discount to Net Asset Value", "premium_discount_published")
    prem["premium_discount_published"] /= 100.0
    lbs = series("Pounds of U3O8 held (millions, weekly)", "u3o8_lbs")
    lbs["u3o8_lbs"] *= 1e6

    acq = pd.DataFrame(d["Daily Pounds Acquired"],
                       columns=["date", "lbs_acquired", "lbs_cumulative"]).assign(
        date=lambda x: pd.to_datetime(x["date"]))

    df = nav.merge(px, on="date", how="outer").merge(prem, on="date", how="outer")
    df = df.merge(lbs, on="date", how="outer").merge(acq, on="date", how="outer")
    return df.sort_values("date").reset_index(drop=True)


def write_fund_data() -> pd.DataFrame:
    OUT.mkdir(parents=True, exist_ok=True)
    df = parse_fund_data()
    df.to_parquet(OUT / "fund_data.parquet", index=False)
    src_meta = json.loads((DISCOVERY / "sprott_uranium_inline_series.extracted.meta.json").read_text())
    (OUT / "meta.json").write_text(json.dumps({
        "parsed_at": datetime.now(UTC).isoformat(),
        "source_retrieval": src_meta,
        "rows": len(df),
        "first_date": str(df["date"].min().date()),
        "last_date": str(df["date"].max().date()),
        "currency": "USD",
        "nav_valuation_local": "16:00 America/Toronto (see MECHANICS.md)",
        "availability_policy": "published evening of valuation day; tradeable next open; +1d stress",
        "gaps": ["units_outstanding history not published", "CAD NAV history not published",
                 "holdings weekly only"],
    }, indent=2))
    return df
