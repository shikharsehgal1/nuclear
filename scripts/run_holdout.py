"""ONE-SHOT untouched-holdout evaluation. Eligible families and their frozen
(modal walk-forward) parameters are read from the robustness stage; this
script may be run once per family — it refuses to run again if results exist
(delete reports/tables/holdout_results.csv only via a DECISION_LOG entry).

Eligibility (from pre-registered gates applied to dev-sample robustness):
passed WF screen AND neighbor plateau (min neighbor Sharpe > 0) AND
LOO-year min > 0 AND >= 10 trades.
"""

from __future__ import annotations

import json
import sys

import pandas as pd
import yaml

from sput_research.paths import CONFIG, TABLES
from sput_research.statistics.metrics import sharpe, summarize
from sput_research.statistics.walkforward import holdout_split
from sput_research.strategies.families import FAMILY_BUILDERS, run_legs

CFG = yaml.safe_load((CONFIG / "preregistered_parameters.yaml").read_text())
OUT = TABLES / "holdout_results.csv"


def main() -> int:
    if OUT.exists() and "--force-rerun-with-decision-log-entry" not in sys.argv:
        print(f"{OUT} exists; holdout may be evaluated only once. Aborting.")
        return 1
    rob = pd.read_csv(TABLES / "robustness_results.csv")
    rob = rob[rob["status"] == "tested"]
    eligible = rob[(rob["neighbor_sharpe_min"] > 0)
                   & (rob["loo_year_min_sharpe"] > 0)
                   & (rob["n_trades"] >= 10)]
    print(f"eligible: {list(eligible['family'])}")

    rows = []
    for _, e in eligible.iterrows():
        family, params = e["family"], json.loads(e["params"])
        legs = FAMILY_BUILDERS[family](params)
        r_full = run_legs(legs, 1.0, 0)
        _, hold_idx = holdout_split(r_full.index, CFG["sample"]["holdout_frac"])
        r_h = r_full.loc[hold_idx]
        rec = summarize(r_h, family)
        rec.update({
            "family": family, "params": json.dumps(params),
            "holdout_start": str(hold_idx[0].date()), "holdout_end": str(hold_idx[-1].date()),
            "holdout_sharpe_2x": sharpe(run_legs(legs, 2.0, 0).loc[hold_idx]),
            "holdout_sharpe_lag1": sharpe(run_legs(legs, 1.0, 1).loc[hold_idx]),
        })
        rows.append(rec)
        print(f"{family}: HOLDOUT net sharpe={rec['sharpe']:.2f} "
              f"(2x={rec['holdout_sharpe_2x']:.2f}, lag1={rec['holdout_sharpe_lag1']:.2f}), "
              f"{rec['n_days']} days, maxDD={rec['max_dd']:.1%}")

    pd.DataFrame(rows).to_csv(OUT, index=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
