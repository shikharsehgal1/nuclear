# LIVE_SPEC — paper trading only

**Status: CONDITIONAL NO-GO for real capital.** G_sput_yca passed every
individual economic/robustness/holdout gate except the pooled deflated-Sharpe
criterion, but the red team showed the stresses are jointly fatal (2× costs +
1-day lag → holdout Sharpe 0.13) and ~83% of PnL sits on the borrow-dependent
YCA leg. The paper track's primary purpose is therefore to measure REAL fill
quality and borrow, which decide whether the edge exists at all. This document
specifies a
**paper-trading process** whose purpose is to (a) accumulate true point-in-time
out-of-sample evidence, (b) measure real fill quality and borrow, before any
go decision is revisited. No broker connection; no real orders.

## Strategy: G_sput_yca (SPUT vs Yellow Cake relative value)

### Signal (computed once daily, after 21:05 UTC / TSX close)

```
sput_usd(t) = close(U.UN, TSX, CAD) / USDCAD(t, 16:00 ET)
yca_usd(t)  = close(YCA.L, LSE, GBp)/100 × GBPUSD(t)     # prior LSE session if UK holiday, max 3d stale
x(t)        = ln(sput_usd(t)) − ln(yca_usd(t))
z(t)        = ( x(t) − mean(x, 120d) ) / std(x, 120d)
```

Frozen parameters (modal walk-forward selection; pre-registered grid):
`z_window=120, entry_z=1.0, exit_z=0.5, holding_cap=10 trading days`.

### Rules

| Event | Action |
|---|---|
| flat and z ≤ −1.0 | enter: +50% NAV U.UN (TSX), −50% NAV YCA.L (LSE) |
| flat and z ≥ +1.0 | enter: −50% NAV U.UN, +50% NAV YCA.L |
| in position and z crosses back within ±0.5 | exit both legs |
| position age = 10 trading days | force exit |
| YCA close stale > 3 LSE sessions | no new entries; exits allowed |

### Execution (paper)

- U.UN leg: next TSX opening auction (09:30 ET); record the auction print.
- YCA leg: next LSE opening auction (08:00 UK); record the auction print.
- Log for every fill: quoted spread at open, assumed fill vs mid, achievable
  size at touch. Participation cap 5% of trailing 60d ADV per leg.
- Record daily indicative borrow (broker short availability screens) for
  YCA.L and U.UN even though no short is placed — this is the key unknown.

### Sizing & risk

- Paper capital: US$300k (within red-team-revised capacity of ~$0.3–0.6M;
  the YCA leg's 5% ADV participation is ≈$289k/day).
- Max gross exposure 100% (0.5/0.5). No leverage. No pyramiding.
- Kill switches (stop paper test, investigate):
  - strategy drawdown > 12% (2.4× worst backtest DD);
  - hedge relationship break: 120d correlation(SPUT, YCA daily USD returns) < 0.3;
  - either leg's measured half-spread persistently > 3× config assumption;
  - borrow indicated unavailable or fee > 10%/yr on >20% of days;
  - corporate action on YCA (tender/buyback program change, placing) → flat.
- Expected failure regimes (monitor, from HYPOTHESES/backtest): market-wide
  uranium crashes (both legs gap together — fine, hedged), YCA discount
  regime shift from buyback policy changes, TSX/LSE holiday desync weeks.

### Data dependencies & computation time

Yahoo (or broker) closes for U-UN.TO, YCA.L, CAD=X, GBPUSD=X by 21:05 UTC;
signal is 4 arithmetic operations — run `scripts/paper_signal.py` (to be
generated from `families.family_G`) at 21:15 UTC; orders staged for next opens.

### Review

Monthly: compare paper fills vs backtest assumptions (spread, impact, borrow);
append results to DECISION_LOG. Go/no-go re-evaluation only after ≥ 12 months
of paper track AND resolution of the borrow question, against the SAME
pre-registered thresholds (no relaxation).
