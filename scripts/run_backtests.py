"""Run pre-registered strategy families through expanding-window walk-forward
on the development sample (first 75%); the final 25% holdout is NOT touched.

Per family:
  - compute net returns once per grid point over the dev sample
  - walk-forward: per fold, select grid point by net train Sharpe, take its
    test-slice returns
  - log every grid point evaluated (trial accounting for deflated Sharpe)
Outputs: reports/tables/wf_results.csv, wf_fold_log.json, trial_count.json,
          data/processed/wf_oos_returns.parquet
"""

from __future__ import annotations

import itertools
import json

import pandas as pd
import yaml

from sput_research.paths import CONFIG, PROCESSED, TABLES
from sput_research.statistics.metrics import sharpe, summarize
from sput_research.statistics.walkforward import expanding_folds, holdout_split
from sput_research.strategies.families import FAMILY_BUILDERS, run_legs

CFG = yaml.safe_load((CONFIG / "preregistered_parameters.yaml").read_text())
G = CFG["grids"]


def grid_for(family: str) -> list[dict]:
    dims = {
        "z_window": G["z_window"],
        "entry_z": G["entry_z"],
        "exit_z": G["exit_z"],
        "holding_cap_days": G["holding_cap_days"],
    }
    if family == "B_trend":
        dims["trend_window"] = G["trend_window"]
    keys = list(dims)
    return [dict(zip(keys, vals)) for vals in itertools.product(*(dims[k] for k in keys))]


def main() -> int:
    wf_cfg = CFG["sample"]["walk_forward"]
    results, fold_logs, trials = [], {}, {}
    oos_paths, combo_sharpes = {}, {}

    for family, builder in FAMILY_BUILDERS.items():
        grid = grid_for(family)
        # returns per grid point over the FULL dev sample
        returns_by_combo = {}
        for i, p in enumerate(grid):
            legs = builder(p)
            if not legs:
                print(f"{family}: no data, skipped")
                break
            r = run_legs(legs, multiplier=1.0, signal_lag=0)
            returns_by_combo[i] = r
        if not returns_by_combo:
            continue

        full_idx = returns_by_combo[0].index
        dev_idx, hold_idx = holdout_split(full_idx, CFG["sample"]["holdout_frac"])
        trials[family] = len(grid)
        combo_sharpes[family] = [sharpe(r.loc[dev_idx[0]:dev_idx[-1]]) for r in returns_by_combo.values()]

        folds = list(expanding_folds(dev_idx, **wf_cfg))
        oos_parts, log = [], []
        for fold in folds:
            best_i, best_s = None, -1e9
            for i, r in returns_by_combo.items():
                s = sharpe(r.loc[fold.train_start:fold.train_end])
                if s == s and s > best_s:
                    best_i, best_s = i, s
            if best_i is None:
                continue
            seg = returns_by_combo[best_i].loc[fold.test_start:fold.test_end]
            oos_parts.append(seg)
            log.append({"train_end": str(fold.train_end.date()),
                        "test": f"{fold.test_start.date()}->{fold.test_end.date()}",
                        "chosen": grid[best_i], "train_sharpe": round(best_s, 2),
                        "test_ret_sum": round(float(seg.sum()), 4)})
        if not oos_parts:
            continue
        oos = pd.concat(oos_parts).sort_index()
        oos = oos[~oos.index.duplicated()]
        oos_paths[family] = oos
        fold_logs[family] = log

        # modal parameter across folds (pre-specified freezing rule)
        chosen_series = pd.Series([json.dumps(e["chosen"], sort_keys=True) for e in log])
        modal = json.loads(chosen_series.mode().iloc[0])

        stats = summarize(oos, family)
        stats.update({
            "family": family,
            "n_folds": len(log),
            "positive_folds_frac": float(pd.Series([e["test_ret_sum"] for e in log]).gt(0).mean()),
            "modal_params": json.dumps(modal),
            "dev_end": str(dev_idx[-1].date()),
            "grid_size": len(grid),
        })
        results.append(stats)
        print(f"{family}: WF-OOS sharpe={stats['sharpe']:.2f}, folds+={stats['positive_folds_frac']:.0%}, "
              f"modal={modal}")

    pd.DataFrame(results).to_csv(TABLES / "wf_results.csv", index=False)
    (TABLES / "wf_fold_log.json").write_text(json.dumps(fold_logs, indent=2))
    (TABLES / "trial_count.json").write_text(json.dumps(
        {"per_family": trials, "total": sum(trials.values())}, indent=2))
    (TABLES / "combo_sharpes.json").write_text(json.dumps(combo_sharpes, indent=2))
    if oos_paths:
        pd.DataFrame(oos_paths).to_parquet(PROCESSED / "wf_oos_returns.parquet")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
