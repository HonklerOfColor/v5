"""Cash-and-Carry: Spot long, Perp short, Funding kassieren. Kein Kursrisiko, nur Funding-Risiko.

Jeden Montag 00:00 UTC wird unter den Kandidaten der Coin mit dem höchsten
Funding der letzten 7 Tage gewählt. Liegt dessen Funding annualisiert unter
min_annual, bleibt das Kapital in Cash. Ein Wechsel kostet beide Beine:
Spot-Fee je Seite, Perp-Taker plus Slippage je Seite. Das Kapital wird je zur
Hälfte auf Spot (1×) und Perp-Margin gelegt; Perp-Notional ist deshalb
equity / 2 (bei Hebel 2 bleibt die Hälfte der Perp-Margin als Puffer).
Basis-Schwankungen zwischen Spot und Perp werden ignoriert.
"""

from __future__ import annotations

from dataclasses import dataclass

from research.momentum import is_rebalance


@dataclass(frozen=True)
class CarryParams:
    name: str = "carry_7d"
    spot_fee: float = 0.001  # Bitget Spot Standard; die API nennt 0,2 %, mit BGB-Rabatt 0,1 %
    perp_taker: float = 0.0006
    slippage: float = 0.0002
    min_annual: float = 0.03
    lookback_days: int = 7


def annualize(rates: list[float], days: float) -> float:
    if days <= 0:
        return 0.0
    return sum(rates) / days * 365.0


def run_carry(
    funding_books: dict[str, dict[int, float]],
    p: CarryParams,
    equity0: float,
    start_ts: int,
    end_ts: int,
    candidates: list[str] | None = None,
) -> dict:
    symbols = candidates or list(funding_books)
    stamps = sorted({ts for s in symbols for ts in funding_books[s] if start_ts <= ts <= end_ts})
    equity = equity0
    held: str | None = None
    switches = 0
    income = 0.0
    fees = 0.0
    weeks_in_cash = 0
    weeks = 0
    per_symbol: dict[str, float] = {}
    switch_cost = 2 * p.spot_fee + 2 * (p.perp_taker + p.slippage)  # Einstieg und Ausstieg, beide Beine
    peak = equity0
    max_dd = 0.0

    def leg_notional() -> float:
        return equity / 2.0

    for ts in stamps:
        if held is not None:
            rate = funding_books[held].get(ts)
            if rate is not None:
                gain = rate * leg_notional()
                income += gain
                equity += gain
                per_symbol[held] = per_symbol.get(held, 0.0) + gain
        if is_rebalance(ts, 7):
            weeks += 1
            window_start = ts - p.lookback_days * 86_400_000
            best, best_rate = None, -1.0
            for s in symbols:
                rates = [r for t, r in funding_books[s].items() if window_start < t <= ts]
                if len(rates) < 3 * p.lookback_days * 0.5:
                    continue
                annual = annualize(rates, p.lookback_days)
                if annual > best_rate:
                    best, best_rate = s, annual
            target = best if best is not None and best_rate >= p.min_annual else None
            if target != held:
                if held is not None:
                    cost = leg_notional() * (p.spot_fee + p.perp_taker + p.slippage)
                    fees += cost
                    equity -= cost
                if target is not None:
                    cost = leg_notional() * (p.spot_fee + p.perp_taker + p.slippage)
                    fees += cost
                    equity -= cost
                    switches += 1
                held = target
            if held is None:
                weeks_in_cash += 1
        peak = max(peak, equity)
        max_dd = max(max_dd, (peak - equity) / peak if peak > 0 else 0.0)
    if held is not None:
        cost = leg_notional() * (p.spot_fee + p.perp_taker + p.slippage)
        fees += cost
        equity -= cost
    return {
        "strategy": p.name,
        "net": equity - equity0,
        "end_equity": equity,
        "income": income,
        "fees": fees,
        "switches": switches,
        "weeks": weeks,
        "weeks_in_cash": weeks_in_cash,
        "max_drawdown_pct": max_dd * 100.0,
        "per_symbol": per_symbol,
    }
