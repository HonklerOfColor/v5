"""Range-Filter. Kein Grid, solange eine Bedingung fehlt.

Für ein laufendes Grid (holding=True) gibt es optional eine Hysterese:
ADX- und ER-Schwelle plus Aufschlag, und mit EXIT_TREND_ONLY zählen beim
Halten nur ADX und ER. Default ist aus — dieselben Filter wie beim Einstieg.
Im Vergleich vom 18.10.2026 (backtest/exit_variants.md) tauschte die Hysterese
Regime-Ausstiege gegen Breakouts, ohne robust besser zu sein.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from gridbot.candles import Candle, aggregate
from gridbot.indicators import adx, atr_pct, bb_width, efficiency_ratio, mid_crosses
from gridbot.params import GridParams

REASON_DE = {
    "zu_wenig_daten": "zu wenig Kerzen",
    "adx_1h": "ADX 1h über der Range-Schwelle",
    "adx_4h": "ADX 4h über der Range-Schwelle",
    "efficiency": "Preispfad zu gerichtet (Efficiency Ratio)",
    "keine_kompression": "weder Bollinger-Bandbreite noch ATR komprimiert",
    "zu_wenig_kreuzungen": "zu wenige Mittelkreuzungen im Fenster",
}


@dataclass
class Regime:
    ranging: bool
    reasons: list[str] = field(default_factory=list)
    adx_1h: float | None = None
    adx_4h: float | None = None
    bb_width: float | None = None
    atr_pct: float | None = None
    efficiency: float | None = None
    crosses: int = 0

    def reason_text(self) -> str:
        if self.ranging:
            return "Range"
        return ", ".join(REASON_DE.get(item, item) for item in self.reasons)


def assess(
    candles_1h: list[Candle],
    candles_4h: list[Candle] | None,
    params: GridParams,
    holding: bool = False,
) -> Regime:
    """holding=True: Prüfung für ein laufendes Grid, mit den Ausstiegsschwellen."""
    trend_only = holding and params.exit_trend_only
    higher = candles_4h if candles_4h is not None else aggregate(candles_1h, 4)
    if len(candles_1h) < params.min_bars_1h or len(higher) < params.min_bars_4h:
        return Regime(False, ["zu_wenig_daten"])
    closes = [candle.close for candle in candles_1h]
    adx_1h = adx(candles_1h, params.adx_period)
    adx_4h = adx(higher, params.adx_period)
    width = bb_width(closes, params.bb_period, params.bb_mult)
    atr_ratio = atr_pct(candles_1h, params.atr_period)
    efficiency = efficiency_ratio(closes, params.er_lookback)
    crosses = mid_crosses(candles_1h, min(params.swing_lookback, len(candles_1h)))
    adx_cap_1h = params.adx_max_1h + (params.adx_exit_margin if holding else 0.0)
    adx_cap_4h = params.adx_max_4h + (params.adx_exit_margin if holding else 0.0)
    er_cap = params.er_max + (params.er_exit_margin if holding else 0.0)
    reasons: list[str] = []
    if adx_1h is None or adx_1h >= adx_cap_1h:
        reasons.append("adx_1h")
    if adx_4h is None or adx_4h >= adx_cap_4h:
        reasons.append("adx_4h")
    if efficiency is None or efficiency >= er_cap:
        reasons.append("efficiency")
    compressed = (
        width is not None and width <= params.bb_width_max
    ) or (
        atr_ratio is not None and atr_ratio <= params.atr_pct_max
    )
    if not trend_only and not compressed:
        reasons.append("keine_kompression")
    if not trend_only and crosses < params.min_mid_crosses:
        reasons.append("zu_wenig_kreuzungen")
    return Regime(
        ranging=not reasons,
        reasons=reasons,
        adx_1h=adx_1h,
        adx_4h=adx_4h,
        bb_width=width,
        atr_pct=atr_ratio,
        efficiency=efficiency,
        crosses=crosses,
    )
