# Overnight Drift in Commodity-Miner ETFs

> the original SPUT/YCA pair trade writeup now lives in [SPUT_YCA.md](SPUT_YCA.md).

**TL;DR:** niche commodity ETFs (uranium, silver/gold juniors, copper, rare earths) make basically all their money **overnight** and lose money **during the session**. URNM since 2020: +74%/yr close→open, −43%/yr open→close. the trade: every month pick the 5 ETFs where that gap has been strongest over the last 24 months. each day, buy the ones that closed up in the **closing auction**, sell in the **next opening auction**, and short them open→close with the same money. no waiting for a signal, the capital works every day. net Sharpe **1.0 / 1.7 / 2.1** across 2011–15 (never looked at), 2016–23 (where params were picked) and 2024–26 (out of sample). green in all 17 calendar years. catch: it only works through the auctions (cross the spread and it's dead), it tops out around **$100–300k**, the short leg needs a margin account with $25k+ (pattern day trader rule), and in 2024–26 uranium carried most of it.

## the best strats (short version)

| rank | strategy | what you do | net Sharpe 2011–15 / 2016–23 / 2024–26 | use it when |
|---|---|---|---|---|
| **1** | **up-day long/short** | buy the up-closers at the close auction, sell at the open auction, short all 5 open→close | **1.04 / 1.71 / 2.12** | default. green 17/17 years, works in bear markets too |
| 2 | up-day long overnight only | same, without the intraday short | 0.31 / 2.08 / 2.65 | you can't short or you're under $25k. flat in commodity bear markets (2012–14) |
| 3 | short-only (intraday leg alone) | short the 5 at the open, cover at the close, no overnight long | 0.90 / 0.37 / 0.58 | not on its own. max DD −38%, 13/17 years green. most of the edge is the overnight long |
| — | everything else | trend, intraday momentum, EIA windows, pairs (USO/BNO, GLD/SLV, PPLT/PALL), roll timing, 5-min lead-lag | — | don't. inconsistent or too small to beat costs |

**rules for #1:**
- auction orders only (MOC in, MOO out). crossing the spread kills it
- size $25k–$300k. ADV ≥ $20M filter if you want more room
- margin account + intraday short locates on thin ETFs (URNM, SILJ)
- 2024–26 was carried by uranium (without it, OOS Sharpe 0.29)
- optional overlays that helped in every period (post-hoc, see below): size by **15/VIX (max 1x)**, and hold a small **long SPY** sized to the strategy's trailing beta
- paper trade first

**risk (up-day LS, net, 2011–2026):** CAGR 47%, vol 26%, Sharpe 1.60, Sortino 2.24, max DD **−27%** (Mar 2020, recovered in 3 months), longest underwater 367 days (2013–14), worst day −22% (Mar 2020), worst month −12%, 70% of months up.

---

## the effect

![overnight vs intraday](reports/overnight/figures/01_overnight_vs_intraday.png)

the top of that chart is all miner/producer equity ETFs: URNM, SILJ, SIL, COPX, URA, GDXJ, NLR, REMX. futures ETFs (USO, UNG, CORN…) barely show it. my best guess at why: part of what these ETFs hold trades in Sydney, London and Kazakhstan while the US ETF is closed, so it catches up at the open. on top of that, retail buying in attention-grabbing names tends to hit at the open, which pushes opens up (Berkman et al. 2012, "Paying Attention: Overnight Returns and the Hidden Cost of Buying at the Open").

![cumulative split](reports/overnight/figures/02_cumulative_split.png)

## the rule

1. **universe:** 36 commodity-linked US ETFs, chosen for being commodity exposure, not for their results (`config/overnight.yaml`). needs ≥$2M median daily volume.
2. **pick (1st of each month):** rank by trailing 24-month Sharpe of (overnight − intraday) and keep the top 5 with a positive score. weight by inverse overnight vol.
3. **each day:** of those 5, the ones that are up open→close get the overnight money, renormalised (cash if none are up). **MOC buy → MOO sell.**
4. **LS leg:** short all 5 from the open to the close with the same capital. gross exposure is never above 1x.

`up-day LS` = all four steps. `core` skips step 3; `ON` skips step 4.

## in-sample / out-of-sample

| period | role | touched? |
|---|---|---|
| 2010–2015 | **pre-sample** | never looked at before the freeze |
| 2016–2023 | discovery | the only data used to choose lookback, K, and the up-day filter |
| 2024 – 2026-10 | out-of-sample | first run after the freeze |

the ETF picks are walk-forward (month m only sees data before m), so URNM etc. are never hand-picked. full disclosure: this idea came out of a sweep that saw 2024–26 per-ticker numbers, so **2010–15 is the cleanest test**, not 2024–26 (see `docs/OVERNIGHT_DECISIONS.md`).

## results (net, auction costs)

| strategy | 2011–15 pre-sample | 2016–23 discovery | 2024–26 OOS | max DD | years green |
|---|---|---|---|---|---|
| **up-day LS** | **1.04** (22%/yr) | **1.71** (53%/yr) | **2.12** (83%/yr) | −27% | **17/17** |
| up-day ON | 0.31 | 2.08 | 2.65 | −24% | 13/17 |
| core LS | 0.93 | 1.13 | 1.73 | −28% | |
| core ON | 0.03 | 1.09 | 1.94 | −37% | |
| buy & hold same names | −0.80 | 0.26 | 0.68 | | 9/17 |

![equity curves](reports/overnight/figures/03_equity_curves.png)
![pnl by year](reports/overnight/figures/06_pnl_by_year.png)

- the long-only versions **fail the pre-sample**. 2011–15 was a commodity bear market and buying overnight still meant owning miners. the LS hedge is what makes it work in every regime, so up-day LS is the headline.
- OOS up-day LS: bootstrap 95% CI on Sharpe **[1.15, 3.22]**, deflated Sharpe 0.61 after counting 200 trials.

![rolling sharpe](reports/overnight/figures/11_rolling_sharpe.png)

## is the money just sitting there?

no, and this is the big difference from SPUT/YCA, which only trades when the z-score stretches past ±1. here:

- the overnight leg is invested **73–83% of nights** (the rest are nights where none of the 5 closed up)
- the LS short leg runs **every** trading day
- the **same dollar** is long overnight and short intraday, so you never need more than 1x gross

## making it better

| change | result | kept? |
|---|---|---|
| auction execution (MOC/MOO) vs crossing the spread | the whole edge. crossing the spread: Sharpe −2.2 / −1.6 / 0.4 | **yes, mandatory** |
| up-day filter (only hold names that closed up) | discovery 1.13 → 1.71 (LS). down-day control: 0.56 | **yes** |
| LS: short the same names intraday | the only version positive in the pre-sample | **yes** |
| higher liquidity floor (ADV ≥ $20M) | slightly lower Sharpe (0.65 / 1.01 / 1.94) but ~2× the capacity | optional, if you're >$100k |
| sell later than the open | niche names give back half the overnight gain by 10:30 | no, sell in the open auction |
| skip weekends | +0.1 Sharpe on ON only, nothing on LS | no |
| futures/physical ETFs only | ~0 Sharpe | no, it's a miners effect |

![exit timing](reports/overnight/figures/07_exit_timing.png)

the up-day signal uses the close in the backtest. live, you'd use the price a few minutes before the MOC cutoff. checked on KIBOT 5-min data for 2016–23: the 15:45 sign agrees with the close sign on ~95% of days, and the after-up/after-down gap is still there.

## variations, monte carlo, risk overlays, hedging

all of this was run **after** the rule was frozen, so it's sensitivity analysis. nothing here re-picks the rule on 2024–26.

**ranking window × number of names.** 90 combos, from 1 month (~21 days) to 48 months and from top 1 to top 15:

![lookback x topk](reports/overnight/figures/12_lookback_topk.png)

- every combo is positive in 2016–23 and 2024–26, and 89/90 in the pre-sample. it's a plateau, not a lucky cell
- 6–18 months with 2–6 names is the most balanced. 24m/top 5 is fine
- 1–3 month windows (~60 days) work early but are weaker OOS (~0.6–1.6). 36–48 months are weak early but best OOS (uranium stayed on top for years)
- 10–15 names dilutes it. blending the 6+12+24 month rankings (~8 names) is also worse: 0.86 / 1.94 / 1.84
- other ranking scores (raw mean gap, overnight-only Sharpe) land in the same place, nothing better

![score variants](reports/overnight/figures/13_score_variants.png)

**monte carlo / randomized sampling:**

| test | result |
|---|---|
| pick the 5 ETFs **at random** each month (500 runs, same mechanics) | the ranked version beats **100%** of them in all 3 periods. random median Sharpe −0.20 / 0.57 / 0.13. **the ranking is the edge**, the close→open mechanics alone aren't |
| drop a **random 30% of the universe** (300 runs) | positive in 97% / 100% / 98% of runs. median 0.74 / 1.43 / 1.68. runs without URA+URNM: OOS median 1.05 |
| **random start dates** (1,000 windows each) | 92% of 1-year windows and 97% of 2-year windows made money |
| **block bootstrap** of daily returns (5,000 one-year paths) | 1-year Sharpe 5–95%: [0.1, 3.1]. P(losing year) 5%. P(1-year drawdown worse than −20%) 17%, worse than −30%: 1% |

![random selection](reports/overnight/figures/14_random_selection_mc.png)
![randomized sampling](reports/overnight/figures/18_randomized_sampling.png)
![bootstrap](reports/overnight/figures/15_bootstrap_mc.png)

**volatility.** usually 15–30% a year. spikes: 2020 (46%, ~77% rolling at the peak), 2022 (33%), 2025 (35%).

![vol history](reports/overnight/figures/16_vol_history.png)

**VIX sizing** (size = 15/VIX, using the VIX close from 2 days before so it's known before the MOC):

| sizing | Sharpe pre / disc / OOS | max DD full | avg size |
|---|---|---|---|
| as frozen (1x) | 1.04 / 1.71 / 2.12 | −27% | 1.00 |
| **15/VIX, max 1x** | **1.05 / 1.95 / 2.38** | **−18%** | 0.85 |
| 15/VIX, max 2x | 1.07 / 1.97 / 2.40 | −21% | 0.91 |
| half size when VIX > 25 | 0.98 / 1.86 / 2.26 | −20% | 0.94 |
| vol target 20% (de-risk only) | 0.97 / 1.86 / 2.29 | −20% | — |

the strategy still makes money when VIX is high (Sharpe 1.1–1.6 above VIX 25), so VIX sizing doesn't dodge losing regimes. it just cuts the size of the gaps, like March 2020. 15/VIX capped at 1x is the cleanest: it didn't hurt any period.

![vix sizing](reports/overnight/figures/17_vix_sizing.png)

**hedging / beta.** up-day LS is already **short** the market: beta about −0.25 to −0.37 to SPY and about −0.2 to GDX, because the intraday short leg dominates.

| hedge | Sharpe pre / disc / OOS | max DD full | corr to SPY |
|---|---|---|---|
| none | 1.04 / 1.71 / 2.12 | −27% | −0.16 |
| short SPY overnight (beta-sized) | 0.66 / 1.36 / 1.71 | −34% | −0.33 |
| short GDX overnight (beta-sized) | 0.70 / 1.30 / 1.83 | −29% | −0.23 |
| **beta-neutral: hold long SPY ≈ −beta (avg 0.35x)** | **1.18 / 1.88 / 2.36** | −29% | **0.05** |
| beta-neutral: hold long GDX | 0.95 / 1.91 / 2.60 | −26% | −0.09 |

shorting a hedge overnight is the wrong way round: it adds to the short beta and pays away SPY/GDX's own overnight drift. what helps is the opposite: a small **long SPY** sized to the trailing beta makes it market-neutral (corr ~0) and lifts Sharpe in every period.

## then i tried to kill it

| up-day LS, Sharpe | pre | disc | OOS |
|---|---|---|---|
| as frozen | 0.98 | 1.71 | 2.12 |
| best 10 days removed | 0.59 | 1.43 | 1.47 |
| no uranium (URA/URNM/NLR) | 0.98 | 1.44 | **0.29** |
| miners/equity ETFs only | 1.06 | 1.93 | 2.21 |
| futures/physical only | −0.82 | −0.03 | −0.29 |
| ADV ≥ $20M | 0.65 | 1.01 | 1.94 |

(the pre-sample number here counts the empty months before the first pick, hence 0.98 vs 1.04.)

![param surface](reports/overnight/figures/04_param_surface.png)
![cost sensitivity](reports/overnight/figures/05_cost_sensitivity.png)
![capacity](reports/overnight/figures/09_capacity.png)
![selection](reports/overnight/figures/08_selection_map.png)

what landed:

- **costs are everything.** breakeven is 6.5–8.8 bp/side for up-day LS. auctions cost ~1.5 bp, crossing the spread costs 2–20 bp + commission on these names.
- **capacity is tiny.** with sqrt impact against auction volume (assumed 4% of ADV per auction, conservative), Sharpe falls to ~1.1 at $100k, ~0.4 at $300k, and below zero at $1M. the ADV ≥ $20M version holds 0.8 at $300k.
- **2024–26 is a uranium story.** take out URA/URNM/NLR and OOS LS drops to 0.29. it held up without uranium in 2011–23 (0.98 / 1.44), so it's not *only* uranium, but recently it mostly is.
- the whole grid is positive in discovery and OOS for both variants (fig above), so it's not one lucky parameter cell. ON in the pre-sample is ~0 across the whole grid.

## verdict

- **up-day LS is the one.** positive in all three periods, including six years nobody looked at, and in all 17 calendar years. Sharpe ~1.6 over 2011–2026.
- **it's an execution strategy.** if your broker can't do MOC/MOO on Arca-listed ETFs, don't bother.
- **practical size: $25k–$300k.** under $25k the intraday short runs into the pattern day trader rule (check your broker, FINRA has been revising it), so run the ON-only version (and accept it can go flat for years like 2012–14). above ~$300k impact eats it.
- **you need intraday short locates** for SILJ/URNM-type names. no overnight borrow fee because the short is flat by the close, but the locate has to be there.
- status: paper trade first. the up-day filter was found in 2016–23 and passed both untouched periods, but it's one more degree of freedom.

## repro

```
uv sync
make overnight     # ingest (yahoo) → timing tests → grid/backtests/robustness/figures
```

optional: `KIBOT_DIR=/path/to/KIBOT make overnight` adds the 2016–23 5-min exit-timing panel (licensed data, not committed).

| file | what |
|---|---|
| `config/overnight.yaml` | universe, periods, grid, costs, the frozen rule |
| `docs/OVERNIGHT_DECISIONS.md` | every call in order, incl. the lookahead bug i caught in myself |
| `src/sput_research/overnight/` | data split + walk-forward strategy |
| `tests/test_overnight.py` | point-in-time tests (poisoned future data must not change picks/signals) |
| `reports/overnight/tables/` | every number above |

## the fine print

- prices are yahoo daily OHLC. checked against KIBOT 5-min for 10 ETFs over 2016–23: overnight returns correlate 0.994–0.999.
- "open" and "close" are the official auction prints. the backtest assumes you get them plus 1.5 bp. thin auctions can move against you, which is what the capacity curve models.
- spreads come from a tiered $ADV table, not measured quotes. a daily-bar spread estimator was tried and thrown out (it put GLD at 30 bp).
- days with stale or zero-volume bars are not traded (CPER/CANE/NLR lose 12–23% of days to this).
- no taxes. every overnight hold is a short-term gain.
