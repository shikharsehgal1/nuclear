"""Ingest all configured raw data. Usage: uv run python scripts/ingest_data.py [--force]"""

import sys

import yaml

from sput_research.ingestion.yahoo import ingest_universe
from sput_research.paths import CONFIG


def main() -> int:
    force = "--force" in sys.argv
    cfg = yaml.safe_load((CONFIG / "data_sources.yaml").read_text())
    tickers = cfg["yahoo_equities"]["tickers"]
    print(f"Ingesting {len(tickers)} Yahoo tickers (force={force})")
    status = ingest_universe(tickers, force=force)
    for sym, st in sorted(status.items()):
        print(f"  {sym:<12} {st}")
    hard_failures = [s for s, st in status.items() if st == "failed"]
    if hard_failures:
        print(f"REQUIRED tickers failed: {hard_failures}")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
