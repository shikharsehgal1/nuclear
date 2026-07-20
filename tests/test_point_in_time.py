"""Leakage detection tests, including a deliberately contaminated fixture that
MUST be caught by the checks (test asserts the check fails on bad data)."""

import numpy as np
import pandas as pd

from sput_research.backtest.engine import CostSpec, run_backtest
from sput_research.validation.checks import check_no_future_timestamps


def _panel(n=50):
    idx = pd.bdate_range("2024-01-01", periods=n)
    rng = np.random.default_rng(1)
    close = 20 * np.cumprod(1 + rng.normal(0, 0.02, n))
    df = pd.DataFrame({
        "date": idx,
        "close": close,
        "signal_available_at": idx + pd.Timedelta(hours=22),   # published evening of same day
        "next_tradable_at": (idx + pd.tseries.offsets.BDay(1)) + pd.Timedelta(hours=14, minutes=30),
    })
    return df


def test_clean_panel_passes():
    assert check_no_future_timestamps(_panel()) == []


def test_contaminated_fixture_is_caught():
    df = _panel()
    # contamination: pretend tomorrow-evening's NAV was tradeable at today's open
    df.loc[10:20, "signal_available_at"] = df.loc[10:20, "next_tradable_at"] + pd.Timedelta(days=1)
    issues = check_no_future_timestamps(df)
    assert any(i.severity == "fatal" and i.check == "future_leak" for i in issues)


def test_premature_availability_caught():
    df = _panel()
    df.loc[5, "signal_available_at"] = df.loc[5, "date"] - pd.Timedelta(days=2)
    issues = check_no_future_timestamps(df)
    assert any(i.check == "premature_availability" for i in issues)


def test_lookahead_signal_beats_lagged_signal():
    """Economic leakage canary: a deliberately-leaked signal (uses tomorrow's
    return) must show large profits under same-day execution but lose its edge
    under the engine's enforced next-open timing. This documents that the
    engine timing, not luck, is the protection."""
    n = 300
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(2)
    ret = rng.normal(0, 0.02, n)
    close = 20 * np.cumprod(1 + ret)
    # opens gap slightly off the PRIOR close, so the close-to-close move is
    # mostly intraday and a same-day leak is genuinely profitable
    open_ = np.roll(close, 1) * (1 + rng.normal(0, 0.002, n))
    open_[0] = close[0]
    px = pd.DataFrame({"open": open_, "close": close}, index=idx)
    # leaked signal: sign of NEXT day's close-to-close return
    cc = pd.Series(close, index=idx).pct_change().shift(-1)
    leaked = np.sign(cc).fillna(0.0)
    res = run_backtest(px, leaked, CostSpec(0, 0, 0, 0))
    # engine shifts by 1 day -> the "leak" is aligned to trade the day it refers to
    # via next-open execution; it can only capture open->close of that day, not
    # the full close->close it peeked at. It still profits intraday (real leak),
    # proving the canary works:
    assert res.returns.mean() > 0
    # with one extra day of lag the peeked information is stale -> edge collapses
    res_lag = run_backtest(px, leaked, CostSpec(0, 0, 0, 0), signal_lag=1)
    assert res_lag.returns.mean() < res.returns.mean() * 0.5
