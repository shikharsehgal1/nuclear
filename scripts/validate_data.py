"""Run data-quality checks over every raw Yahoo series and (if present) the
Sprott fund-data series. Fatal issues exit nonzero."""

import json

import pandas as pd

from sput_research.paths import RAW
from sput_research.validation import checks


def main() -> int:
    fatal = 0
    for pq in sorted((RAW / "yahoo").glob("*.parquet")):
        df = pd.read_parquet(pq)
        issues = checks.run_price_checks(pq.stem, df)
        for i in issues:
            print(f"[{i.severity:5}] {i.check}: {i.detail}")
            fatal += i.severity == "fatal"

    sprott_pq = RAW / "sprott" / "fund_data.parquet"
    if sprott_pq.exists():
        s = pd.read_parquet(sprott_pq)
        issues = checks.check_duplicates(s, ["date"])
        if "u3o8_lbs" in s:
            issues += checks.check_holdings_monotonic(s.set_index("date")["u3o8_lbs"])
        if {"total_nav_usd", "nav_usd", "units_outstanding"} <= set(s.columns):
            sub = s.rename(columns={"total_nav_usd": "total_nav", "nav_usd": "published_nav"})
            issues += checks.check_nav_arithmetic(sub)
        for i in issues:
            print(f"[{i.severity:5}] sprott:{i.check}: {i.detail}")
            fatal += i.severity == "fatal"
    else:
        print("[warn ] sprott fund_data.parquet not present yet")

    print(json.dumps({"fatal_issues": fatal}))
    return 1 if fatal else 0


if __name__ == "__main__":
    raise SystemExit(main())
