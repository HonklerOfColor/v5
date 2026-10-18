"""Bollinger-Mean-Reversion auf 1h-Kerzen mit Post-only-Einstieg und Maker-Ziel.

Nach jeder geschlossenen Stundenkerze liegt ein Limit-Buy am unteren Band und
ein Limit-Sell am oberen Band (BB 20, 2). Füllt die nächste Kerze das Limit
(Docht reicht), ist die Lage offen — dieselbe optimistische Fill-Annahme wie
im Grid-Backtest. Ziel ist der gleitende Mittelwert als Maker-Limit, das jede
Stunde nachgezogen wird. Stop: Schluss weiter als k × ATR jenseits des Einstiegs
(Taker). Zeitstopp nach max_hold Stunden (Taker). Optionaler Filter: kein
Einstieg gegen den 4h-Trend (ADX 4h über Schwelle und DI in Gegenrichtung).
"""

from __future__ import annotations

from dataclasses import dataclass

from gridbot.candles import Candle
from gridbot.specs import ContractSpec, floor_to_step
from research.costs import Costs
from research.metrics import Ledger
from research.trend import atr_series


@dataclass(frozen=True)
class MeanRevParams:
    name: str = "bb_meanrev"
    bb_period: int = 20
    bb_mult: float = 2.0
    atr_period: int = 14
    atr_stop_mult: float = 1.5
    max_hold: int = 36
    risk_pct: float = 0.01
    max_margin_fraction: float = 0.5
    adx_filter: float = 0.0  # 0 = aus; sonst kein Einstieg gegen einen 1h-ADX-Trend über der Schwelle
    adx_period: int = 14


def _bands(closes: list[float], i: int, period: int, mult: float) -> tuple[float, float, float] | None:
    if i + 1 < period:
        return None
    window = closes[i + 1 - period: i + 1]
    mid = sum(window) / period
    var = sum((c - mid) ** 2 for c in window) / period
    std = var ** 0.5
    return mid - mult * std, mid, mid + mult * std


def _adx_di_series(candles: list[Candle], period: int) -> list[tuple[float, float, float] | None]:
    from gridbot.indicators import _true_ranges, _wilder

    trs, plus, minus = _true_ranges(candles)
    out: list[tuple[float, float, float] | None] = [None] * len(candles)
    if len(trs) < period:
        return out
    atr_s = _wilder(trs, period)
    plus_s = _wilder(plus, period)
    minus_s = _wilder(minus, period)
    dxs: list[float] = []
    pdis: list[float] = []
    mdis: list[float] = []
    for atr_v, p_v, m_v in zip(atr_s, plus_s, minus_s):
        if atr_v <= 0:
            dxs.append(0.0)
            pdis.append(0.0)
            mdis.append(0.0)
            continue
        pdi = 100.0 * p_v / atr_v
        mdi = 100.0 * m_v / atr_v
        denom = pdi + mdi
        dxs.append(0.0 if denom == 0 else 100.0 * abs(pdi - mdi) / denom)
        pdis.append(pdi)
        mdis.append(mdi)
    smoothed = _wilder(dxs, period)
    # dxs[k] gehört zu candles[period + k]; smoothed[j] zu candles[2*period + j - 1 + 1]
    offset = 2 * period
    for j, value in enumerate(smoothed):
        idx = offset + j
        if idx < len(candles):
            out[idx] = (value, pdis[period - 1 + j], mdis[period - 1 + j])
    return out


def run_meanrev(
    candles: list[Candle],
    spec: ContractSpec,
    p: MeanRevParams,
    costs: Costs,
    equity0: float,
    leverage: int = 2,
    start_index: int = 0,
) -> dict:
    closes = [c.close for c in candles]
    atrs = atr_series(candles, p.atr_period)
    adx = _adx_di_series(candles, p.adx_period) if p.adx_filter > 0 else [None] * len(candles)
    ledger = Ledger(equity0)
    pos: dict | None = None
    warm = max(p.bb_period, p.atr_period + 1, 3 * p.adx_period) + 1

    def close_position(price: float, reason: str, taker: bool) -> None:
        nonlocal pos
        assert pos is not None
        if pos["side"] == "long":
            fill = costs.taker_sell(price) if taker else price
            pnl = (fill - pos["entry"]) * pos["qty"]
        else:
            fill = costs.taker_buy(price) if taker else price
            pnl = (pos["entry"] - fill) * pos["qty"]
        fee = fill * pos["qty"] * (costs.taker_fee if taker else costs.maker_fee)
        ledger.fee(fee, taker)
        ledger.realized += pnl
        ledger.equity += pnl - fee
        ledger.close_trade(pnl - fee - pos["entry_fee"] - pos["funding"], reason)
        pos = None

    pending: dict | None = None  # Limits aus der Vorkerze
    for i in range(warm, len(candles)):
        bar = candles[i]
        ledger.bars += 1
        if pos is not None:
            ledger.bars_in_market += 1
            charge = costs.funding_charge(spec.symbol, bar.ts, pos["side"], pos["qty"] * bar.close)
            if charge:
                ledger.funding += charge
                ledger.equity -= charge
                pos["funding"] += charge
            pos["bars"] += 1
            target = pos["target"]
            if pos["side"] == "long" and bar.high >= target:
                close_position(target, "ziel", taker=False)
            elif pos["side"] == "short" and bar.low <= target:
                close_position(target, "ziel", taker=False)
            else:
                stop = pos["stop"]
                if (pos["side"] == "long" and bar.close <= stop) or (pos["side"] == "short" and bar.close >= stop):
                    close_position(bar.close, "stop", taker=True)
                elif pos["bars"] >= p.max_hold:
                    close_position(bar.close, "zeit", taker=True)
                else:
                    bands = _bands(closes, i, p.bb_period, p.bb_mult)
                    if bands:
                        pos["target"] = bands[1]
        elif pending is not None and bar.ts >= candles[start_index].ts:
            side = None
            if bar.low <= pending["buy"] and bar.high >= pending["sell"]:
                side = None  # beide berührt, Reihenfolge unbekannt: auslassen
            elif bar.low <= pending["buy"] and pending["long_ok"]:
                side = "long"
            elif bar.high >= pending["sell"] and pending["short_ok"]:
                side = "short"
            if side is not None:
                price = pending["buy"] if side == "long" else pending["sell"]
                # Eröffnung jenseits des Limits: Post-only wäre abgelehnt worden
                if (side == "long" and bar.open <= price) or (side == "short" and bar.open >= price):
                    side = None
            if side is not None:
                stop_dist = p.atr_stop_mult * pending["atr"]
                risk = ledger.equity * p.risk_pct
                qty = min(risk / stop_dist, ledger.equity * p.max_margin_fraction * leverage / price)
                qty = floor_to_step(qty, spec.qty_step)
                if qty >= spec.min_qty and qty * price + 1e-9 >= spec.min_notional:
                    fee = price * qty * costs.maker_fee
                    ledger.fee(fee, False)
                    ledger.equity -= fee
                    pos = {
                        "side": side,
                        "qty": qty,
                        "entry": price,
                        "stop": price - stop_dist if side == "long" else price + stop_dist,
                        "target": pending["mid"],
                        "entry_fee": fee,
                        "funding": 0.0,
                        "bars": 0,
                    }
                    # Stop schon in der Einstiegskerze?
                    if (side == "long" and bar.close <= pos["stop"]) or (side == "short" and bar.close >= pos["stop"]):
                        close_position(bar.close, "stop", taker=True)
                else:
                    ledger.exits["zu_klein"] = ledger.exits.get("zu_klein", 0) + 1
        # Limits für die nächste Kerze
        pending = None
        if pos is None:
            bands = _bands(closes, i, p.bb_period, p.bb_mult)
            atr_now = atrs[i]
            if bands and atr_now:
                long_ok = short_ok = True
                if p.adx_filter > 0 and adx[i] is not None:
                    value, pdi, mdi = adx[i]
                    if value >= p.adx_filter:
                        long_ok = pdi >= mdi
                        short_ok = mdi >= pdi
                pending = {
                    "buy": bands[0],
                    "mid": bands[1],
                    "sell": bands[2],
                    "atr": atr_now,
                    "long_ok": long_ok,
                    "short_ok": short_ok,
                }
        if pos is not None:
            unreal = (bar.close - pos["entry"]) * pos["qty"] if pos["side"] == "long" else (pos["entry"] - bar.close) * pos["qty"]
            ledger.mark(ledger.equity + unreal)
        else:
            ledger.mark(ledger.equity)

    if pos is not None and candles:
        close_position(candles[-1].close, "ende", taker=True)
        ledger.mark(ledger.equity)
    return ledger.result({"strategy": p.name})
