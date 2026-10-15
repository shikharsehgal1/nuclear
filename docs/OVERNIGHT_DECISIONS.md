# Overnight study: decision log

## 2026-10-15

1. **Origin (disclosed).** An exploratory sweep on KIBOT 5-min bars (11 ETFs, 2016–23)
   tested trend, intraday momentum, EIA windows, pairs, roll seasonality and 5-min
   lead-lag. All failed after costs except the overnight/intraday split. Per-ticker
   2024–26 stats for ~25 ETFs (incl. URA/URNM/COPX) were then looked at **once**, before
   any rule existed. That glimpse is why 2010–15 (never looked at) is the cleanest test.
2. **Data.** Yahoo daily OHLC (auto_adjust off), 2009–2026-10-14. The open is scaled by
   AdjClose/Close so dividends land in the overnight leg. Stale bars (O=H=L=C), zero volume
   and |overnight| > 30% are invalidated, and so is the next overnight. Cross-check against
   KIBOT 5-min first-trade opens: corr 0.994–0.999, means within ~2–3%/yr.
3. **Spread model.** The Abdi–Ranaldo daily estimator gave GLD ≈ 30 bp half-spread and
   was rejected. 1-minute Corwin–Schultz went to zero on thin names (single-print bars)
   and was also rejected. Replaced with a tiered $ADV table (config), checked against
   1-minute high-low ranges as an upper bound. The headline uses auction costs, which
   don't depend on the spread.
4. **Pre-registration.** Universe, periods, grid (lookback 12/24/36 × K 3/5/8 × ON/LS) and
   costs were written to `config/overnight.yaml` before any backtest.
5. **Discovery grid.** Every auction-cost cell had positive Sharpe (0.7–1.4). Every
   spread-cost cell was negative. Picked **24 months / K=5**, the centre of the plateau,
   not the best cell (12/3).
6. **Improvements tested on discovery only:** up-day filter (+), down-day filter (control,
   −), skip weekends (≈0), leverage-free up-day renormalisation (kept).
7. **Bug caught.** The first up-day backtest aligned the signal with the same date's
   overnight return. `on[t]` is the night *ending* at t's open, so that used the session
   after the night = lookahead. Fixed with `id.shift(1)` and a poisoned-fixture test
   (`test_up_day_signal_uses_previous_session`). The corrected discovery result was
   stronger (ON 1.82 → 2.08), so the bug was not flattering the result, but the earlier
   number was wrong.
8. **Freeze.** The `final:` block in config was written before any pre-sample or OOS run.
9. **Signal timing.** In production, MOC orders have to go in before the close. KIBOT
   check: the open→15:45 sign agrees with the open→close sign ~95% of the time, and the
   overnight gap after up vs down days survives.
10. **Pre-sample / OOS first run after the freeze** (later reruns for figure fixes
    reproduced identical numbers). Long-only variants failed the pre-sample (≈0). LS
    passed all three periods, so up-day LS is the headline. Up-day ON is reported as
    regime-dependent.
11. **Post-hoc, labelled as such:** ADV ≥ $20M capacity variant, and the hourly
    exit-timing check (2023-11 on, overlaps OOS). Neither changed the frozen rule.
12. **Trial count for DSR:** 200 (36 grid runs = 9 cells × ON/LS × 2 cost models, 8
    improvement tests, ~150 exploratory configs in the original sweep), rounded up.
