# Data inventory

All retrievals 2026-07-20 (UTC). Tiers: 1 licensed point-in-time benchmark /
2 public official with reliable stamps / 3 public proxy / 4 reconstructed.
See `docs/DATA_ENDPOINTS.md` for endpoint-level detail and failed probes;
`config/data_sources.yaml` for the machine-readable registry.

| Field | Source | Method | Range | Freq | Obs. timezone | Available-at policy | Revisions | Currency/unit | License | Tier | Fallback | Gaps |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| U.UN / U.U / SRUUF OHLCV | Yahoo Finance | yfinance API | 2021-07-26→2026-07-17 (UPC-era excluded) | daily | America/Toronto | exchange close | occasional retro fixes | CAD / USD | research only, no redistribution | 3 | TMX manual | no bid/ask history |
| YCA.L, URNM, URA, CCJ, PHYS, PSLV, CEF, SPPP, COP-UN, NLR, KAP, GLD, SLV OHLCV | Yahoo | yfinance | varies (all ≥2021-07) | daily | exchange-local | exchange close | idem | GBp/USD/CAD | idem | 3 | exchange sites | YCA in pence (verified ÷100) |
| USD/CAD, GBP/USD | Yahoo | yfinance | 2003→ | daily | UTC session | same-day close | none seen | rate | idem | 3 | BoC/BoE fixes | — |
| 13w T-bill (^IRX) | Yahoo | yfinance | 1960→ | daily | US/Eastern | same-day | none | % | idem | 3 | FRED | discount basis |
| SPUT NAV/unit (USD) | sprott.com fund page (inline Highcharts) | HTML capture + parser | 2021-07-19→2026-07-17 | daily (TSX bd) | 16:00 America/Toronto valuation | published same evening; base case next-open tradable; +1d stress | unknown; snapshots kept | USD | public website | 2 | Wayback snapshots | CAD NAV not published |
| SPUT share price (U.U USD) | idem | idem | idem | daily | TSX close | next open | idem | USD | idem | 2 | Yahoo U-U.TO (verified: median diff 1bp) | — |
| SPUT premium/discount | idem | idem | idem | daily | TSX close | next open | idem | fraction | idem | 2 | reconstructed close/NAV−1 | — |
| U3O8 pounds held | idem | idem | 2021-07-16→2026-07-17 | weekly | as-of Friday | next business day (conservative) | idem | lbs | idem | 2 | press releases | weekly only |
| U3O8 purchases (lbs, cumulative) | idem | idem | 256 events → 2026-05-11 | event | trade date | next day | idem | lbs | idem | 2 | — | settlement dates unknown |
| Units outstanding / total NAV | sprott.com API `BullionCalculatorData` | JSON | **current day only** | daily fwd | 16:00 Toronto | same evening | n/a | units/USD | public | 2 (forward) / **4 (history: NOT AVAILABLE)** | Wayback backfill (partial) | **no history — blocks per-unit level synthetic NAV; returns-space used instead** |
| Numerco U3O8 spot + implied | numerco Parse backend | JSON paged | 2007-07-27→2026-07-17 | daily | ~UK evening (stamp convention verified: lags Sprott NAV input by ~1d) | next day (conservative) | pre-2018 rows bulk-backloaded | USD/lb | public page; indications NOT executable | 3 | Cameco monthly | stamp-convention offset documented |
| UxC / TradeTech spot & term | — | — | — | weekly/daily | — | — | — | USD/lb | **LICENSED — NOT OBTAINED** | 1 | Cameco monthly republication | provider interface stubbed |
| Cameco monthly spot & LT | cameco.com | HTML table | 1988-01→2026-06 | monthly | month-end | month-end + 3bd | none seen | USD/lb | public | 2 | — | monthly granularity |
| CME UX futures | cmegroup.com | — | — | — | — | — | — | — | **blocked (403 anti-scraping ToU)** | — | none free | OI ≈ 0 anyway (MECHANICS) |
| U.UN options (MX) | Montréal Exchange | — | listed 2025-09-02 | — | — | — | — | CAD | paid | 1 | none | **family J deferred** |
| U.UN borrow rate history | — | — | — | — | — | — | — | — | prime-broker only | 1 | config assumption 300bps + shocks | **UNVERIFIED assumption** |
| Historical bid/ask spreads | — | — | — | — | — | — | — | — | — | 1 | vol/volume estimates, 0.5–3× stress | **estimated, not observed** |
| UPC (pre-2021) NAV/price | — | — | — | — | — | — | — | — | — | — | none found | **excluded; unadjusted conversion break in Yahoo** |

## Explicit non-substitutions

- Numerco indications are never used as fills; only as signal inputs/diagnostics.
- Units-outstanding history was NOT interpolated; hypothesis E runs only on
  acquisition events + premium (published fields), not reconstructed units.
- Sprott's NAV input composite (UxC/TradeTech/Platts/Numerco weights) is
  unknown (MECHANICS UNVERIFIED item); no synthetic recreation is presented as
  "the" NAV input.
