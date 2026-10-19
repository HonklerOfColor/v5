"""Pairs-Trading: zwei verwandte Coins, dollar-neutral, Rückkehr des Log-Verhältnisses zum Mittel.

Spread = log(A) − log(B) auf 4h-Schlüssen. z = (Spread − Mittel) / Streuung über
lookback Kerzen. Bei z ≥ entry: A short, B long (und umgekehrt), beide Beine mit
gleichem Notional. Ausstieg bei |z| ≤ exit_z, Stop bei |z| ≥ stop_z, Zeitstopp
nach max_bars. Alles Taker. Funding je Bein mit Vorzeichen. Kein Hedge-Ratio
aus einer Regression: ein Verhältnis von 1 ist ausführbar und stabil, eine
geschätzte Beta wäre ein weiterer Freiheitsgrad.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from gridbot.candles import Candle, aggregate
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger


@dataclass(frozen=True)
class PairsParams:
    name: str = "pairs_30d"
    lookback_bars: int = 180  # 30 Tage auf 4h
    entry_z: float = 2.0
    exit_z: float = 0.5
    stop_z: float = 4.0
    max_bars: int = 90  # 15 Tage
    leg_fraction: float = 0.4  # Notional je Bein als Anteil des Kapitals


def _zscore(spread: list[float], i: int, look: int) -> float | None:
    if i + 1 < look:
        return None
    window = spread[i + 1 - look: i + 1]
    mean = sum(window) / look
    var = sum((s - mean) ** 2 for s in window) / look
    std = math.sqrt(var)
    if std <= 0:
        return None
    return (spread[i] - mean) / std


def half_life(spread: list[float]) -> float | None:
    """Halbwertszeit der Rückkehr in Kerzen (AR(1) auf Differenzen). None, wenn keine Rückkehr."""
    if len(spread) < 50:
        return None
    x = spread[:-1]
    y = [b - a for a, b in zip(spread[:-1], spread[1:])]
    mx = sum(x) / len(x)
    my = sum(y) / len(y)
    sxx = sum((a - mx) ** 2 for a in x)
    if sxx == 0:
        return None
    beta = sum((a - mx) * (b - my) for a, b in zip(x, y)) / sxx
    if beta >= 0:
        return None
    return -math.log(2) / math.log(1 + beta) if beta > -1 else 0.0


def run_pair(
    candles_a: list[Candle],
    candles_b: list[Candle],
    spec_a: ContractSpec,
    spec_b: ContractSpec,
    p: PairsParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    start_ts: int = 0,
) -> dict:
    bars_a = {b.ts: b for b in aggregate(candles_a, 4)}
    bars_b = {b.ts: b for b in aggregate(candles_b, 4)}
    stamps = sorted(set(bars_a) & set(bars_b))
    spread = [math.log(bars_a[t].close) - math.log(bars_b[t].close) for t in stamps]
    ledger = Ledger(equity0)
    pos: dict | None = None

    def leg_pnl(leg: dict, price: float) -> float:
        return (price - leg["entry"]) * leg["qty"] if leg["side"] == "long" else (leg["entry"] - price) * leg["qty"]

    def close_position(ts: int, reason: str) -> None:
        nonlocal pos
        assert pos is not None
        total = 0.0
        fees = 0.0
        for leg, bar in ((pos["a"], bars_a[ts]), (pos["b"], bars_b[ts])):
            fill = costs.taker_sell(bar.close) if leg["side"] == "long" else costs.taker_buy(bar.close)
            pnl = leg_pnl(leg, fill)
            fee = fill * leg["qty"] * costs.taker_fee
            total += pnl
            fees += fee
        ledger.fee(fees, True)
        ledger.realized += total
        ledger.equity += total - fees
        ledger.close_trade(total - fees - pos["entry_fee"] - pos["funding"], reason)
        pos = None

    for i, ts in enumerate(stamps):
        ledger.bars += 1
        z = _zscore(spread, i, p.lookback_bars)
        if pos is not None:
            ledger.bars_in_market += 1
            for leg, symbol, bar in ((pos["a"], spec_a.symbol, bars_a[ts]), (pos["b"], spec_b.symbol, bars_b[ts])):
                charge = costs.funding_charge(symbol, ts, leg["side"], leg["qty"] * bar.close)
                if charge:
                    ledger.funding += charge
                    ledger.equity -= charge
                    pos["funding"] += charge
            pos["bars"] += 1
            if z is None:
                pass
            elif pos["dir"] * z <= p.exit_z:
                close_position(ts, "ziel")
            elif pos["dir"] * z >= p.stop_z:
                close_position(ts, "stop")
            elif pos["bars"] >= p.max_bars:
                close_position(ts, "zeit")
        if pos is None and z is not None and ts >= start_ts and abs(z) >= p.entry_z:
            direction = 1 if z > 0 else -1  # +1: A zu teuer → A short, B long
            notional = ledger.equity * p.leg_fraction
            legs = {}
            ok = True
            for key, spec, bar, side in (
                ("a", spec_a, bars_a[ts], "short" if direction > 0 else "long"),
                ("b", spec_b, bars_b[ts], "long" if direction > 0 else "short"),
            ):
                qty = floor_to_step(notional / bar.close, spec.qty_step)
                if qty < spec.min_qty or qty * bar.close + 1e-9 < spec.min_notional:
                    ok = False
                    break
                fill = costs.taker_buy(bar.close) if side == "long" else costs.taker_sell(bar.close)
                legs[key] = {"side": side, "qty": qty, "entry": fill, "fee": fill * qty * costs.taker_fee}
            if not ok:
                ledger.exits["zu_klein"] = ledger.exits.get("zu_klein", 0) + 1
            else:
                fee = legs["a"]["fee"] + legs["b"]["fee"]
                ledger.fee(fee, True)
                ledger.equity -= fee
                pos = {"dir": direction, "a": legs["a"], "b": legs["b"], "entry_fee": fee, "funding": 0.0, "bars": 0}
        if pos is not None:
            unreal = leg_pnl(pos["a"], bars_a[ts].close) + leg_pnl(pos["b"], bars_b[ts].close)
            ledger.mark(ledger.equity + unreal)
        else:
            ledger.mark(ledger.equity)
    if pos is not None and stamps:
        close_position(stamps[-1], "ende")
        ledger.mark(ledger.equity)
    return ledger.result({"strategy": p.name, "half_life_bars": half_life(spread)})
