"""Robustness suite on the development sample for families that cleared the
WF screen (net WF Sharpe > 0.3). Modal walk-forward parameters are used as the
frozen configuration. Holdout remains untouched here.

Tests per family: cost multipliers 0.5/1/2/3x, +1d signal lag, placebo signal
shifts (+/-5d) and sign reversal, parameter neighborhood (+/-1 grid step),
leave-one-year-out, stationary-bootstrap Sharpe CI, deflated Sharpe using the
logged trial count, top-5 trade PnL share, and single-year PnL concentration.
"""

from __future__ import annotations

import json

import pandas as pd
import yaml

from sput_research.paths import CONFIG, TABLES
from sput_research.statistics.metrics import (
    deflated_sharpe,
    sharpe,
    stationary_bootstrap_sharpe_ci,
)
from sput_research.statistics.walkforward import holdout_split
from sput_research.strategies.families import FAMILY_BUILDERS, run_legs

CFG = yaml.safe_load((CONFIG / "preregistered_parameters.yaml").read_text())
SCREEN_MIN_SHARPE = 0.3


def dev_slice(r: pd.Series) -> pd.Series:
    dev_idx, _ = holdout_split(r.index, CFG["sample"]["holdout_frac"])
    return r.loc[dev_idx]


def trade_blocks(pos: pd.Series, net: pd.Series) -> list[float]:
    """PnL per contiguous held block on the primary leg."""
    blocks, cur, in_pos = [], 0.0, False
    for d in pos.index:
        p = pos.loc[d]
        if p != 0:
            in_pos = True
            cur += float(net.get(d, 0.0))
        elif in_pos:
            blocks.append(cur)
            cur, in_pos = 0.0, False
    if in_pos:
        blocks.append(cur)
    return blocks


def neighbors(p: dict) -> list[dict]:
    G = CFG["grids"]
    out = []
    for key, gridname in [("z_window", "z_window"), ("entry_z", "entry_z"),
                          ("exit_z", "exit_z"), ("holding_cap_days", "holding_cap_days"),
                          ("trend_window", "trend_window")]:
        if key not in p:
            continue
        vals = G[gridname]
        i = vals.index(p[key])
        for j in (i - 1, i + 1):
            if 0 <= j < len(vals):
                q = dict(p)
                q[key] = vals[j]
                out.append(q)
    return out


def main() -> int:
    wf = pd.read_csv(TABLES / "wf_results.csv")
    trials = json.loads((TABLES / "trial_count.json").read_text())["total"]
    combo_sharpes = json.loads((TABLES / "combo_sharpes.json").read_text())
    rows = []
    for _, fam_row in wf.iterrows():
        family = fam_row["family"]
        if fam_row["sharpe"] <= SCREEN_MIN_SHARPE:
            rows.append({"family": family, "status": f"screened_out (wf_sharpe={fam_row['sharpe']:.2f})"})
            continue
        params = json.loads(fam_row["modal_params"])
        builder = FAMILY_BUILDERS[family]
        legs = builder(params)

        r_base = dev_slice(run_legs(legs, 1.0, 0))
        rec: dict = {"family": family, "params": json.dumps(params), "status": "tested",
                     "dev_sharpe_1x": sharpe(r_base)}

        for m in [0.5, 2.0, 3.0]:
            rec[f"sharpe_{m}x_cost"] = sharpe(dev_slice(run_legs(legs, m, 0)))
        rec["sharpe_lag1"] = sharpe(dev_slice(run_legs(legs, 1.0, 1)))

        # placebos: shift the target positions in time; reverse sign
        for shift in (-5, 5):
            legs_s = [type(leg)(leg.instrument, leg.prices, leg.target_pos.shift(shift).fillna(0.0),
                                leg.is_short_capable) for leg in legs]
            rec[f"placebo_shift{shift}"] = sharpe(dev_slice(run_legs(legs_s, 1.0, 0)))
        legs_r = [type(leg)(leg.instrument, leg.prices, -leg.target_pos, leg.is_short_capable)
                  for leg in legs]
        rec["placebo_reversed"] = sharpe(dev_slice(run_legs(legs_r, 1.0, 0)))

        nb = [sharpe(dev_slice(run_legs(builder(q), 1.0, 0))) for q in neighbors(params)]
        rec["neighbor_sharpe_min"] = float(pd.Series(nb).min())
        rec["neighbor_sharpe_median"] = float(pd.Series(nb).median())
        rec["neighbor_frac_positive"] = float(pd.Series(nb).gt(0).mean())

        years = r_base.index.year.unique()
        loo = {int(y): sharpe(r_base[r_base.index.year != y]) for y in years}
        rec["loo_year_min_sharpe"] = min(loo.values())
        yearly = r_base.groupby(r_base.index.year).sum()
        total = yearly.sum()
        rec["max_year_pnl_share"] = float((yearly / total).max()) if total > 0 else float("nan")

        lo, hi = stationary_bootstrap_sharpe_ci(r_base)
        rec["sharpe_ci_lo"], rec["sharpe_ci_hi"] = lo, hi
        # DSR with the empirical variance of annualized Sharpe across ALL logged
        # trials (all families pooled), converted to daily-SR variance
        all_trial_sharpes = pd.Series(
            [s for fam in combo_sharpes.values() for s in fam]).dropna()
        var_daily = float(all_trial_sharpes.var(ddof=1)) / 252.0
        rec["dsr"] = deflated_sharpe(r_base, n_trials=trials, sr_variance_across_trials=var_daily)
        # secondary, less conservative: deflate only within this family's grid
        fam_sh = pd.Series(combo_sharpes.get(family, [])).dropna()
        if len(fam_sh) > 2:
            rec["dsr_family"] = deflated_sharpe(
                r_base, n_trials=len(fam_sh),
                sr_variance_across_trials=float(fam_sh.var(ddof=1)) / 252.0)

        # engine-aligned positions: ffill to price calendar, then the engine's +1 shift
        pos_engine = (legs[0].target_pos.reindex(r_base.index).ffill().fillna(0.0)
                      .shift(1).fillna(0.0))
        blocks = trade_blocks(pos_engine, r_base)
        if blocks:
            s = pd.Series(blocks).sort_values(ascending=False)
            rec["n_trades"] = len(s)
            rec["top5_trade_pnl_share"] = float(s.head(5).sum() / s.sum()) if s.sum() > 0 else float("nan")
        rows.append(rec)
        print(f"{family}: 1x={rec['dev_sharpe_1x']:.2f} 2x={rec.get('sharpe_2x_cost', float('nan')):.2f} "
              f"lag1={rec['sharpe_lag1']:.2f} DSR={rec['dsr']:.2f} "
              f"nbr_min={rec['neighbor_sharpe_min']:.2f} looYmin={rec['loo_year_min_sharpe']:.2f}")

    pd.DataFrame(rows).to_csv(TABLES / "robustness_results.csv", index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
