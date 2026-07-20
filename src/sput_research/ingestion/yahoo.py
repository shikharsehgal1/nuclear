"""Yahoo Finance daily-bar ingestion with raw snapshots and retrieval metadata.

Bars are unadjusted (auto_adjust=False); `adj_close` retained for corporate-action
verification. Daily closes are stamped available at the exchange close of that day,
so the first tradeable bar for a close-derived signal is the NEXT session's open.
"""

from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import pandas as pd
import yfinance as yf

from sput_research.paths import RAW

YAHOO_RAW = RAW / "yahoo"

COLMAP = {
    "Open": "open", "High": "high", "Low": "low", "Close": "close",
    "Adj Close": "adj_close", "Volume": "volume",
    "Dividends": "dividends", "Stock Splits": "splits", "Capital Gains": "capital_gains",
}


def fetch_ticker(symbol: str, retries: int = 3) -> pd.DataFrame | None:
    last_err: Exception | None = None
    for attempt in range(retries):
        try:
            hist = yf.Ticker(symbol).history(period="max", auto_adjust=False, actions=True)
            if hist is not None and len(hist) > 0:
                return hist
            last_err = RuntimeError("empty frame")
        except Exception as e:  # noqa: BLE001 - vendor client raises many types
            last_err = e
        time.sleep(2.0 * (attempt + 1))
    print(f"  FAILED {symbol}: {last_err}")
    return None


def normalize(hist: pd.DataFrame, symbol: str, meta: dict) -> pd.DataFrame:
    df = hist.rename(columns=COLMAP)
    df = df[[c for c in COLMAP.values() if c in df.columns]].copy()
    # Yahoo daily index is tz-aware at exchange tz, stamped at session start (00:00 local).
    idx = pd.DatetimeIndex(df.index)
    df.insert(0, "date", idx.tz_localize(None).normalize())
    df.insert(1, "instrument", symbol)
    df["exchange_tz"] = str(idx.tz) if idx.tz is not None else "UNKNOWN"
    df["currency"] = meta.get("currency", "UNKNOWN")
    df = df.reset_index(drop=True)
    return df


def ingest_universe(tickers: dict[str, dict], force: bool = False) -> dict[str, str]:
    YAHOO_RAW.mkdir(parents=True, exist_ok=True)
    status: dict[str, str] = {}
    for symbol, meta in tickers.items():
        safe = symbol.replace("^", "_").replace("=", "_").replace("/", "_")
        out = YAHOO_RAW / f"{safe}.parquet"
        if out.exists() and not force:
            status[symbol] = "cached"
            continue
        hist = fetch_ticker(symbol)
        if hist is None:
            status[symbol] = "failed" if meta.get("required") else "failed_optional"
            continue
        df = normalize(hist, symbol, meta)
        df.to_parquet(out, index=False)
        (YAHOO_RAW / f"{safe}.meta.json").write_text(json.dumps({
            "symbol": symbol,
            "source": "yahoo_finance_v8_via_yfinance",
            "retrieved_at": datetime.now(UTC).isoformat(),
            "rows": len(df),
            "first_date": str(df["date"].min().date()),
            "last_date": str(df["date"].max().date()),
            "adjustment": "unadjusted_with_adj_close",
            "declared_currency": meta.get("currency"),
            "exchange": meta.get("exchange"),
            "licensing": "Yahoo ToS: personal/research use, no redistribution",
        }, indent=2))
        status[symbol] = f"ok:{len(df)}"
        time.sleep(1.0)
    return status
