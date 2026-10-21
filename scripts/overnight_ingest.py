"""Pull daily bars for the overnight universe (+ hourly for exit-timing and the audit's 15:30 signal)."""

from sput_research.overnight.data import CFG, fetch_daily, fetch_hourly, fetch_minute, fetch_vix, tradeable_universe

MINUTE = ["URNM", "URA", "NLR", "SILJ", "SIL", "GDXJ", "COPX", "REMX", "XME", "FCG", "PALL", "BNO",
          "GDX", "GLD", "SPY"]
HOURLY = tradeable_universe() + ["SPY"]

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_daily(force=force)
    fetch_hourly(HOURLY, force=force)
    fetch_vix(force=force)
    fetch_minute(MINUTE, force=force)
    print("done; end =", CFG["data"]["end"])
