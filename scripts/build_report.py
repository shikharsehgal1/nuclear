"""Assemble reports/strategy_leaderboard.csv from stage outputs and verify
report artifacts exist."""

from __future__ import annotations


import pandas as pd

from sput_research.paths import REPORTS, TABLES

DECISIONS = {
    "A_long": ("REJECT", "fails 1-day-lag gate (holdout lag1 0.49 vs 1.79 base = 27% retention; "
                          "gate >=50%); top5 trade share 53% > 50%; pooled DSR 0.00"),
    "A_longshort": ("REJECT", "lag1 negative on holdout; depends on unverified U.UN borrow; "
                              "single-year concentration 63%"),
    "B_trend": ("REJECT", "2 trades in dev sample (parameter island); 11% positive WF folds"),
    "F_crossline": ("REJECT", "net WF Sharpe -2.36: spread never exceeds round-trip costs; "
                               "NOT arbitrage"),
    "G_sput_yca": ("CONDITIONAL NO-GO", "passes all holdout gates (1.14 net; 0.63 at 2x costs; "
                    "lag1 54% retention) and plateau/LOO/concentration tests, but fails the "
                    "pre-registered pooled deflated-Sharpe gate (0.08); capacity <= ~$5M; "
                    "short-leg borrow unverified. Verdict: promising - paper-trade, do not deploy"),
    "H_hedged_resid": ("REJECT", "neighbor Sharpe -0.40 (no parameter plateau); 40% positive folds"),
    "H_unhedged_resid": ("REJECT", "WF Sharpe 0.22 below screen"),
}


def main() -> int:
    wf = pd.read_csv(TABLES / "wf_results.csv").set_index("family")
    rob = pd.read_csv(TABLES / "robustness_results.csv").set_index("family")
    hold = (pd.read_csv(TABLES / "holdout_results.csv").set_index("family")
            if (TABLES / "holdout_results.csv").exists() else pd.DataFrame())
    cap = (pd.read_csv(TABLES / "capacity_results.csv")
           if (TABLES / "capacity_results.csv").exists() else pd.DataFrame())

    rows = []
    for fam in wf.index:
        w = wf.loc[fam]
        r = rob.loc[fam] if fam in rob.index else pd.Series(dtype=float)
        h = hold.loc[fam] if len(hold) and fam in hold.index else pd.Series(dtype=float)
        c = cap[cap["family"] == fam].set_index("capital_usd") if len(cap) else pd.DataFrame()
        decision, reason = DECISIONS.get(fam, ("UNTESTED", ""))
        rows.append({
            "strategy": fam,
            "economic_mechanism": {
                "A_long": "closed-end discount mean reversion (flow-driven)",
                "A_longshort": "premium/discount two-sided reversion",
                "B_trend": "discount reversion gated by NAV trend",
                "F_crossline": "same-trust dual-line FX-adjusted parity",
                "G_sput_yca": "two physical-U holders' relative premium reversion",
                "H_hedged_resid": "SPUT-specific residual vs uranium-equity beta",
                "H_unhedged_resid": "as H without hedge",
            }.get(fam, ""),
            "frequency": "daily signal, next-open execution",
            "parameters": w.get("modal_params", ""),
            "wf_oos_sharpe_net": round(float(w.get("sharpe", float("nan"))), 2),
            "dev_sharpe_net": round(float(r.get("dev_sharpe_1x", float("nan"))), 2),
            "holdout_sharpe_net": round(float(h.get("sharpe", float("nan"))), 2),
            "sortino_holdout": round(float(h.get("sortino", float("nan"))), 2),
            "cagr_holdout": round(float(h.get("cagr", float("nan"))), 4),
            "max_dd_holdout": round(float(h.get("max_dd", float("nan"))), 3),
            "positive_fold_ratio": round(float(w.get("positive_folds_frac", float("nan"))), 2),
            "top5_trade_pnl_share": round(float(r.get("top5_trade_pnl_share", float("nan"))), 2),
            "n_trades_dev": r.get("n_trades", float("nan")),
            "cost_2x_sharpe_dev": round(float(r.get("sharpe_2.0x_cost", float("nan"))), 2),
            "cost_2x_sharpe_holdout": round(float(h.get("holdout_sharpe_2x", float("nan"))), 2),
            "one_day_lag_sharpe_holdout": round(float(h.get("holdout_sharpe_lag1", float("nan"))), 2),
            "dsr_pooled": round(float(r.get("dsr", float("nan"))), 2),
            "dsr_family": round(float(r.get("dsr_family", float("nan"))), 2),
            "capacity_sharpe_1m": round(float(c.loc[1_000_000, "net_sharpe_with_impact"]), 2) if len(c) else float("nan"),
            "capacity_sharpe_5m": round(float(c.loc[5_000_000, "net_sharpe_with_impact"]), 2) if len(c) else float("nan"),
            "capacity_sharpe_10m": round(float(c.loc[10_000_000, "net_sharpe_with_impact"]), 2) if len(c) else float("nan"),
            "final_decision": decision,
            "rejection_reason": reason,
        })
    lb = pd.DataFrame(rows).sort_values("holdout_sharpe_net", ascending=False)
    lb.to_csv(REPORTS / "strategy_leaderboard.csv", index=False)
    print(lb[["strategy", "wf_oos_sharpe_net", "holdout_sharpe_net", "final_decision"]]
          .to_string(index=False))

    missing = [p for p in ["FINAL_REPORT.md"] if not (REPORTS / p).exists()]
    if missing:
        print(f"NOTE: missing report artifacts: {missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
