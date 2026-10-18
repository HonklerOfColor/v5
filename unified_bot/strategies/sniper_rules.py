"""V3-Signal und die Größen-Gates. Entries bleiben pausiert, bis sie bewusst angehen."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

VIENNA = ZoneInfo("Europe/Vienna")
# V3 sperrt 2–4 / 14 / 17 / 20 / 22. Stunde 0 und 1 sind die V1-Erweiterung, nicht V3.
BLOCKED_ENTRY_HOURS = frozenset({2, 3, 4, 14, 17, 20, 22})
IMBALANCE_LONG = 1.4
IMBALANCE_SHORT = 0.7
SL_ATR_MULT = 1.3
TP_ATR_MULT = 2.0
LEVERAGE = 3
RISK_PCT = 0.003
MAX_POSITIONS = 2
LONG_ONLY = True


def vienna_hour(epoch_s: float) -> int:
    return datetime.fromtimestamp(epoch_s, VIENNA).hour


def entry_hour_blocked(epoch_s: float) -> bool:
    return vienna_hour(epoch_s) in BLOCKED_ENTRY_HOURS


def imbalance_ratio(bids: list, asks: list, depth: int = 10) -> float:
    bid_vol = sum(float(level[1]) for level in bids[:depth])
    ask_vol = sum(float(level[1]) for level in asks[:depth])
    if ask_vol == 0:
        return 999.0 if bid_vol > 0 else 0.0
    return bid_vol / ask_vol


def trend_from_closes(closes: list[float]) -> str:
    """Wie der Live-Bot: Mittel der letzten 20 Schlüsse, nicht ein echtes EMA."""
    if len(closes) < 20:
        return "NEUTRAL"
    window = closes[-20:]
    mean = sum(window) / 20.0
    last = closes[-1]
    if last > mean:
        return "LONG"
    if last < mean:
        return "SHORT"
    return "NEUTRAL"


def update_sweep(state: dict, best_bid: float, best_ask: float, last_px: float, now_s: float) -> tuple[dict, str | None]:
    """Zustandsautomat über mehrere Polls. Rückgabe ist der neue Zustand und LONG/SHORT/None."""
    st = {
        "below_bid": bool(state.get("below_bid", False)),
        "above_ask": bool(state.get("above_ask", False)),
        "since": float(state.get("since", now_s)),
    }
    if last_px < best_bid:
        st["below_bid"] = True
        st["since"] = now_s
    if last_px > best_ask:
        st["above_ask"] = True
        st["since"] = now_s
    if st["below_bid"] and last_px >= best_bid:
        return {"below_bid": False, "above_ask": False, "since": now_s}, "LONG"
    if st["above_ask"] and last_px <= best_ask:
        return {"below_bid": False, "above_ask": False, "since": now_s}, "SHORT"
    if now_s - st["since"] > 60:
        st["below_bid"] = False
        st["above_ask"] = False
    return st, None


def sniper_side(imbalance: float, trend: str, sweep: str | None, hour_blocked: bool) -> str | None:
    """Long-only. Shorts sind seit dem Live-Learning aus, auch wenn der Sweep short ist."""
    if hour_blocked or sweep != "LONG":
        return None
    if imbalance > IMBALANCE_LONG and trend == "LONG":
        return "long"
    return None
