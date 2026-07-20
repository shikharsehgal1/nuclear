"""Walk-forward evaluation harness with an untouched chronological holdout.

Design for SPUT's short history (2021-07-26 onward, ~5y):
  - HOLDOUT: the final `holdout_frac` of the sample (default last ~15 months) is
    written to disk once and never used for selection. `evaluate_holdout` may be
    called exactly once per strategy family, after parameters are frozen.
  - Walk-forward: expanding window, anchored start, quarterly folds. Parameters
    are chosen on train, applied to the next fold; folds are concatenated into
    a single out-of-sample path.
  - Embargo: `embargo_days` dropped between train end and test start to purge
    overlapping-label leakage.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from dataclasses import dataclass

import pandas as pd


@dataclass
class Fold:
    train_start: pd.Timestamp
    train_end: pd.Timestamp
    test_start: pd.Timestamp
    test_end: pd.Timestamp


def holdout_split(index: pd.DatetimeIndex, holdout_frac: float = 0.25) -> tuple[pd.DatetimeIndex, pd.DatetimeIndex]:
    cut = int(len(index) * (1 - holdout_frac))
    return index[:cut], index[cut:]


def expanding_folds(
    index: pd.DatetimeIndex,
    min_train_days: int = 378,   # ~18 months
    test_days: int = 63,         # ~1 quarter
    embargo_days: int = 5,
) -> Iterator[Fold]:
    i = min_train_days
    while i + embargo_days + 5 < len(index):
        test_end_i = min(i + embargo_days + test_days, len(index)) - 1
        yield Fold(
            train_start=index[0],
            train_end=index[i - 1],
            test_start=index[i + embargo_days],
            test_end=index[test_end_i],
        )
        i += test_days


def walk_forward(
    index: pd.DatetimeIndex,
    param_grid: list[dict],
    fit_score: Callable[[dict, pd.Timestamp, pd.Timestamp], float],
    run_oos: Callable[[dict, pd.Timestamp, pd.Timestamp], pd.Series],
    **fold_kw,
) -> tuple[pd.Series, list[dict]]:
    """Generic walk-forward: for each fold pick argmax fit_score on train,
    run run_oos on test. Returns (concatenated OOS daily returns, fold log)."""
    oos_parts: list[pd.Series] = []
    log: list[dict] = []
    for fold in expanding_folds(index, **fold_kw):
        scores = [(fit_score(p, fold.train_start, fold.train_end), p) for p in param_grid]
        scores = [(s, p) for s, p in scores if s == s]  # drop NaN
        if not scores:
            continue
        best_score, best_p = max(scores, key=lambda t: t[0])
        r = run_oos(best_p, fold.test_start, fold.test_end)
        oos_parts.append(r)
        log.append({
            "train_end": str(fold.train_end.date()), "test_start": str(fold.test_start.date()),
            "test_end": str(fold.test_end.date()), "chosen": best_p, "train_score": best_score,
            "oos_mean_daily": float(r.mean()) if len(r) else float("nan"),
            "oos_sum": float(r.sum()) if len(r) else float("nan"),
        })
    oos = pd.concat(oos_parts).sort_index() if oos_parts else pd.Series(dtype=float)
    oos = oos[~oos.index.duplicated(keep="first")]
    return oos, log
