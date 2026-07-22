"""Daily paper-trading runner for G_sput_yca per docs/LIVE_SPEC.md.

Run once per day, any time after the TSX close (idempotent; safe to re-run,
and it catches up if you miss days — staged orders fill at their execution
date's actual open, fetched historically).

Frozen rule: z = zscore_120( ln(U.UN_USD / YCA_USD) ), enter |z|>=1.0 (long
cheap leg, short rich leg, 50% of capital each), exit |z|<=0.5 or 10 sessions.
Fills at next TSX/LSE open +/- modeled half-spread; $1 min commission/order;
borrow accrues daily on the short leg. State in paper/state.json, log in
paper/paper_log.csv (both local-only, gitignored).
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
import requests
import yfinance as yf

ROOT = Path(__file__).resolve().parents[1]
PAPER = ROOT / "paper"
PAPER.mkdir(exist_ok=True)
STATE_F = PAPER / "state.json"
LOG_F = PAPER / "paper_log.csv"

# ---- frozen parameters (do not tune; see config/preregistered_parameters.yaml)
Z_WINDOW, ENTRY_Z, EXIT_Z, MAX_HOLD = 120, 1.0, 0.5, 10
CAPITAL_USD_DEFAULT = 2500.0
HALF_SPREAD = {"UUN": 6e-4, "YCA": 12e-4}   # measured 2026-07-20
MIN_COMMISSION = 1.0
FX_SPREAD = 2.5e-4
BORROW_DEFAULT = {"UUN": 0.0277, "YCA": 0.0068}  # annual, IBKR 2026-07-17
KILL_DD = 0.12


def now_et() -> datetime:
    return datetime.now(ZoneInfo("America/New_York"))


def fetch_history() -> dict[str, pd.DataFrame]:
    out = {}
    for key, sym in [("UUN", "U-UN.TO"), ("YCA", "YCA.L"),
                     ("USDCAD", "CAD=X"), ("GBPUSD", "GBPUSD=X")]:
        h = yf.Ticker(sym).history(period="2y", auto_adjust=False)
        h.index = pd.DatetimeIndex(h.index).tz_localize(None).normalize()
        out[key] = h[["Open", "Close"]].rename(columns=str.lower)
    # drop today's partial TSX bar if the session hasn't closed yet
    et = now_et()
    today = pd.Timestamp(et.date())
    if et.hour < 16 and today in out["UUN"].index:
        out["UUN"] = out["UUN"].drop(today)
    # LSE closes 16:30 UK = 11:30 ET
    if (et.hour, et.minute) < (11, 35) and today in out["YCA"].index:
        out["YCA"] = out["YCA"].drop(today)
    return out


def compute_signal(d: dict[str, pd.DataFrame]) -> pd.Series:
    fx = d["USDCAD"]["close"]
    gbp = d["GBPUSD"]["close"]
    uun_usd = d["UUN"]["close"] / fx.reindex(d["UUN"].index).ffill()
    yca_usd = d["YCA"]["close"] * gbp.reindex(d["YCA"].index).ffill() / 100.0
    x = np.log(uun_usd) - np.log(yca_usd.reindex(uun_usd.index).ffill(limit=3))
    x = x.dropna()
    mu = x.rolling(Z_WINDOW, min_periods=60).mean()
    sd = x.rolling(Z_WINDOW, min_periods=60).std(ddof=1)
    return ((x - mu) / sd).dropna()


def live_quotes() -> dict:
    q = {}
    for key, sym in [("UUN", "U-UN.TO"), ("YCA", "YCA.L")]:
        try:
            i = yf.Ticker(sym).info
            b, a = i.get("bid"), i.get("ask")
            q[key] = {"bid": b, "ask": a, "state": i.get("marketState"),
                      "spread_bps": round((a - b) / ((a + b) / 2) * 1e4, 1)
                      if (b and a and a > b > 0) else None}
        except Exception:
            q[key] = {"bid": None, "ask": None, "state": "ERR", "spread_bps": None}
    return q


def borrow_snapshot() -> dict:
    out = {}
    for key, sym in [("UUN", "SRUUF"), ("YCA", "YLLXF")]:
        try:
            r = requests.get(f"https://iborrowdesk.com/api/ticker/{sym}",
                             headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
            last = r.json()["daily"][-1]
            out[key] = {"fee_pct": last["fee"], "available": last["available"],
                        "as_of": last["date"]}
        except Exception:
            out[key] = {"fee_pct": None, "available": None, "as_of": None}
    return out


def load_state() -> dict:
    if STATE_F.exists():
        return json.loads(STATE_F.read_text())
    return {"capital": CAPITAL_USD_DEFAULT, "cash": CAPITAL_USD_DEFAULT,
            "position": None, "pending": None, "equity_peak": CAPITAL_USD_DEFAULT,
            "killed": False, "last_run_date": None}


def fill_price(df: pd.DataFrame, date: pd.Timestamp, side: int, leg: str) -> float | None:
    """Open of `date` adjusted adversely by the modeled half-spread."""
    if date not in df.index:
        after = df.index[df.index >= date]
        if not len(after):
            return None
        date = after[0]
    px = float(df.loc[date, "open"])
    return px * (1 + side * HALF_SPREAD[leg])  # side +1 buy pays up, -1 sell hits bid


def mark_equity(state: dict, d: dict) -> float:
    eq = state["cash"]
    pos = state.get("position")
    if pos:
        fx = float(d["USDCAD"]["close"].iloc[-1])
        gbp = float(d["GBPUSD"]["close"].iloc[-1])
        uun_usd = float(d["UUN"]["close"].iloc[-1]) / fx
        yca_usd = float(d["YCA"]["close"].iloc[-1]) * gbp / 100.0
        eq += pos["uun_units"] * uun_usd + pos["yca_units"] * yca_usd
    return eq


def main() -> int:
    state = load_state()
    if state["killed"]:
        print("KILLED state - review paper/state.json and docs/LIVE_SPEC.md before resetting")
        return 1
    d = fetch_history()
    z = compute_signal(d)
    sig_date, z_now = z.index[-1], float(z.iloc[-1])
    fx_now = float(d["USDCAD"]["close"].iloc[-1])
    gbp_now = float(d["GBPUSD"]["close"].iloc[-1])

    # 1) fill any staged order whose execution session has now happened
    pend = state.get("pending")
    if pend:
        exec_date = pd.Timestamp(pend["execute_on"])
        if exec_date <= d["UUN"].index[-1]:
            fx_exec = float(d["USDCAD"]["close"].asof(exec_date))
            gbp_exec = float(d["GBPUSD"]["close"].asof(exec_date))
            if pend["action"] == "enter":
                side = pend["side"]  # +1: long UUN / short YCA ; -1: reverse
                half = state["capital"] / 2
                pu = fill_price(d["UUN"], exec_date, +1 if side > 0 else -1, "UUN")
                py = fill_price(d["YCA"], exec_date, -1 if side > 0 else +1, "YCA")
                if pu and py:
                    pu_usd = pu / fx_exec
                    py_usd = py * gbp_exec / 100.0
                    uun_units = side * half / pu_usd
                    yca_units = -side * half / py_usd
                    cost = 2 * MIN_COMMISSION + 2 * half * FX_SPREAD
                    state["cash"] -= uun_units * pu_usd + yca_units * py_usd + cost
                    state["position"] = {"side": side, "entry_date": str(exec_date.date()),
                                         "uun_units": uun_units, "yca_units": yca_units,
                                         "uun_fill": pu, "yca_fill": py, "sessions_held": 0}
                    print(f"FILLED entry {('LONG UUN/SHORT YCA' if side>0 else 'SHORT UUN/LONG YCA')} "
                          f"@ UUN C${pu:.2f} / YCA {py:.1f}p on {exec_date.date()}")
            elif pend["action"] == "exit" and state.get("position"):
                pos = state["position"]
                pu = fill_price(d["UUN"], exec_date, -1 if pos["uun_units"] > 0 else +1, "UUN")
                py = fill_price(d["YCA"], exec_date, -1 if pos["yca_units"] > 0 else +1, "YCA")
                if pu and py:
                    proceeds = pos["uun_units"] * pu / fx_exec + pos["yca_units"] * py * gbp_exec / 100.0
                    state["cash"] += proceeds - 2 * MIN_COMMISSION
                    print(f"FILLED exit on {exec_date.date()} @ UUN C${pu:.2f} / YCA {py:.1f}p")
                    state["position"] = None
            state["pending"] = None

    # idempotency: if we already processed this signal date, just report
    already_ran = state.get("last_run_date") == str(sig_date.date())

    # 2) accrue borrow + holding sessions on open position (once per session)
    pos = state.get("position")
    if pos and not already_ran:
        pos["sessions_held"] += 1
        short_leg = "YCA" if pos["side"] > 0 else "UUN"
        short_notional = abs(pos["yca_units"] * float(d["YCA"]["close"].iloc[-1]) * gbp_now / 100.0
                             if short_leg == "YCA" else
                             pos["uun_units"] * float(d["UUN"]["close"].iloc[-1]) / fx_now)
        state["cash"] -= short_notional * BORROW_DEFAULT[short_leg] / 252

    # 3) decide next action from today's signal
    action = "hold" if pos else "flat"
    if pos and not already_ran:
        # long-spread entered at z<=-1 exits when z>=-0.5; short-spread at z>=+1 exits z<=+0.5
        if pos["side"] > 0:
            want_exit = z_now >= -EXIT_Z or pos["sessions_held"] >= MAX_HOLD
        else:
            want_exit = z_now <= EXIT_Z or pos["sessions_held"] >= MAX_HOLD
        if want_exit and not state["pending"]:
            state["pending"] = {"action": "exit", "signal_date": str(sig_date.date()),
                                "execute_on": str((sig_date + pd.tseries.offsets.BDay(1)).date())}
            action = "stage_exit"
    elif not state["pending"] and not already_ran:
        if z_now <= -ENTRY_Z:
            state["pending"] = {"action": "enter", "side": +1, "signal_date": str(sig_date.date()),
                                "execute_on": str((sig_date + pd.tseries.offsets.BDay(1)).date())}
            action = "stage_enter_long_uun"
        elif z_now >= ENTRY_Z:
            state["pending"] = {"action": "enter", "side": -1, "signal_date": str(sig_date.date()),
                                "execute_on": str((sig_date + pd.tseries.offsets.BDay(1)).date())}
            action = "stage_enter_short_uun"

    # 4) mark equity, kill switches
    equity = mark_equity(state, d)
    state["equity_peak"] = max(state["equity_peak"], equity)
    dd = equity / state["equity_peak"] - 1
    ret_u = d["UUN"]["close"].pct_change().tail(120)
    ret_y = d["YCA"]["close"].pct_change().reindex(d["UUN"].index).tail(120)
    corr = float(ret_u.corr(ret_y))
    yca_stale = int((d["UUN"].index[-1] - d["YCA"].index[-1]).days)
    kills = []
    if dd < -KILL_DD:
        kills.append(f"drawdown {dd:.1%} < -12%")
    if corr < 0.3:
        kills.append(f"pair correlation {corr:.2f} < 0.3")
    if yca_stale > 5:
        kills.append(f"YCA data stale {yca_stale}d")
    if kills:
        state["killed"] = True
        print("KILL SWITCH:", "; ".join(kills))

    quotes, borrow = live_quotes(), borrow_snapshot()
    row = {
        "run_at_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "signal_date": str(sig_date.date()), "z": round(z_now, 3), "action": action,
        "position": (state["position"] or {}).get("side", 0),
        "sessions_held": (state["position"] or {}).get("sessions_held", ""),
        "equity_usd": round(equity, 2), "drawdown": round(dd, 4),
        "pair_corr_120d": round(corr, 3),
        "uun_spread_bps": quotes["UUN"]["spread_bps"], "yca_spread_bps": quotes["YCA"]["spread_bps"],
        "borrow_uun_pct": borrow["UUN"]["fee_pct"], "borrow_yca_pct": borrow["YCA"]["fee_pct"],
        "borrow_yca_avail": borrow["YCA"]["available"],
        "killed": state["killed"],
    }
    pd.DataFrame([row]).to_csv(LOG_F, mode="a", header=not LOG_F.exists(), index=False)
    state["last_run_date"] = str(sig_date.date())
    STATE_F.write_text(json.dumps(state, indent=2))

    print(f"\n=== paper run {row['run_at_utc']} ===")
    print(f"signal ({row['signal_date']}): z = {z_now:+.2f}  "
          f"[enter @ +/-{ENTRY_Z}, exit @ +/-{EXIT_Z}]")
    print(f"action: {action} | position: {row['position']} "
          f"({row['sessions_held']} sessions) | equity ${equity:,.2f} ({dd:+.2%} from peak)")
    if state["pending"]:
        p = state["pending"]
        print(f"staged: {p['action']} (side {p.get('side','-')}) executes at open of {p['execute_on']}")
    print(f"live spreads: UUN {quotes['UUN']['spread_bps']}bps / YCA {quotes['YCA']['spread_bps']}bps | "
          f"borrow: UUN {borrow['UUN']['fee_pct']}% / YCA {borrow['YCA']['fee_pct']}% "
          f"(avail {borrow['YCA']['available']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
