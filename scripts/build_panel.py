"""Build and save the canonical point-in-time panel."""

import pandas as pd

from sput_research.features.panel import build_panel, save_panel
from sput_research.paths import RAW


def main() -> int:
    sprott_pq = RAW / "sprott" / "fund_data.parquet"
    sprott = pd.read_parquet(sprott_pq) if sprott_pq.exists() else None
    panel = build_panel(sprott)
    save_panel(panel)
    sput = panel[panel["instrument"] == "U-UN.TO"]
    print(f"panel rows={len(panel)}, instruments={panel['instrument'].nunique()}, "
          f"SPUT {sput['date'].min().date()}->{sput['date'].max().date()}")
    if "premium_discount" in panel.columns:
        pd_cov = sput["premium_discount"].notna().mean()
        print(f"SPUT premium/discount coverage: {pd_cov:.1%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
