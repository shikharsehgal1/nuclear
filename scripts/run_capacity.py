"""Capacity and market-impact analysis for holdout-evaluated families.

Model: for capital C, a day with position change |dpos| trades Q = C*|dpos|
notional on each affected leg. Costs added on top of the base 1x stack:
  impact_bps = coeff * daily_vol_bps * sqrt(Q / ADV_leg)
Participation constraint: Q <= plimit * ADV_leg; days violating it are counted
(fills would need to extend over multiple days -> slippage/decay reported as
the impact at the capped size plus a violation count, not silently ignored).
Liquidation time = full position notional / (plimit * ADV of the thinnest leg).
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd
import yaml

from sput_research.paths import CONFIG, TABLES
from sput_research.statistics.metrics import sharpe
from sput_research.strategies.families import FAMILY_BUILDERS, run_legs

CAPITALS = [100_000, 500_000, 1_000_000, 5_000_000, 10_000_000, 25_000_000]
PLIMITS = [0.01, 0.025, 0.05, 0.10]
COSTS = yaml.safe_load((CONFIG / "costs.yaml").read_text())
COEFF = COSTS["defaults"]["impact_coefficient"]


def leg_stats(leg) -> pd.DataFrame:
    px = leg.prices
    adv = (px["close"] * px["volume"]).rolling(60, min_periods=20).median()
    vol_bps = px["close"].pct_change().rolling(60, min_periods=20).std() * 1e4
    pos = leg.target_pos.reindex(px.index).ffill().fillna(0.0).shift(1).fillna(0.0)
    dpos = pos.diff().abs().fillna(0.0)
    return pd.DataFrame({"adv": adv, "vol_bps": vol_bps, "pos": pos, "dpos": dpos})


def main() -> int:
    hold = pd.read_csv(TABLES / "holdout_results.csv")
    rows = []
    for _, h in hold.iterrows():
        family, params = h["family"], json.loads(h["params"])
        legs = FAMILY_BUILDERS[family](params)
        base = run_legs(legs, 1.0, 0)
        stats = [leg_stats(leg) for leg in legs]

        for C in CAPITALS:
            drag = pd.Series(0.0, index=base.index)
            viol_days = 0
            for leg, st in zip(legs, stats):
                st_al = st.reindex(base.index)
                q = C * st_al["dpos"]
                cap = 0.05 * st_al["adv"]
                viol_days += int((q > cap).sum())
                q_eff = np.minimum(q, cap)
                imp_bps = COEFF * st_al["vol_bps"] * np.sqrt((q_eff / st_al["adv"]).clip(0, 1))
                drag = drag.add((st_al["dpos"] * imp_bps / 1e4).fillna(0.0), fill_value=0.0)
            r_c = base - drag
            # liquidation: worst-day position notional vs thinnest leg
            liq_days = max(
                float((C * st.reindex(base.index)["pos"].abs().max()) /
                      max(1.0, 0.05 * st.reindex(base.index)["adv"].median()))
                for st in stats)
            rows.append({
                "family": family, "capital_usd": C,
                "net_sharpe_with_impact": sharpe(r_c),
                "annual_impact_drag_bps": float(drag.mean() * 252 * 1e4),
                "participation_violation_days": viol_days,
                "n_days": int(base.notna().sum()),
                "est_liquidation_days_5pct": round(liq_days, 1),
            })
        thin = min(float(st["adv"].median()) for st in stats)
        print(f"{family}: thinnest-leg median ADV ${thin:,.0f}")

    df = pd.DataFrame(rows)
    df.to_csv(TABLES / "capacity_results.csv", index=False)
    print(df.pivot(index="capital_usd", columns="family",
                   values="net_sharpe_with_impact").round(2).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
