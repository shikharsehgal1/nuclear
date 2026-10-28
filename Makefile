.PHONY: overnight research ingest validate panel backtests robustness capacity report test lint

research: validate-config ingest panel test backtests robustness capacity report

validate-config:
	uv run python scripts/validate_config.py

ingest:
	uv run python scripts/ingest_data.py

validate:
	uv run python scripts/validate_data.py

panel:
	uv run python scripts/build_panel.py

backtests:
	uv run python scripts/run_backtests.py

robustness:
	uv run python scripts/run_robustness.py

capacity:
	uv run python scripts/run_capacity.py

report:
	uv run python scripts/build_report.py

test:
	uv run pytest -q

lint:
	uv run ruff check src tests scripts

paper:
	uv run python scripts/paper_trade.py

overnight:
	uv run python scripts/overnight_ingest.py
	uv run pytest -q tests/test_overnight.py
	uv run python scripts/overnight_research.py
	uv run python scripts/overnight_sensitivity.py
	uv run python scripts/overnight_postcost.py
	uv run python scripts/overnight_auction_prices.py
	uv run python scripts/overnight_auction_ticks.py
	uv run python scripts/overnight_universe_ext.py
	uv run python scripts/overnight_audit.py
	uv run python scripts/overnight_auction_imbalance.py
	uv run python scripts/overnight_risk.py
	uv run python scripts/overnight_auction_rules.py
