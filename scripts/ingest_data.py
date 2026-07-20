"""Ingest all configured raw data. Usage: uv run python scripts/ingest_data.py [--force]"""

import sys

import yaml

from sput_research.ingestion.sprott import write_fund_data
from sput_research.ingestion.uranium_spot import write_cameco, write_numerco
from sput_research.ingestion.yahoo import ingest_universe
from sput_research.paths import CONFIG, RAW


def main() -> int:
    force = "--force" in sys.argv
    cfg = yaml.safe_load((CONFIG / "data_sources.yaml").read_text())
    tickers = cfg["yahoo_equities"]["tickers"]
    print(f"Ingesting {len(tickers)} Yahoo tickers (force={force})")
    status = ingest_universe(tickers, force=force)
    for sym, st in sorted(status.items()):
        print(f"  {sym:<12} {st}")

    if (RAW / "discovery").exists():
        sp = write_fund_data()
        print(f"sprott fund_data: {len(sp)} rows {sp['date'].min().date()}->{sp['date'].max().date()}")
        nm = write_numerco()
        print(f"numerco spot: {len(nm)} rows {nm['date'].min().date()}->{nm['date'].max().date()}")
        cc = write_cameco()
        print(f"cameco monthly: {len(cc)} rows")
    else:
        print("WARNING: data/raw/discovery missing - Sprott/Numerco/Cameco parsers skipped")
    hard_failures = [s for s, st in status.items() if st == "failed"]
    if hard_failures:
        print(f"REQUIRED tickers failed: {hard_failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
