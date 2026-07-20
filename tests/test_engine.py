import numpy as np
import pandas as pd
import pytest

from sput_research.backtest.engine import CostSpec, position_from_events, run_backtest

IDX = pd.bdate_range("2023-01-02", periods=10)


def make_prices(opens, closes):
    return pd.DataFrame({"open": opens, "close": closes}, index=IDX[: len(opens)])


def test_no_same_close_fill():
    """A signal on day t's close must not capture day t's close-to-close move."""
    opens = [100] * 10
    closes = [100, 100, 100, 110, 110, 110, 110, 110, 110, 110]
    px = make_prices(opens, closes)
    # signal fires at close of day 3 (the +10% day)
    sig = pd.Series(0.0, index=IDX)
    sig.iloc[3:] = 1.0
    res = run_backtest(px, sig, CostSpec(commission_bps=0, half_spread_bps=0, borrow_bps_annual=0))
    # day 3's +10% close move must NOT be captured
    assert res.gross_returns.iloc[3] == 0.0
    # day 4: overnight open(110? no, open=100)... position enters at open of day 4
    # intraday day 4: close 110 / open 100 - 1 = +10% captured
    assert res.gross_returns.iloc[4] == pytest.approx(0.10)


def test_overnight_attribution():
    opens = [100, 105, 100, 100, 100]
    closes = [100, 105, 100, 100, 100]
    px = make_prices(opens, closes)
    sig = pd.Series([1, 1, 1, 1, 1], index=IDX[:5], dtype=float)
    res = run_backtest(px, sig, CostSpec(0, 0, 0, 0))
    # enter at open day1 (105). overnight day2: 100/105-1 with pos held
    assert res.gross_returns.iloc[2] == pytest.approx(100 / 105 - 1)


def test_costs_charged_on_turnover():
    px = make_prices([100] * 5, [100] * 5)
    sig = pd.Series([0, 1, 1, 0, 0], index=IDX[:5], dtype=float)
    res = run_backtest(px, sig, CostSpec(commission_bps=10, half_spread_bps=40, borrow_bps_annual=0))
    total_cost = res.costs.sum()
    assert total_cost == pytest.approx(2 * 50 / 1e4)  # entry + exit at 50bps one-way
    assert res.n_trades == 2


def test_borrow_accrues_on_shorts_only():
    px = make_prices([100] * 5, [100] * 5)
    long_sig = pd.Series(1.0, index=IDX[:5])
    short_sig = pd.Series(-1.0, index=IDX[:5])
    cl = run_backtest(px, long_sig, CostSpec(0, 0, 0, borrow_bps_annual=252 * 100))
    cs = run_backtest(px, short_sig, CostSpec(0, 0, 0, borrow_bps_annual=252 * 100))
    assert cl.costs.sum() == 0
    assert cs.costs.sum() > 0


def test_signal_lag_delays_entry():
    # +100% intraday move on day 1: lag-0 enters at day-1 open and captures it;
    # lag-1 enters at day-2 open and misses it entirely.
    opens = [100, 100, 200, 200, 200]
    closes = [100, 200, 200, 200, 200]
    px = make_prices(opens, closes)
    sig = pd.Series([1, 1, 1, 1, 1], index=IDX[:5], dtype=float)
    r0 = run_backtest(px, sig, CostSpec(0, 0, 0, 0), signal_lag=0)
    r1 = run_backtest(px, sig, CostSpec(0, 0, 0, 0), signal_lag=1)
    assert r0.returns.sum() > r1.returns.sum()


def test_position_state_machine_max_holding():
    idx = pd.bdate_range("2023-01-02", periods=8)
    entries = pd.Series([True] + [False] * 7, index=idx)
    exits = pd.Series(False, index=idx)
    pos = position_from_events(idx, entries, exits, max_holding_days=3)
    assert pos.iloc[0] == 1.0
    assert pos.iloc[2] == 1.0
    assert pos.iloc[3] == 0.0  # timed out


def test_deterministic():
    rng = np.random.default_rng(0)
    closes = 100 * np.cumprod(1 + rng.normal(0, 0.01, 10))
    px = make_prices(list(closes * 0.999), list(closes))
    sig = pd.Series(rng.choice([0, 1], 10).astype(float), index=IDX)
    a = run_backtest(px, sig, CostSpec()).returns
    b = run_backtest(px, sig, CostSpec()).returns
    pd.testing.assert_series_equal(a, b)
