# FINAL REPORT — Systematic NAV/spot dislocation research: Sprott Physical Uranium Trust

Date: 2026-07-20. Sample: 2021-07-26 → 2026-07-17 (1,250 SPUT trading days;
final ~25% untouched holdout). All results **net of costs** unless stated.

## 1. Executive conclusion

**The null hypothesis largely survives.** Of seven pre-registered strategy
families tested end-to-end, six are rejected. One — a SPUT-vs-Yellow-Cake
relative-value pair (G) — passes each individual economic, robustness and
untouched-holdout gate (walk-forward OOS net Sharpe 1.54; holdout 1.14; 0.63
at doubled costs; 54% retention under one-day execution lag; no parameter
island; no outlier dependence), but three findings, two surfaced by the
independent red team, are collectively decisive:

1. **Individually-passed stresses are jointly fatal**: 2× costs AND +1-day lag
   together collapse the holdout Sharpe to **0.13** (0.27 dev; ~0.08 adding a
   borrow shock). The strategy turns over ~44× per year one-way (~645 bps/yr
   base cost drag), so it lives or dies on fill quality.
2. It **fails the pre-registered pooled deflated-Sharpe gate** (0.08 vs 0.90
   required across all 648 logged trials), and the holdout alone is not
   statistically distinguishable from zero (PSR 0.90, p≈0.10 before adjusting
   for three families reaching the holdout; ~0.3 after).
3. **Realistic capacity is ~$0.3–0.6M**, bounded by Yellow Cake's LSE
   liquidity once impact is charged on full intended size rather than only
   the participation-capped portion.

> **Verdict: CONDITIONAL NO-GO — "promising but requires better data and a
> live paper track."** Paper-trade per `docs/LIVE_SPEC.md`; do not deploy
> capital. Five years of post-conversion history is too short to certify an
> edge of this size against the multiple-testing burden this project itself
> created, and the economics only work at personal-account scale with
> near-perfect execution.

The headline negative results are as valuable: the persistent SPUT discount is
**not arbitrage and not reliably tradeable on its own**, and the U.UN/U.U
cross-currency line "arbitrage" is decisively untradeable (net Sharpe −2.4).

## 2. Instrument mechanics (full detail: docs/MECHANICS.md)

- U.UN/U.U are one unit class on two TSX currency lines (single CUSIP;
  journaling via broker). SRUUF is an unsponsored OTC quotation.
- **No redemption of any kind** — the OSC decision states unitholders cannot
  redeem for cash or physical. Unlike PHYS/PSLV (monthly cash redemption at a
  haircut), SPUT has **no contractual discount floor**.
- NAV: daily, 16:00 Toronto, computed by RBC IS, published same evening (USD).
- ATM issuance only at ≥100% of most recently calculated NAV (NI 81-102);
  proceeds buy uranium (1.0% manager commission); management fee 0.35%.
- CME UX futures: financially settled vs UxC, open interest ≈ 0 — not a
  usable hedge leg. MX options on U.UN listed only 2025-09 — no usable history.
- UPC→SPUT conversion (2021-07-19, 0.5 units/share) is a hard regime break;
  Yahoo carries the predecessor price series UNADJUSTED across it (a fake
  +118% jump) — predecessor data excluded.

## 3. Why the apparent spread is not arbitrage

With no redemption/tender/buyback channel, nothing forces price → NAV from
below. The ATM compresses **premiums** only (issuance at ≥ NAV). Empirically:
premium episodes half-life ≈ 1.8 days vs 4.5 days for discounts, and 54% of
all pounds ever acquired were bought on days following a premium (premium days
are only 15% of the sample). Uranium "spot" itself is an assessed price from
brokered off-market transactions (UxC/TradeTech) — not executable — so the
NAV leg of the "spread" cannot be traded at all. Discounts of −10% to −19%
persisted for months in 2022–2025. Any discount strategy is a statistical
convergence bet carrying uranium beta, not arbitrage.

## 4. Data (full detail: docs/DATA_INVENTORY.md, DATA_ENDPOINTS.md)

Recovered free point-in-time-usable history: Sprott daily NAV/price/premium
(inception→2026-07-17, verified to ≤6bp against independent price/NAV
reconstruction), weekly holdings, all 256 purchase events; Numerco daily spot
2007→; Cameco monthly assessments 1988→. Key gaps, all load-bearing for
interpretation: **no units-outstanding history** (level-based synthetic NAV
replaced by returns-space nowcasting), **no bid/ask history** (spreads
estimated, stressed 0.5–3×), **no borrow-rate history** (short legs flagged),
no licensed UxC/TradeTech point-in-time series, no usable options history.

A material timestamp finding: Numerco's as-dated series **lags** the
assessment embedded in Sprott's NAV — corr(NAV_t, Numerco_{t+1}) = 0.84 vs
0.55 same-day. Naively treating as-dated "spot" as leading NAV would
manufacture a spurious signal; family D was specified to avoid this.

## 5. Point-in-time methodology

Every close-derived signal is tradeable no earlier than the **next session's
open**; the engine decomposes daily P&L into an overnight leg at the old
position and an intraday leg at the new position, making same-close fills
structurally impossible (unit-tested, including a deliberately contaminated
fixture that the leakage checks must catch). NAV published in the evening is
used for next-open trades in the base case and lagged one extra day in a
mandatory stress. Costs: commission + estimated half-spread + FX spread +
borrow + square-root impact.

## 6. Hypotheses and results (pre-registered in docs/HYPOTHESES.md; grids and gates frozen before any performance run)

| Family | Mechanism | WF-OOS SR | Holdout SR | Verdict |
|---|---|---|---|---|
| G SPUT vs Yellow Cake RV | two closed-end physical-U holders' relative premium mean-reverts | 1.54 (100% folds+) | **1.14** (2×costs 0.63, lag1 0.62) | **CONDITIONAL NO-GO** (pooled DSR 0.08; capacity) |
| A_long discount reversion | flow-driven discount extremes partially revert | 0.93 | 1.79 **but lag1 0.49 (27% retention — gate ≥50%)** | REJECT (execution-timing dependence; top-5 trades 53% of PnL) |
| A_longshort | two-sided reversion | 0.51 | 0.98, lag1 −0.68 | REJECT (lag; unverified borrow; 63% single-year PnL) |
| B trend-gated discount | avoid falling knives | 0.50 (11% folds+) | — | REJECT (2 trades; island) |
| H hedged residual | SPUT-specific residual vs URNM beta | 0.36 | — | REJECT (neighbor Sharpe −0.40) |
| F cross-line U.UN/U.U | same-trust parity | **−2.36** | — | REJECT (never exceeds round-trip costs — NOT arbitrage) |
| D stale-NAV lead-lag | price impounds news before NAV | diagnostic | — | Mechanism CONFIRMED, not independently tradeable: premium t-stat 3.5 predicting next-day NAV change; discount partly anticipates NAV declines |
| C falling-knife decomposition | — | diagnostic | — | Widening is price-driven (−3.9% price vs +0.3% NAV); convergence ≈ 2/3 price recovery, 1/3 NAV decline |
| E ATM/premium asymmetry | issuance caps premiums | diagnostic | — | CONFIRMED (half-lives 1.8d vs 4.5d; acquisition asymmetry above) |
| I cross-vehicle factor | discount reversion generalizes | +0.42 PHYS, +0.40 YCA, −0.22 PSLV, −0.09 CEF | — | NOT robust — factor does not generalize; treated as evidence against A |
| J options | — | — | — | DEFERRED — no data (MX options listed 2025-09) |

Failed specifications were preserved, not tuned: 648 grid-point evaluations
logged (reports/tables/trial_count.json, combo_sharpes.json) and used to
deflate reported Sharpes.

## 7. Statistical validation (survivor: G)

- Walk-forward (expanding, quarterly folds, 5-day embargo): 100% positive folds.
- Untouched holdout (final 313–321 days, evaluated exactly once, script-enforced):
  net Sharpe 1.14, max DD −4.9%.
- Stationary block-bootstrap 95% CI on dev Sharpe: [1.33, 2.46].
- Placebos: +5d-shifted signal ≈ 0 (−0.06); trading before information existed
  −1.07; reversed signal −2.85. All as expected for a real, correctly-stamped signal.
- Parameter plateau: all ±1-step neighbors ≥ 1.35. Leave-one-year-out ≥ 1.74.
- Concentration: top-5 trades = 18% of PnL (81 trades); worst single year still
  positive; removing the best 5 trades leaves SR 1.51.
- **Deflated Sharpe: 0.08 pooled** (all 648 trials, registered accounting) vs
  0.99 family-level. The registered figure governs. With ~5y of data and a
  cross-family trial variance inflated by intentionally-tested bad families,
  the pooled DSR is extremely conservative — but relaxing it post hoc is
  exactly the failure mode this project was designed to prevent.
- **Joint stresses (red team):** 2× costs + 1-day lag together → holdout 0.13,
  dev 0.27; adding a 3× borrow shock → ~0.08. Stresses were originally
  reported one-at-a-time; the joint case is the realistic retail case.
- **Holdout significance (red team):** PSR on the 321-day holdout = 0.90
  (p ≈ 0.10); three families reached the holdout, so the selection-adjusted
  p is ~0.3. The holdout is supportive, not conclusive.

## 8. Capacity and impact

Binding constraint: YCA.L median ADV ≈ $5.8M → 5% participation ≈ $289k/day
per leg. At $1M capital, 17% of trade days exceed the cap; at $5M, fills take
~8.7 days against a ~5-day median holding period — the trade is over before
the position is on. The original impact model charged impact only on the
capped quantity while crediting full P&L (which is why modeled Sharpe
artificially "flattens" at 1.52 above $5M) and used an impact coefficient
5–10× below literature estimates; the red team's corrected reading puts
**realistic capacity at ~$0.3–0.6M**. Viable only for personal capital;
irrelevant at fund scale.

## 9. Explainability (why might G persist?)

SPUT (TSX, retail+institutional flow, ATM supply valve, no redemption) and
Yellow Cake (LSE, buyback-prone, periodic NAV disclosure) hold the same asset
with different investor bases, disclosure rhythms and supply mechanics. Their
relative premium wanders on flow segmentation and cannot be closed by any
arbitrage channel (neither vehicle is redeemable; borrow in both is scarce),
which is precisely why a small, slow reversion edge could persist for small
capital. It should fail when: either vehicle changes its capital-return policy
(YCA tender/buyback regime shifts), uranium enters a squeeze where the pair's
premia decouple structurally (2021Q3-style), or borrow becomes unavailable.

## 10. Red-team findings

Full review: docs/RED_TEAM.md (independent adversarial pass; all numbers
independently recomputed — baseline reproduced exactly).

**Attacks that failed** (conclusions that stand): no lookahead across the
TSX/LSE calendar mismatch (0 of 215 YCA fills use non-prior information);
stale-price forward-fill does not drive the edge (contemporaneous-only signal:
dev 1.86 / holdout 1.16 vs 1.89 / 1.14); no GBp/GBP 100× data corruption; no
splits/dividends missed; not uranium beta (static long-SPUT/short-YCA Sharpe
0.07); an FX-consistency wart in the traded CAD leg is real but *adverse* —
fixing it raises Sharpe to 1.97/1.16, so reported numbers are conservative.

**Findings accepted and applied** (sections 1, 7, 8): joint-stress collapse;
holdout statistical thinness; capacity revised down to ~$0.3–0.6M; headline
restated as WF-OOS 1.54 rather than in-sample-refit 1.89; trial count
corrected to 648; ~83% of G's PnL comes from the YCA (borrow-dependent) leg —
reinforcing the borrow-verification requirement in LIVE_SPEC.

**One factual correction to the review:** it states the project has no git
history; the repository has had version control with staged commits throughout.
The substantive point behind it — that pre-registration and holdout evaluation
occurred within one working session by one author, so "frozen before results"
rests on same-day commit timestamps rather than independent attestation — is
accepted and disclosed here.

## 10b. Addendum — live-market verification (2026-07-20, regular session)

Real quotes and borrow were captured live (data/raw/live_quotes/) and the
surviving strategy re-run with measured instead of assumed costs
(reports/tables/real_cost_scenarios.csv):

| Input | Assumed | Measured (settled book, 10:03 ET) |
|---|---|---|
| U.UN half-spread | 7.5 bps | **5.8 bps** (3¢ on C$25.72) |
| U.U half-spread | 12.5 bps | 2.7 bps |
| YCA.L half-spread | 15 bps | 5–14 bps (intraday range) |
| U.UN short borrow | 300 bps | **277 bps** (SRUUF, IBKR; 1y mean 242, max 348) |
| YCA short borrow fee | 150 bps | **68 bps** (YLLXF; 1y mean 46, max 114) |
| YCA short availability | assumed available | **fragile: 1y min 1,000 shares, median 100k (OTC line)** |

G_sput_yca at measured costs: dev 1.97 / holdout **1.24** net Sharpe
(~23%/yr on deployed notional); 2× measured costs → holdout 0.81; 1-day lag →
0.71; joint 2×+lag worst case → **0.30–0.40** (vs 0.13 under the old, more
punitive assumptions). The red team's joint-stress collapse was thus partly an
artifact of conservative cost assumptions — the measured-cost joint stress is
thin but positive. Cost assumptions are hereby validated; the remaining open
risks are **statistical thinness** (holdout p≈0.10 unadjusted, ~0.3
selection-adjusted; pooled DSR gate still failed) and **YCA short
availability**, which retail-accessible channels cannot guarantee.

Options landscape (same session): U.UN has a real Montréal Exchange chain
(root "U", CAD line only) — 13 expiries to Jun-2027, 29,247 total OI
(~C$75M notional), 318/322 lines two-sided, ATM IV 35.2% vs 27.6% realized
(rich), slight call skew (36.2 vs 34.1), but bid-ask ≈ 10–33% of premium —
viable for bounded-risk hedging, not for spread-sensitive vol strategies.
No options exist on U.U, SRUUF, YCA (any venue), or meaningfully on PHYS;
CCJ options are deep (LEAPs to 2028); URNM/URA moderate.

## 11. What additional data would raise confidence

1. Licensed UxC/TradeTech point-in-time assessments (true NAV input).
2. Units outstanding / total NAV history (Wayback backfill or Sprott IR).
3. Historical bid/ask and borrow (prime broker) for U.UN and YCA.L — the
   single biggest unverified cost assumption.
4. MX options quotes for U.UN (family J).
5. Simply: more time. At the observed edge size, ~3+ further years of live
   or paper track are needed before the pooled-DSR gate could plausibly clear.

## 12. Final decision

- **G_sput_yca: CONDITIONAL NO-GO** — paper-trade per docs/LIVE_SPEC.md,
  re-evaluate against the same frozen thresholds after ≥12 months.
- All other families: REJECT (reasons in reports/strategy_leaderboard.csv).
- Overall project conclusion, in the pre-registered taxonomy: **"promising but
  requires better data"** for G; **"discount convergence is not reliably
  tradeable"** for the SPUT-only families; **"no statistically credible
  strategy found"** at institutional capacity.
