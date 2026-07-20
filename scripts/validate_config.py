"""Validate config files parse and contain required keys."""

import yaml

from sput_research.paths import CONFIG

REQUIRED = {
    "data_sources.yaml": ["yahoo_equities"],
    "costs.yaml": ["defaults", "half_spread_bps", "borrow_bps_annual", "stress_multipliers"],
    "preregistered_parameters.yaml": ["sample", "grids", "execution"],
    "go_no_go_thresholds.yaml": ["go_criteria", "automatic_rejection"],
}


def main() -> int:
    ok = True
    for fname, keys in REQUIRED.items():
        path = CONFIG / fname
        if not path.exists():
            print(f"MISSING {fname}")
            ok = False
            continue
        cfg = yaml.safe_load(path.read_text())
        missing = [k for k in keys if k not in cfg]
        if missing:
            print(f"{fname}: missing keys {missing}")
            ok = False
        else:
            print(f"{fname}: ok")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
