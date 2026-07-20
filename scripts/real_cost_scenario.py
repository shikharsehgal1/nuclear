"""Re-run G_sput_yca with MEASURED (2026-07-20 live) costs instead of assumed:
usage: uv run python scripts/real_cost_scenario.py <uun_half_spread_bps> <yca_half_spread_bps>

Measured inputs (data/raw/live_quotes/): borrow SRUUF 2.77% (proxy for U.UN
short), YLLXF 0.68% (proxy fee for YCA short; availability caveat separate).
Assumed-vs-real is reported for the base case, the 2x-spread stress and the
joint 2x+1-day-lag stress that the red team flagged as decisive.
"""

import json
import sys

import pandas as pd

from sput_research.backtest.engine import CostSpec, run_backtest
from sput_research.paths import TABLES
from sput_research.statistics.metrics import sharpe
from sput_research.statistics.walkforward import holdout_split
from sput_research.strategies.families import FAMILY_BUILDERS


def run(legs, specs, lag=0):
    total = None
    for leg, spec in zip(legs, specs):
        r = run_backtest(leg.prices, leg.target_pos, spec, signal_lag=lag).returns
        total = r if total is None else total.add(r, fill_value=0.0)
    return total


def main() -> int:
    uun_hs = float(sys.argv[1])
    yca_hs = float(sys.argv[2])
    hold = pd.read_csv(TABLES / "holdout_results.csv").set_index("family")
    params = json.loads(hold.loc["G_sput_yca", "params"])
    legs = FAMILY_BUILDERS["G_sput_yca"](params)  # [U-UN.TO leg, YCA.L leg]

    def specs(mult):
        return [
            CostSpec(commission_bps=1.0, half_spread_bps=uun_hs, fx_spread_bps=0.0,
                     borrow_bps_annual=277, multiplier=mult),
            CostSpec(commission_bps=1.0, half_spread_bps=yca_hs, fx_spread_bps=2.5,
                     borrow_bps_annual=68, multiplier=mult),
        ]

    rows = []
    for label, mult, lag in [("real_1x", 1.0, 0), ("real_2x", 2.0, 0),
                             ("real_2x_lag1", 2.0, 1), ("real_1x_lag1", 1.0, 1)]:
        r = run(legs, specs(mult), lag)
        dev_idx, hold_idx = holdout_split(r.index, 0.25)
        rows.append({"scenario": label,
                     "dev_sharpe": round(sharpe(r.loc[dev_idx]), 2),
                     "holdout_sharpe": round(sharpe(r.loc[hold_idx]), 2),
                     "full_sharpe": round(sharpe(r), 2),
                     "ann_ret_full": round(float(r.mean() * 252), 4)})
    out = pd.DataFrame(rows)
    out.to_csv(TABLES / "real_cost_scenarios.csv", index=False)
    print(f"measured half-spreads: U.UN {uun_hs}bps, YCA {yca_hs}bps; borrow 277/68bps")
    print(out.to_string(index=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
