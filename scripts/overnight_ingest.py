"""Pull daily bars for the overnight universe (+ hourly for exit-timing checks)."""

from sput_research.overnight.data import CFG, fetch_daily, fetch_hourly, fetch_vix

HOURLY = ["URNM", "URA", "COPX", "SIL", "REMX", "GDXJ", "SILJ", "GLD", "SLV", "USO", "SPY"]

if __name__ == "__main__":
    import sys
    force = "--force" in sys.argv
    fetch_daily(force=force)
    fetch_hourly(HOURLY, force=force)
    fetch_vix(force=force)
    print("done; end =", CFG["data"]["end"])
