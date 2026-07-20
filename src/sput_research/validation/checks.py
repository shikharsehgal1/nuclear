"""Data-quality and point-in-time integrity checks.

Each check returns a list of Issue records; `run_all` aggregates them. Severity
'fatal' issues must stop the pipeline; 'warn' issues are recorded in the
decision log and reports.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SPUT_START = pd.Timestamp("2021-07-26")  # first real SPUT trading day post-UPC conversion
UPC_CONVERSION = pd.Timestamp("2021-07-19")


@dataclass
class Issue:
    check: str
    severity: str  # 'fatal' | 'warn' | 'info'
    detail: str


def check_duplicates(df: pd.DataFrame, keys: list[str]) -> list[Issue]:
    dups = df.duplicated(subset=keys).sum()
    return [Issue("duplicates", "fatal", f"{dups} duplicate rows on {keys}")] if dups else []


def check_stale_prices(px: pd.Series, max_run: int = 5) -> list[Issue]:
    """Flag runs of identical consecutive closes longer than max_run (excl. NaN)."""
    x = px.dropna()
    same = (x.diff() == 0)
    run = same.groupby((~same).cumsum()).cumsum()
    worst = int(run.max()) if len(run) else 0
    if worst >= max_run:
        return [Issue("stale_prices", "warn", f"longest identical-close run = {worst} days")]
    return []


def check_price_jumps(px: pd.Series, thresh: float = 0.5) -> list[Issue]:
    r = px.pct_change().abs()
    jumps = r[r > thresh]
    return [Issue("price_jumps", "warn",
                  f"{len(jumps)} daily moves > {thresh:.0%}: {list(jumps.index.date)[:5]}")] if len(jumps) else []


def check_nav_arithmetic(df: pd.DataFrame, tol: float = 0.02) -> list[Issue]:
    """total_nav ≈ nav_per_unit * units_outstanding, where all three present."""
    sub = df.dropna(subset=["total_nav", "published_nav", "units_outstanding"])
    if not len(sub):
        return [Issue("nav_arithmetic", "info", "no rows with all three NAV fields")]
    rel = (sub["total_nav"] - sub["published_nav"] * sub["units_outstanding"]).abs() / sub["total_nav"]
    bad = int((rel > tol).sum())
    return [Issue("nav_arithmetic", "warn" if bad else "info",
                  f"{bad}/{len(sub)} rows violate total≈per-unit×units at {tol:.0%}")]


def check_premium_reconstruction(df: pd.DataFrame, tol: float = 0.005) -> list[Issue]:
    """published premium/discount vs (close/NAV - 1) in matching currency."""
    sub = df.dropna(subset=["premium_discount_published", "close", "published_nav"])
    if not len(sub):
        return [Issue("premium_reconstruction", "info", "no overlapping premium rows")]
    recon = sub["close"] / sub["published_nav"] - 1.0
    diff = (recon - sub["premium_discount_published"]).abs()
    bad = int((diff > tol).sum())
    sev = "warn" if bad > 0.05 * len(sub) else "info"
    return [Issue("premium_reconstruction", sev,
                  f"{bad}/{len(sub)} rows differ from published premium by >{tol:.1%} "
                  f"(median abs diff {diff.median():.4f})")]


def check_holdings_monotonic(h: pd.Series, max_daily_add_pct: float = 0.10) -> list[Issue]:
    """SPUT cannot sell uranium (verify in MECHANICS); holdings should be
    non-decreasing and daily adds bounded."""
    issues: list[Issue] = []
    x = h.dropna()
    drops = x.diff() < -1e-6
    if drops.any():
        issues.append(Issue("holdings_decrease", "warn",
                            f"{int(drops.sum())} days with decreasing physical holdings: "
                            f"{list(x.index[drops].date)[:5]}"))
    adds = x.pct_change()
    big = adds[adds > max_daily_add_pct]
    if len(big):
        issues.append(Issue("holdings_jump", "warn", f"{len(big)} days add >{max_daily_add_pct:.0%}"))
    return issues


def check_no_future_timestamps(df: pd.DataFrame) -> list[Issue]:
    """available_at must be <= next_tradable open used for execution; and no
    observation may carry an available_at earlier than its observation date."""
    issues: list[Issue] = []
    if {"signal_available_at", "next_tradable_at"} <= set(df.columns):
        bad = df.dropna(subset=["signal_available_at", "next_tradable_at"])
        n = int((bad["signal_available_at"] > bad["next_tradable_at"]).sum())
        if n:
            issues.append(Issue("future_leak", "fatal",
                                f"{n} rows have signal_available_at AFTER assumed execution time"))
    if {"date", "signal_available_at"} <= set(df.columns):
        sub = df.dropna(subset=["signal_available_at"])
        early = int((pd.to_datetime(sub["signal_available_at"]).dt.tz_localize(None)
                     < pd.to_datetime(sub["date"])).sum())
        if early:
            issues.append(Issue("premature_availability", "fatal",
                                f"{early} rows available before their observation date"))
    return issues


def check_calendar(df: pd.DataFrame, max_gap_days: int = 6) -> list[Issue]:
    d = pd.to_datetime(df["date"]).sort_values()
    gaps = d.diff().dt.days
    big = gaps[gaps > max_gap_days]
    return [Issue("calendar_gaps", "warn",
                  f"{len(big)} gaps > {max_gap_days} calendar days (holidays/halts?): "
                  f"{list(d[big.index].dt.date)[:5]}")] if len(big) else []


def run_price_checks(name: str, df: pd.DataFrame) -> list[Issue]:
    issues = []
    issues += check_duplicates(df, ["date"])
    if "close" in df:
        px = df.set_index("date")["close"]
        issues += check_stale_prices(px)
        issues += check_price_jumps(px)
    issues += check_calendar(df)
    return [Issue(f"{name}:{i.check}", i.severity, i.detail) for i in issues]
