# Data dictionary — canonical panel (`data/processed/panel.parquet`)

One row per (instrument, trading day). Built by `src/sput_research/features/panel.py`.

| Column | Type | Definition | Lineage |
|---|---|---|---|
| date | datetime | exchange session date (naive, exchange-local calendar) | Yahoo bar index |
| instrument | str | ticker (Yahoo convention) | — |
| currency | str | trading currency declared in config | config/data_sources.yaml |
| open/high/low/close | float | unadjusted session prices | Yahoo raw |
| adj_close | float | Yahoo dividend/split-adjusted close (return calc for distributing funds) | Yahoo raw |
| volume | int | shares/units | Yahoo raw |
| dollar_volume | float | close × volume | derived |
| dividends, splits | float | corporate actions on that date | Yahoo raw |
| usdcad | float | CAD per USD, same-date FX close | Yahoo CAD=X |
| nav_usd | float | Sprott published NAV/unit (SPUT rows only) | sprott fund page |
| price_usd_published | float | Sprott published U.U close | idem |
| premium_discount_published | float | Sprott published premium (fraction) | idem |
| u3o8_lbs | float | pounds held, weekly as-of stamps (NOT forward-filled in panel) | idem |
| lbs_acquired / lbs_cumulative | float | purchase events | idem |
| premium_discount | float | reconstructed: close/NAV−1 (CAD line via same-close FX) | derived; verified ≤6bp vs published |
| nav_valuation_at | datetime | date + 16:00 (Toronto wall time) | mechanics |
| nav_published_at | datetime | date + 23:00 (conservative evening publication stamp) | mechanics |
| signal_available_at | datetime | when a NAV-derived signal is usable | = nav_published_at |
| close_available_at | datetime | date + 16:00 | — |
| next_tradable_at | datetime | next business day 09:30 (first permissible fill) | derived |

Return conventions: strategy returns are fractions of strategy NAV per day,
net of costs; engine decomposes into overnight (old position) + intraday (new
position) legs. See `backtest/engine.py` docstring.

Auxiliary datasets: `data/raw/sprott/fund_data.parquet` (schema above),
`data/raw/numerco/spot.parquet` (date, spot_usd, implied_usd),
`data/raw/cameco/monthly.parquet` (date, spot_usd_lb, long_term_usd_lb, available_at).
