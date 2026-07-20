# Pre-registered strategy hypotheses

Frozen 2026-07-20, before any strategy performance was computed on real data.
Descriptive statistics (premium distribution, autocorrelation) were permitted
before freezing; conditional forward-return analysis and backtests were not.

Null hypothesis for every family: apparent premium/discount or spot-relative
alpha disappears after correcting for stale NAVs, publication timing, trading
costs, short availability, market impact, parameter selection and multiple
testing.

Data-driven scope note: with only free/public data, hypotheses D (partially),
F, G, H, I are testable end-to-end; A–C are testable using Sprott's published
NAV history; E is testable if units-outstanding history was recovered from
Sprott's endpoints; J (options) is NOT testable (no free options history for
U.UN) and is deferred with an explicit data requirement.

Common execution assumptions (all families):
- Signals computed from information available at/after the relevant close and
  assumed published before the NEXT open (Sprott NAV is posted in the evening;
  conservative variant adds one full extra day of lag).
- Fills at next TSX open (or NYSE open for US-listed legs). No same-close fills.
- Costs per `config/costs.yaml`; shorts flagged as borrow-assumption-dependent.
- Sample: 2021-07-26 onward. Final 25% chronological holdout untouched.

---

## H-A: Premium/discount mean reversion

- **Mechanism:** SPUT cannot be redeemed at NAV; discounts reflect risk appetite
  of a retail/fund flow-driven holder base. Extremes driven by flow rather than
  information should partially revert as flows normalize. Because no arbitrage
  channel exists, reversion should be slow, noisy and regime-dependent — this is
  a statistical convergence trade, NOT arbitrage.
- **Signal:** premium = close / published_NAV(same currency) − 1, using the NAV
  published for that valuation day. Variants: raw level, rolling z-score
  (windows per pre-registered grid), rolling percentile, expanding median gap.
- **Signal timestamp:** NAV valuation 16:00 Toronto, published same evening →
  tradeable next open.
- **Instrument:** U.UN (CAD line, most liquid).
- **Direction:** long-only variant (buy deep discount); long/short variant
  (short extreme premium) reported separately with borrow caveats.
- **Entry:** z ≤ −entry_z (discount wide). **Exit:** z ≥ −exit_z or holding cap.
- **Expected return source:** discount narrowing; **risk:** uranium beta while
  holding, discount widening further.
- **Falsification:** conditional forward returns not monotone in discount
  decile; or reversion attributable entirely to NAV falling rather than price
  rising (checked via H-D decomposition); or net Sharpe < 0 after costs.

## H-B: Trend-conditioned discount

- **Mechanism:** discounts during uranium downtrends are compensation for
  falling NAV (catching knives); discounts during flat/up markets are flow
  noise. Conditioning on NAV/spot trend separates the two.
- **Signal:** H-A entry only when published NAV > its trend_window SMA (grid).
- **Falsification:** no improvement over unconditional H-A out-of-sample.

## H-C: Falling-knife decomposition (diagnostic, feeds A/B)

- Classify discount-widening days by driver: (i) price down, NAV flat = panic;
  (ii) NAV down, price sticky = valuation lag; (iii) both = beta.
  Measure which component converges (price rises vs NAV falls). Primarily a
  diagnostic; its output disciplines interpretation of A/B rather than being
  its own tradeable rule.

## H-D: Stale NAV and price discovery

- **Mechanism:** NAV inputs (assessed uranium spot) update sluggishly; SPUT's
  market price impounds uranium news first. Apparent "discounts" may predict
  NAV falling (not price rising). Test lead-lag: SPUT return, URNM/URA/CCJ
  returns, futures where available → next published NAV change. Then re-run
  H-A replacing published NAV with synthetic live NAV (holdings × best
  contemporaneous uranium value + cash) and see if the signal survives.
- **Falsification:** if H-A's edge disappears under synthetic NAV, the
  "discount" was stale-NAV artifact, not opportunity.

## H-E: ATM issuance and premium compression

- **Mechanism:** at premium > issuance-friction threshold, Sprott sells units
  via ATM (supply) and buys uranium (demand for the underlying) — compressing
  the premium and supporting NAV. Premiums should be self-limiting in a way
  discounts are not (asymmetry).
- **Signals:** premium level; Δunits_outstanding (published with lag — use only
  after publication); days since last issuance; issuance/ADV.
- **Trades:** short-premium variant (borrow-dependent); long-uranium-proxy
  variant. Also purely descriptive asymmetry test: premium half-life ≪ discount
  half-life.
- **Falsification:** no issuance→compression link, or untradeable after costs.

## H-F: Cross-currency line dislocation (U.UN vs U.U)

- **Mechanism:** same units, two trading lines, CAD vs USD; retail order flow
  segmentation can push the FX-adjusted line prices apart; convergence via
  journaling (operationally slow) or market-making. Likely small and
  cost-bounded — the test is whether deviations exceed round-trip costs.
- **Signal:** spread = ln(P_U.UN) − ln(P_U.U × USDCAD) at matching TSX closes.
- **Trade:** buy cheap line / short rich line (borrow-dependent) or
  switch-timing for an existing holder (cost-free rebalance alpha).
- **Falsification:** |spread| rarely exceeds modeled round-trip cost
  (two half-spreads on thin lines + FX + borrow); label NOT ARBITRAGE if legs
  cannot both be executed at observed closes.

## H-G: SPUT vs Yellow Cake relative value

- **Mechanism:** two closed-end physical uranium holders listed on different
  exchanges with different investor bases; their premia to their own NAVs
  should co-move; relative dislocations mean-revert. YCA NAV is only published
  periodically (monthly/quarterly RNS) → use holdings×spot synthetic NAV for
  both, or trade the price ratio's z-score directly (documented as proxy).
- **Signal:** z-score of ln(U.UN_USD / YCA_USD) vs rolling window (grid).
- **Risks:** GBP FX, non-overlapping hours (LSE close ≠ TSX close — execution
  uses next joint session), YCA buybacks, structurally different fee/liquidity.
- **Falsification:** ratio non-stationary (no cointegration evidence), or edge
  < costs, or hedge ratio unstable.

## H-H: SPUT vs uranium-equity hedge basket (residual premium trade)

- **Mechanism:** isolate SPUT-specific premium/discount moves from uranium
  beta by hedging with URNM (purest liquid proxy). Trade the residual only.
- **Signal:** rolling beta (>=120d) of SPUT on URNM; residual z-score.
- **Trade variants:** unhedged (=H-A), beta-hedged, dollar-neutral.
- **Falsification:** residual has no mean reversion, or hedged variant's
  Sharpe ≤ unhedged (hedge adds cost, not signal), or hedge ratio unstable.

## H-I: Cross-vehicle discount factor (external validity)

- **Mechanism:** if discount mean-reversion is a real closed-end-fund flow
  phenomenon, the SAME rule (same grid point) should work directionally on
  PHYS/PSLV/CEF/SPPP (which have redemption features and tighter discounts —
  expect weaker but same-signed effect) and YCA. Leave-one-vehicle-out: a rule
  fitted only on SPUT that fails everywhere else is suspect.
- **Note:** PHYS/PSLV NAV history via synthetic NAV from GLD/SLV-implied metal
  prices (documented proxy) unless published NAV series found.
- **Falsification:** sign flips across vehicles.

## H-J: Options (DEFERRED — data unavailable)

- No free historical options quotes/OI for U.UN (Montréal Exchange data is
  paid). Requirement documented in FINAL_REPORT "additional data needed".

---

Trial accounting starts at zero; every (family × grid point) evaluated on real
data increments the count used for deflated-Sharpe computation.
