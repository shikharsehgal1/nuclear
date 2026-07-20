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
