"""Timing tests for the overnight study: return split identity, no lookahead in
monthly selection, and the up-day signal using the PREVIOUS session."""

import numpy as np
import pandas as pd

from sput_research.overnight.data import split_returns
from sput_research.overnight.strategy import backtest, select, up_day_tilt, weights


def _bars(n=400, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n)
    c = 50 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = c * np.exp(rng.normal(0, 0.005, n))
    return pd.DataFrame({"Open": o, "High": np.maximum(o, c) * 1.01, "Low": np.minimum(o, c) * 0.99,
                         "Close": c, "AdjClose": c, "Volume": 1e6}, index=idx)


def _panel(n=900, k=6, seed=1):
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2015-01-01", periods=n)
    cols = [f"T{i}" for i in range(k)]
    on = pd.DataFrame(rng.normal(0.0005, 0.01, (n, k)), idx, cols)
    idr = pd.DataFrame(rng.normal(-0.0005, 0.01, (n, k)), idx, cols)
    return {"on": on, "id": idr, "cc": (1 + on) * (1 + idr) - 1,
            "dollar_vol": pd.DataFrame(1e8, idx, cols), "price": pd.DataFrame(50.0, idx, cols),
            "half_spread_bps": pd.DataFrame(2.0, idx, cols)}


def test_split_identity():
    r = split_returns(_bars()).dropna()
    assert np.allclose((1 + r.on) * (1 + r.id), 1 + r.cc)


def test_overnight_is_prev_close_to_open():
    d = _bars()
    r = split_returns(d)
    t = d.index[10]
    assert np.isclose(r.on.loc[t], d.Open.loc[t] / d.Close.shift().loc[t] - 1)


def test_stale_bar_invalidates_next_overnight():
    d = _bars()
    t = d.index[50]
    d.loc[t, ["Open", "High", "Low"]] = d.loc[t, "Close"]
    r = split_returns(d)
    assert np.isnan(r.on.loc[t]) and np.isnan(r.on.loc[d.index[51]])


def test_selection_has_no_lookahead(monkeypatch):
    from sput_research.overnight import strategy
    P = _panel()
    monkeypatch.setattr(strategy, "tradeable_universe", lambda: list(P["on"].columns))
    base = select(P, 12, 2)
    m = pd.Timestamp("2017-06-01")
    poisoned = {k: v.copy() for k, v in P.items()}
    poisoned["on"].loc[poisoned["on"].index >= m, "T5"] = 0.05   # T5 explodes from June on
    after = select(poisoned, 12, 2)
    june = (base.index >= m) & (base.index < pd.Timestamp("2017-07-01"))
    assert base.loc[june].equals(after.loc[june])


def test_up_day_signal_uses_previous_session():
    P = _panel()
    w = pd.DataFrame(0.5, P["on"].index, ["T0", "T1"])
    t, t1 = P["on"].index[100], P["on"].index[101]
    P["id"].loc[t, ["T0", "T1"]] = [0.02, -0.02]
    tilt = up_day_tilt(P, w)
    assert tilt.loc[t1, "T0"] == 2.0 and tilt.loc[t1, "T1"] == 0.0   # night after t: only T0
    P2 = {k: v.copy() for k, v in P.items()}
    P2["id"].loc[t1, ["T0", "T1"]] = [-0.5, 0.5]                     # poison day t1's own session
    assert up_day_tilt(P2, w).loc[t1].equals(tilt.loc[t1])


def test_ls_pays_twice_the_sides_and_missing_legs_are_untraded():
    P = _panel()
    w = weights(P, pd.DataFrame(1.0, P["on"].index, P["on"].columns)).iloc[100:]
    on = backtest(P, w, "ON", "auction").iloc[50:]
    ls = backtest(P, w, "LS", "auction").iloc[50:]
    assert np.allclose(ls.cost, 2 * on.cost)
    P["on"].iloc[160, :] = np.nan
    r = backtest(P, w, "ON", "auction")
    assert r.iloc[60].gross == 0 and r.iloc[60].cost == 0
