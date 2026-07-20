"""Vectorized daily backtester with explicit point-in-time execution semantics.

Timing model
------------
A signal computed from information available at the close of day t-1 (or earlier,
via `signal_lag` extra days) is executed at the OPEN of day t. Daily P&L therefore
splits into an overnight leg carried at the old position and an intraday leg at
the new position:

    r_t = pos_{t-1} * (open_t / close_{t-1} - 1) + pos_t * (close_t / open_t - 1)

There are no same-close fills anywhere in this engine.

Costs are charged on turnover at execution: commission + half-spread (+ optional
FX spread), plus daily borrow on short exposure. All in bps, all configurable,
all scalable by a stress multiplier.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class CostSpec:
    commission_bps: float = 1.0
    half_spread_bps: float = 10.0
    fx_spread_bps: float = 0.0
    borrow_bps_annual: float = 300.0
    impact_bps: float = 0.0          # flat per-trade impact add-on (capacity module refines)
    multiplier: float = 1.0

    @property
    def oneway_bps(self) -> float:
        return (self.commission_bps + self.half_spread_bps + self.fx_spread_bps + self.impact_bps) * self.multiplier


@dataclass
class BacktestResult:
    returns: pd.Series          # net daily strategy returns
    gross_returns: pd.Series
    positions: pd.Series        # position held during day t intraday leg
    turnover: pd.Series
    costs: pd.Series
    n_trades: int
    meta: dict = field(default_factory=dict)

    def to_frame(self) -> pd.DataFrame:
        return pd.DataFrame({
            "net": self.returns, "gross": self.gross_returns,
            "pos": self.positions, "turnover": self.turnover, "cost": self.costs,
        })


def run_backtest(
    prices: pd.DataFrame,
    target_pos: pd.Series,
    costs: CostSpec,
    signal_lag: int = 0,
    hedge_prices: pd.DataFrame | None = None,
    hedge_pos: pd.Series | None = None,
    hedge_costs: CostSpec | None = None,
) -> BacktestResult:
    """prices: DataFrame with 'open','close' indexed by date (trading days).
    target_pos: desired position (+1 long .. -1 short), indexed by SIGNAL date —
        the day at whose close the information existed. Executed at open of the
        next trading day (plus signal_lag additional days).
    Optional hedge leg follows identical timing.
    """
    px = prices[["open", "close"]].dropna()
    idx = px.index

    # Shift: signal at close of t → position effective for intraday leg of t+1+lag.
    pos = target_pos.reindex(idx).ffill().fillna(0.0).shift(1 + signal_lag).fillna(0.0)
    pos_prev = pos.shift(1).fillna(0.0)

    overnight = px["open"] / px["close"].shift(1) - 1.0
    intraday = px["close"] / px["open"] - 1.0
    gross = pos_prev * overnight.fillna(0.0) + pos * intraday

    turnover = (pos - pos_prev).abs()
    trade_cost = turnover * costs.oneway_bps / 1e4
    borrow = pos.clip(upper=0.0).abs() * (costs.borrow_bps_annual * costs.multiplier) / 1e4 / 252.0
    cost = trade_cost + borrow

    net = gross - cost

    if hedge_pos is not None:
        hp = (hedge_prices if hedge_prices is not None else prices)[["open", "close"]].dropna()
        hres = run_backtest(hp, hedge_pos, hedge_costs or costs, signal_lag=signal_lag)
        net = net.add(hres.returns.reindex(idx).fillna(0.0), fill_value=0.0)
        gross = gross.add(hres.gross_returns.reindex(idx).fillna(0.0), fill_value=0.0)
        cost = cost.add(hres.costs.reindex(idx).fillna(0.0), fill_value=0.0)
        turnover = turnover.add(hres.turnover.reindex(idx).fillna(0.0), fill_value=0.0)

    n_trades = int((turnover > 1e-9).sum())
    return BacktestResult(net, gross, pos, turnover, cost, n_trades)


def position_from_events(
    index: pd.DatetimeIndex,
    entries: pd.Series,
    exits: pd.Series,
    direction: pd.Series | None = None,
    max_holding_days: int | None = None,
) -> pd.Series:
    """State-machine position builder: enter on entry-signal days, hold until an
    exit signal or max_holding_days elapse. entries/exits are boolean Series on
    signal dates; direction (default +1) gives signed size at entry."""
    ent = entries.reindex(index).fillna(False).to_numpy(dtype=bool)
    exi = exits.reindex(index).fillna(False).to_numpy(dtype=bool)
    dire = (direction.reindex(index).ffill().fillna(1.0) if direction is not None
            else pd.Series(1.0, index=index)).to_numpy(dtype=float)
    pos = np.zeros(len(index))
    holding = 0
    for i in range(len(index)):
        prev = pos[i - 1] if i else 0.0
        if prev != 0.0:
            holding += 1
            timeout = max_holding_days is not None and holding >= max_holding_days
            pos[i] = 0.0 if (exi[i] or timeout) else prev
            if pos[i] == 0.0:
                holding = 0
        if pos[i] == 0.0 and ent[i]:
            pos[i] = dire[i]
            holding = 0
    return pd.Series(pos, index=index)
