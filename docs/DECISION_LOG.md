# Decision log

## 2026-07-20

1. **Repository bootstrapped** (`uv`, Python 3.12, src layout). One-command
   reproduction target: `make research`.
2. **Yahoo Finance chosen as the free market-data backbone** (Tier 3). No
   bid/ask history exists in free data → spreads are ESTIMATED (config/costs.yaml
   floors + vol/volume-based estimates), stress-tested at 0.5–3×. Conclusions
   sensitive to spread assumptions are labeled as such.
3. **UPC predecessor data EXCLUDED.** Yahoo attaches Uranium Participation Corp
   history to U-UN.TO back to 2006 with NO adjustment for the 2021 conversion
   exchange ratio (close C$5.11 on 2021-07-16 → open C$11.43 on 2021-07-26,
   zero-volume placeholder bars in between; no split factor recorded). Using it
   would inject a fake +118% return. UPC also had no ATM program, held UF6, and
   no free point-in-time NAV history was found. Sample therefore starts
   **2021-07-26**. Consequence: ~5.0y of data; overfitting protections tightened
   (small grids, 25% holdout, DSR trial accounting).
4. **Pre-registration completed before any performance run**: HYPOTHESES.md,
   preregistered_parameters.yaml, go_no_go_thresholds.yaml frozen.
5. **NAV availability convention:** NAV valued 16:00 Toronto, published that
   evening (to be confirmed in MECHANICS.md). Base case: usable for next-open
   fills. Robustness: +1 day lag mandatory for all headline strategies.
6. **Options family (H-J) deferred** — no free U.UN options history (Montréal
   Exchange data is licensed). Recorded as a data gap, not silently dropped.
7. **Engine timing model:** overnight leg at old position + intraday leg at new
   position; no same-close fills possible by construction (tests enforce).

## 2026-07-20 (later stages)

8. **Data discovery outcome:** full daily NAV/price/premium history recovered from
   Sprott's server-rendered fund page (Tier 2); Numerco daily spot 2007→ (Tier 3);
   Cameco monthly 1988→ (Tier 2). Units-outstanding history NOT published anywhere
   → per-unit level synthetic NAV replaced by returns-space nowcasting (documented
   in nav/synthetic.py; justified by ATM issuance only at ≥100% NAV).
9. **Numerco timestamp convention:** corr(NAV_ret(t), Numerco_ret(t+1)) = 0.84 ≫
   same-day 0.55 → Numerco's as-dated series LAGS the assessment embedded in
   Sprott NAV. Any "spot leads NAV" signal from as-dated Numerco is an artifact;
   family D re-specified accordingly (nowcast uses only day-t observables).
10. **Holdout evaluated once** (2026-07-20) for the three families passing dev
    gates. Results in reports/tables/holdout_results.csv; script refuses reruns.
11. **DSR interpretation:** pre-registered trial accounting (all 432 grid points
    pooled) yields DSR 0.08 for G_sput_yca; family-level DSR 0.99 reported as a
    labeled secondary. The registered (pooled) figure governs the go/no-go.
12. **Verdict recorded:** G_sput_yca = CONDITIONAL NO-GO (paper-trade spec in
    LIVE_SPEC.md); all other families rejected with reasons in the leaderboard.
