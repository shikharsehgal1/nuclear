# SPUT NAV/Spot Dislocation Research Platform

Point-in-time research repository testing whether dislocations between the
Sprott Physical Uranium Trust's market price, NAV, physical uranium value and
related liquid securities support an implementable systematic strategy.

**Null hypothesis:** apparent premium/discount or spot-relative alpha
disappears after correcting for stale NAVs, publication timing, trading costs,
short availability, market impact, parameter selection and multiple testing.

## Reproduce

```bash
uv sync
make research        # ingest -> validate -> panel -> tests -> backtests -> robustness -> capacity -> report
```

Individual stages: `make ingest`, `make panel`, `make backtests`, `make report`.

## Key documents

| File | Contents |
|---|---|
| `docs/MECHANICS.md` | Instrument/legal mechanics with citations |
| `docs/DATA_INVENTORY.md` | Every field: source, timestamps, licensing, tier |
| `docs/HYPOTHESES.md` | Pre-registered hypotheses (frozen before testing) |
| `config/go_no_go_thresholds.yaml` | Decision criteria (frozen before OOS results) |
| `docs/DECISION_LOG.md` | Dated methodological decisions |
| `docs/RED_TEAM.md` | Independent skeptical review findings |
| `reports/FINAL_REPORT.md` | Conclusions, leaderboard, failed strategies |
| `docs/LIVE_SPEC.md` | Paper-trading spec for any surviving strategy |

## Non-negotiable research rules

1. Every observation carries an `available_at`; signals trade at the **next open**, never the same close.
2. Persistent closed-end discounts are **not arbitrage** (no redemption mechanism forces convergence).
3. Assessed uranium "spot" is not an executable price and is never used as a fill.
4. Net-of-cost results only; borrow-dependent shorts are flagged.
5. Negative results are preserved, not tuned away.

## Data caveats (free-data build)

- Market data: Yahoo Finance (Tier 3; no historical bid/ask — spreads estimated and stress-tested).
- UxC/TradeTech licensed assessments unavailable; Sprott-published spot and
  Cameco monthly averages used as documented substitutes.
- Predecessor UPC history excluded (unadjusted conversion break; see DECISION_LOG #3).
- U.UN options history unavailable (hypothesis family J deferred).
