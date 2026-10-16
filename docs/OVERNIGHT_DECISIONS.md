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
13. **Post-freeze sensitivity** (`scripts/overnight_sensitivity.py`), requested after
    publication, none of it changes the frozen rule: lookback 1–48m × top-K 1–15 grid,
    ranking-score variants, lookback blending, random-selection MC (500), random 70%
    universe MC (300), random 1y/2y windows (1,000 each), block bootstrap (5,000),
    vol history + 20% vol target, VIX sizing (15/VIX, VIX known 2 days before), SPY/GDX
    hedges. Selection refactored into `month_scores` + `members_from_scores`. Frozen
    outputs verified identical after the refactor.
14. **Overlays that helped in all three periods:** 15/VIX sizing (max 1x) and a
    beta-neutral long-SPY hold. Both were found after OOS was known, so they're
    recommended for paper trading, not claimed as validated.
15. **MOO/MOC check** on 20 days of Yahoo 1-minute bars (2026-09-17..10-14): the daily
    open equals the first print exactly, and the first-minute move is 14–28 bp in the
    miner ETFs, so auction execution is required. Closing-auction volume could not be
    measured (Yahoo 1-minute volume doesn't reconcile with daily volume), so the 4%-of-ADV
    auction assumption stays unverified.
16. **Realistic post-cost run** (`scripts/overnight_postcost.py`): per-share IBKR-style
    fees with a $0.35 minimum, SEC fee on sales and short sales, 1 bp auction slippage,
    optional sqrt impact, at $25k/$100k/$300k. Result: the pre-2024 edge only survives
    without impact (fees only); 2024–26 survives up to ~$100k (~$300k with ADV ≥ $20M).
    README headline changed accordingly: the flat-1.5 bp numbers are no longer the
    headline.
17. **Auction prices, second source.** Nasdaq.com official daily open/close
    (`scripts/overnight_auction_prices.py`) matches Yahoo to the cent on 96–100% of days
    for 13 of 15 held ETFs since Oct 2016, with 95% of the remaining gaps under 1 bp.
    Exceptions: NLR closes pre-2024 (64–73% identical) and GDX opens 2024–26 (87%). True
    auction-flagged prints need tick data with trade conditions (not available free
    without an account); flagged as a remaining gap.
18. **Out-of-universe test** (`scripts/overnight_universe_ext.py`, config
    `universe_extension`): 25 commodity ETFs never used in the study. The effect is
    present in 22 of 25 (strongest in junior miners and the Sprott physical trusts), but
    adding them to the ranking hurts both before and after costs, because the thin new names
    crowd out liquid ones. The universe stays at 36. PSLV/PHYS/URNJ/NUKZ/COPJ are on a watch list.
19. **Real auction prints** (`scripts/overnight_auction_ticks.py`): NYSE's free TAQ
    sample files (NYSE Arca trades, 2026-07-01 and 07-02), streamed and filtered to 64
    ETFs. Opening prints (cond `O`) and closing prints (cond `6`) equal the official
    open/close (median 0.0 bp). Auctions are ~1.1% of consolidated daily volume each
    (median), not the 4% assumed, so `auction_share_of_adv` changed 0.08 → 0.022 and every
    impact-based result was rerun. Capacity falls to ~$10–50k (~$100k with ADV ≥ $20M), and
    long-only beats long/short once impact counts, so README ranks it #1. One awk-streamed
    chunk was truncated (gzip EOF), so both days were refetched with the Python downloader
    (July 1 count identical, July 2 complete). Only 2 days, and July 2 preceded a holiday.
