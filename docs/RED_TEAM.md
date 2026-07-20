# RED TEAM REVIEW — adversarial quantitative audit

Date: 2026-07-20. Reviewer mandate: assume the authors fooled themselves; try to
disprove the repository's findings, especially the headline `G_sput_yca` result
(dev net Sharpe ~1.9 / WF-OOS 1.54, one-shot holdout 1.14, verdict CONDITIONAL
NO-GO). Everything below was verified against **code and recomputation**, not
docs. All numbers in this file were independently re-derived by running the
repo's own modules; the baseline reproduced exactly (dev 1.89, holdout 1.14,
full 1.71).

---

## A. Attacks that FAILED (things that check out)

These are reported first because a red team that only lists complaints is not
credible. Each of the following was an explicit attempt to break the result.

### A1. Timing / lookahead in family_G — NO LOOKAHEAD FOUND
- **Engine** (`src/sput_research/backtest/engine.py:77-82`): position from
  signal date *t* is shifted onto each leg's **own** calendar and first earns
  P&L on the intraday leg of the next session; the overnight gap into the fill
  day accrues to the *old* position. Same-close fills are structurally
  impossible. The 11 unit tests (incl. a contaminated fixture) pass.
- **Cross-calendar check**: the YCA leg's target positions are indexed by TSX
  signal dates and reindexed onto the LSE calendar (`families.py:155`). A TSX
  close at 16:00 ET (21:00 UTC) always precedes the next LSE open (07:00 UTC
  next day). Empirically verified: **0 of 215** executed YCA position changes
  derive from a source date that is not strictly prior to the fill date. TSX/LSE
  holiday mismatches produce at worst a one-day *hedge mismatch* (legs briefly
  unpaired), which hurts rather than helps.
- **Stale-price ffill attack**: `families.py:148` ffills YCA closes (limit=3)
  onto the TSX calendar for the *signal*. Recomputing the signal on **truly
  contemporaneous dates only** (both markets open, no ffill) gives dev 1.86 /
  holdout 1.16 vs baseline 1.89 / 1.14 — no change. Only 23/1250 signal dates
  are ffilled and only **2 of 112 entries** occur on TSX-only days. The traded
  leg always uses real LSE prices on real LSE dates, so "convergence at stale
  prices" cannot be monetized by construction. **Attack fails.**
- The 4.5h intraday asynchronicity (LSE 16:30 UK close vs TSX 16:00 ET close)
  can put noise *into the signal* but cannot inflate P&L, because fills are at
  genuine next-session opens which already impound any overnight catch-up. The
  +1-day-lag stress (holdout 0.62) bounds this effect.

### A2. Is the edge just direction/beta? — NO
- Static long-SPUT/short-YCA over the sample: Sharpe **0.07**. Exposure is
  balanced (276 long / 304 short signal days; mean position −0.02). Both
  directions of the YCA leg are profitable (long +0.85, short +0.40 cumulative
  net). Note the asymmetry finding in B5 below, but the edge is timing, not drift.

### A3. Data integrity — CLEAN
- **YCA.L (GBp)**: no 100× GBp/GBP mixups — close range 148.2p–744.5p over
  2018–2026, consistent with the known ~750p all-time high around Jan 2024
  (external spot-check via LSE/Hargreaves Lansdown listings). `dividends` sum =
  0 (Yellow Cake pays none — correct), `splits` = 0, `close == adj_close`
  everywhere. Largest daily move +13.3% (2021-09-13, the SPUT squeeze week —
  real). Feb-2022 (£62m) and later placings/buybacks are genuine market events
  requiring **no** price adjustment for an unadjusted-close backtest.
- **U-UN.TO**: no dividends/splits post 2021-07-26; the UPC conversion break is
  correctly excluded (DECISION_LOG #3) — this was independently confirmed as the
  right call.
- Sept-2021+ prices spot-checked plausible (U.UN C$33.00 on 2024-01-15 near the
  early-2024 uranium peak).

### A4. FX evaluation inconsistency — REAL, BUT DOES NOT FLATTER RESULTS
- Confirmed: the traded U.UN leg uses **raw CAD** prices (`families.py:154`)
  while the signal uses USD-converted; the YCA leg P&L is in USD terms. The
  summed return series is a CAD-return + USD-return hybrid that corresponds to
  no realizable single-currency portfolio, and the ±0.5 USDCAD exposure is
  ignored.
- Quantified: making both legs USD-consistent gives dev **1.97** / holdout
  **1.16** (vs 1.89/1.14) — i.e., the inconsistency slightly *understates*
  performance. Converting YCA at the *previous* day's FX close (removing the
  small same-day-FX marking effect on the overnight leg) gives dev 2.04 /
  holdout 1.09. Local-currency YCA P&L: dev 2.10 / holdout 0.94. **Conclusion:
  a genuine specification bug, immaterial and adverse-direction; fix for
  correctness, not because it manufactured the result.**

### A5. Statistical hygiene mostly sound
- Rolling stats are trailing-only; `min_periods` prevents seeded windows;
  walk-forward selection uses train-fold Sharpe only; the holdout slice is a
  chronological tail; the DSR is computed against the *pooled* trial variance
  (which includes deliberately bad families → very conservative benchmark).
- Placebos behave as they should for a real, correctly stamped signal
  (+5d shift ≈ 0; pre-information −1.07; reversed −2.85).

---

## B. FINDINGS AGAINST

### B1. MAJOR — Robustness stresses were only applied ONE AT A TIME; the edge does not survive them jointly
- Evidence (recomputed with the repo's own engine):

  | Stress | dev Sharpe | holdout Sharpe |
  |---|---|---|
  | base (1×) | 1.89 | 1.14 |
  | 2× costs only | 1.40 | 0.63 |
  | +1d lag only | 0.75 | 0.62 |
  | **2× costs AND +1d lag** | **0.27** | **0.13** |
  | 2× costs + 1d lag + 3× borrow | 0.24 | 0.08 |
  | 1.5× costs only | 1.64 | 0.89 |

- Why this matters: the three stressed assumptions are not alternatives — they
  are *independently plausible simultaneously* for the stated user (retail-ish
  account, no bid/ask history, no borrow history, non-colocated execution).
  Annual one-way turnover is **44× NAV** with a 1× cost drag of ~645 bps/yr
  (recomputed), so every 1 bp of one-way cost misestimate costs ~44 bp/yr.
  The YCA.L 15 bps assumed half-spread is an institutional SETS-book number;
  a retail/stressed effective half-spread of 30 bps (the "2×" case) is not a
  tail scenario, and one day of latency is ordinary for a paper/live retail loop.
- The FINAL_REPORT sentence "passes every … robustness gate (0.63 at doubled
  costs; 54% retention under one-day lag)" is technically true and practically
  misleading: the *joint* realistic-frictions case is a zero-Sharpe strategy.
- **Fix**: add a pre-registered joint stress (≥1.5× costs AND +1d lag AND ≥2×
  borrow) to the gates; report the stress *surface*, not slices.

### B2. MAJOR — The holdout result is not statistically distinguishable from zero
- The repo's own `psr` column in `holdout_results.csv` says it: PSR(SR>0) =
  **0.899** on 321 days → one-sided p ≈ **0.10**. Recomputed and confirmed
  (skew −0.21, kurtosis 3.26). The stationary-bootstrap 95% CI on the holdout
  slice is [0.24, 2.16] — nominally excluding 0, but the more moment-robust PSR
  does not reach 5%; the two methods disagree, which itself signals fragility at
  n≈321.
- **Selection at the holdout**: three families were evaluated on the holdout
  (A_long, A_longshort, G). G is essentially uncorrelated with the other two
  (holdout return correlations −0.02/−0.03), so a Bonferroni-style worst case
  puts the family-selection-adjusted p at ~0.3, and even the most charitable
  reading leaves p ≈ 0.10. A single ~15-month window with 26 entries simply
  cannot certify SR 1.14. The holdout Sharpe also fails to clear its own gate
  with confidence: the 0.75 `net_oos_sharpe_min` threshold is inside every CI.
- This *supports* the repo's pooled-DSR NO-GO — but contradicts the FINAL_REPORT
  framing "passes every … untouched-holdout gate": the gates test point
  estimates, not evidence strength.
- **Fix**: report holdout PSR/CI next to the point estimate in the leaderboard;
  gate on `psr >= 0.95`, not on the point Sharpe.

### B3. MAJOR — Capacity is overstated; "$1–5M" is not defensible, and the impact coefficient is 5–10× below standard
- Binding numbers (recomputed): YCA.L median dollar ADV ≈ **$5.8M** → 5%
  participation ≈ **$289k/day**. Every rebalance trades 0.5 × capital per leg.
  - At **$1M**: $500k YCA orders ≈ 1.7 days at the cap; **216 of 1281 days**
    violate participation (`capacity_results.csv`).
  - At **$5M**: $2.5M orders ≈ **8.7 days** to fill at the cap — longer than the
    strategy's ~5-day average holding period and close to its 10-day cap. The
    strategy literally cannot be established before it wants to exit.
- `scripts/run_capacity.py:57-59` caps Q at 5% ADV **for the impact charge
  only** and then credits the FULL position's P&L — unfilled remainder is free.
  That is why reported Sharpe "flattens" at 1.52 for $5M/$10M/$25M. Those rows
  are artifacts of the model, not capacity estimates.
- `impact_coefficient: 0.1` (config/costs.yaml) versus the square-root-law
  literature standard of ~0.5–1.0 × σ·√(Q/ADV). At a defensible 0.5–0.7, the
  reported $1M impact drag (210 bps/yr) becomes ~1,000–1,500 bps/yr — most of
  the strategy's ~15–19% CAGR.
- Also: U-UN ADV is computed on **CAD** dollar volume but compared against USD
  capital (`run_capacity.py` uses the unconverted leg frame) — a ~35%
  overstatement of that leg's capacity (not binding; YCA binds).
- **Fix**: model multi-day fills with signal-decay (the +5d placebo ≈ 0 shows
  the edge decays within a week — so unfilled remainder is nearly worthless),
  raise the impact coefficient to ≥0.5, and restate capacity. Realistic
  full-fidelity capacity is roughly **$0.3–0.6M** (one-day fills within 5% ADV),
  i.e., personal-account scale only. FINAL_REPORT §8's own prose ("anything
  beyond low-single-digit $M unrealistic") is closer to the truth than its
  headline range; the leaderboard's `capacity_sharpe_5m = 1.52` should be
  deleted or footnoted as unfillable.

### B4. MAJOR (process) — Pre-registration and "one-shot holdout" are unverifiable
- The working directory is **not a git repository**. File mtimes show
  `config/preregistered_parameters.yaml` and `go_no_go_thresholds.yaml` written
  ~15 minutes before `holdout_results.csv`, all on 2026-07-20, in one session.
  "Frozen BEFORE any performance run" is therefore an unfalsifiable claim, and
  the holdout script's rerun guard is a soft check (bypass flag exists at
  `run_holdout.py:29`; deleting the CSV suffices).
- Nothing in the numbers *suggests* the gates were tuned post hoc (the verdict
  is a NO-GO, after all, and the pooled DSR gate was left in place even though
  it kills the headline strategy). But an external reviewer cannot distinguish
  genuine pre-registration from retro-fitting. **Fix**: init git, commit the
  frozen configs, then run; or publish hashes/timestamps of configs before
  computing results.

### B5. MINOR — Headline framing and small errors
1. **"Dev Sharpe 1.89" is an in-sample number**: it is the modal parameter set
   re-evaluated over the same dev sample whose folds chose it. The honest dev
   figure is the stitched WF-OOS **1.54**. The plateau/LOO/top-5 statistics are
   likewise computed with dev-selected parameters (upward bias). Both numbers
   are in the tables, but prose should lead with 1.54.
2. **Trial-count discrepancy**: FINAL_REPORT §6/§7 and DECISION_LOG #11 say
   "432 grid points"; `trial_count.json` and the DSR computation actually used
   **648** (B_trend's grid is 216, not 72... the docs subtracted it). The
   computation is *more* conservative than documented; fix the text.
3. **Partial same-day bar**: `YCA.L.parquet` was retrieved 2026-07-20 11:13 UTC
   — mid-LSE-session — so its last row is an incomplete bar used as a close
   (affects only the final holdout day; U-UN ends 2026-07-17). Ingestion should
   drop the live session's bar.
4. **Leg P&L asymmetry worth disclosing**: ~83% of cumulative net P&L
   (0.95 of 1.14) comes from the **YCA side** of the pair; the short-SPUT side
   is a net loser (−0.07). The "relative premium reversion" story is really
   mostly "YCA mean-reverts against SPUT-defined fair value." This sharpens the
   borrow question (the profitable short is the *YCA* short) and suggests the
   effect could be tested directly on YCA vs NAV.
5. **FX cost asymmetry**: the YCA leg is charged 2.5 bps FX spread per side but
   a USD (or CAD) investor trading U-UN also faces conversion; immaterial at
   this precision.
6. **Uncharged financing**: `financing_spread_bps_annual: 50` is defined in
   costs.yaml but never applied by the engine. Immaterial (~≤5 bps/yr at these
   exposures) but the config implies it is modeled.

### B6. Borrow assumptions — UNVERIFIABLE, but not the kill shot
- 300/150 bps annual for U-UN/YCA cannot be verified from any free source (the
  config says so itself; searches for historical borrow on either name return
  nothing public). For a mid-cap LSE holding company and a squeeze-prone TSX
  trust, episodic hard-to-borrow (>10%) is plausible.
- Quantified: borrow ×10 (3,000/1,500 bps every day) → dev 1.57 / holdout 0.69;
  ×20 → dev 1.21 / holdout 0.19. Borrow *alone* does not kill the dev-sample
  edge because time-in-market is ~52% with balanced sides — but it interacts
  badly with the other frictions (see B1 kitchen-sink: 0.08). Also note B5.4:
  the profitable side *is* the YCA short, so "borrow becomes unavailable"
  removes most of the P&L, not half of it. The repo's flag
  ("borrow-assumption-dependent") is correct and should be promoted into the
  leaderboard's rejection-reason column for G.

### B7. Confirmed rejections (no rehabilitation warranted)
- **A_long**: the 1-day-lag failure is real (holdout 1.79 → 0.49; dev 1.12 →
  0.64) and the mechanism (trading the evening-published premium at next open,
  edge gone a day later) is exactly the stale-signal profile the gate exists
  for. REJECT stands.
- **F_crossline**: −2.36 net WF Sharpe reproduced in the tables; the spread
  never exceeds round-trip costs. REJECT stands.
- **B_trend** (2 trades) and **H** (no plateau): correctly rejected.

---

## C. VERDICT

**The repository's bottom-line conclusion — CONDITIONAL NO-GO, do not deploy —
stands, and this review strengthens it.** The result is *not* an artifact of
lookahead, calendar bugs, stale-price marking, FX mishandling, corporate-action
errors, or bad Yahoo data: all of those attacks failed quantitatively. What
remains is an economically plausible, honestly-measured pattern whose evidence
is simply too thin and too friction-sensitive to act on.

Conclusions that STAND:
1. No lookahead/timing leakage in the engine or family_G (verified empirically).
2. Data integrity of the YCA.L/U-UN.TO series over the sample (verified,
   including external spot-checks).
3. The pooled deflated-Sharpe NO-GO — reinforced by holdout PSR p ≈ 0.10 and
   3-way holdout selection.
4. All six rejections (A_long, A_longshort, B, F, H×2).
5. The mechanism-level negatives: the SPUT discount is not arbitrage; the
   U.UN/U.U cross-line spread is untradeable.

Conclusions that need REVISION:
1. **"Survives 2× costs and +1d lag"** → must be restated: it survives each
   *individually*; jointly (2× costs + 1d lag) the holdout Sharpe is **0.13**
   and dev is **0.27**. For a retail-scale, borrow-dependent, 44×-turnover
   strategy, the joint case is the realistic case.
2. **Capacity "$1–5M"** → revise to **≈$0.3–0.6M** (one-day fills within 5% of
   YCA ADV; impact coefficient ≥0.5; no credit for unfillable size). Remove or
   footnote the flat capacity_sharpe rows above $1M.
3. **"Passes all holdout gates"** → add that the holdout point estimate is not
   significant at 5% (PSR 0.90) and three families consumed the holdout.
4. **Dev headline 1.89** → lead with WF-OOS 1.54; label 1.89 as in-sample-refit.
5. **Pair story** → disclose that ~83% of P&L is the YCA leg, so the strategy
   is effectively a YCA-vs-SPUT-anchor reversion trade whose profitable side
   requires YCA borrow.
6. Fix the documentation errors: 432 vs 648 trials; partial same-day YCA bar;
   uncharged financing line; CAD/USD ADV mismatch in capacity.

Net assessment: even "promising — paper-trade" is generous unless the paper
track is run at realistic joint frictions and personal-account size. As a
research artifact demonstrating that the null survives, the repository is
sound; as support for deploying capital, it provides none — which is,
creditably, what it concludes.
