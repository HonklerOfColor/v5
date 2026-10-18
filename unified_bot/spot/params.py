"""Alle Parameter der Spot-Module an einer Stelle.

Quelle und Verbindlichkeit:
- docs/spot_modules/PREREG_trend_ensemble.md  (Trend-Ensemble, Primärvariante)
- docs/spot_modules/PREREG_trendfilter_dca.md (Trendfilter BTC+ETH, Test 1 Primärvariante)
- docs/spot_modules/SPEC.md                   (Kosten, Alarme, Kapital)
- docs/spot_modules/code/lib.py, tf.py        (Referenz-Implementierung)

Nichts hier wird nachoptimiert. Wer einen Wert ändert, ändert die Strategie.
"""

from __future__ import annotations

import math

DAY_MS = 86_400_000

# ── Takt ─────────────────────────────────────────────────────────────────────
# Bitget "1day" ist UTC+8-ausgerichtet (Schluss 16:00 UTC). "1Dutc" schließt um
# 00:00 UTC, wie PREREG ("Schlusskurs 00:00 UTC") verlangt.
GRANULARITY = "1Dutc"
RUN_AFTER_UTC_MINUTES = 5       # SPEC: "kurz nach 00:00 UTC", Puffer 00:05
RETRY_AFTER_MINUTES = 10        # fehlende Kerze oder API-Fehler: später noch einmal
MAX_SKIPPED_DAYS_FOR_FLAGS = 7  # Flags werden über ausgelassene Tage zusammengefasst

# ── Kosten (PREREG "Kosten (Bitget)": Spot 0,10 % + Slippage 0,05 % je Seite) ──
FEE_RATE = 0.0010
SLIPPAGE_RATE = 0.0005
COST_PER_SIDE = FEE_RATE + SLIPPAGE_RATE   # 0,0015, wie COST["spot"] in runA.py / tf.py

# ── Rebalance-Schwelle (beide Module, PREREG: "> 20 % relativ") ───────────────
REBALANCE_THRESHOLD = 0.20

# ── Modul 1: spot_trend_ensemble (PREREG_trend_ensemble.md, Abschnitt A) ──────
TREND_ID = "spot_trend_ensemble"
TREND_WINDOWS = (5, 10, 20, 30, 60, 90, 150, 250, 360)   # "alle 9 Fenster"
TREND_B = 10                                              # Top-B, je Coin 1/B
TREND_VT = 0.25                                           # VT 25 %
TREND_CAP = 1.0                                           # Cap 1,0 (Spot, kein Hebel)
TREND_SIGMA_DAYS = 90                                     # σ90
TREND_ANNUALIZE = math.sqrt(365)                          # "annualisiert mit √365"
TREND_MIN_HISTORY_DAYS = 60                               # "mind. 60 Handelstage Historie"
TREND_UNIVERSE_VOLUME_DAYS = 30                           # "Median-Quote-Volumen der letzten 30 Tage"
TREND_UNIVERSE_VOLUME_MIN_PERIODS = 20                    # lib.universe: rolling(30, min_periods=20)
TREND_UNIVERSE_MIN_MEDIAN_USDT = 2_000_000.0              # lib.universe: min_med=2e6 (Default der Referenz)
TREND_UNIVERSE_PREFILTER = 100   # Umsetzung: Kandidaten = Top-100 nach 24h-USDT-Volumen (Ticker),
                                 # darauf die exakte Median-Regel. Bitget hat >3000 USDT-Paare.
TREND_LOOKBACK_DAYS = 1000       # Kerzen je Coin für Donchian-Zustand (längstes Fenster 360 + σ90)
TREND_UNIVERSE_CANDLES = 100     # Kerzen je Kandidat für Median-30 und 60-Tage-Regel
TREND_DEFAULT_MIN_ORDER_USDT = 10.0   # PREREG: "unbekannte/delistete Symbole: Spot 10 USDT"
# lib.EXPL: Stablecoins/Fiat, Gold, Wrapped, Index, Tokenized Stocks, Leveraged
TREND_EXCLUDED_BASES = frozenset(
    """XAU XAG PAXG XAUT CL BZ DEFI BTCDOM USDC BUSD TUSD USDP PAX DAI FDUSD USDE USD1 RLUSD PYUSD EUR EURI AEUR GBP AUD BRL TRY
UST XUSD U WBTC WBETH BETH SUSD USDS BFUSD TSLA NVDA MSTR INTC QQQ SPY SAMSUNG SKHYNIX SKHY SNDK SOXL SOXS SPCX MRVL CRCL MU EWY SNXX
DRAM KORU AAPL AMZN GOOGL META MSFT COIN HOOD DOTECO FOOTBALL BLUEBIRD""".split()
)
TREND_LOW_VOL_ANNUAL = 0.05          # lib.excl_set: Jahresvola < 5 % → Stablecoin-artig
TREND_WEEKEND_RATIO = 0.4            # lib.excl_set: Wochenend-/Werktagsbewegung < 0,4 → Tokenized Stock
TREND_WEEKEND_RULE_FROM_DAY = 20089  # 2025-01-01 als UTC-Tagesnummer (lib: "erst ab 2025")
TREND_ALARM_DRAWDOWN = 0.15          # SPEC: Drawdown > 15 %
TREND_ALARM_DEVIATION_PP = 3.0       # SPEC: Paper vs. Schatten > 3 Prozentpunkte über 3 Monate

# ── Modul 2: spot_trendfilter_btceth (PREREG_trendfilter_dca.md, Test 1) ─────
TF_ID = "spot_trendfilter_btceth"
TF_SYMBOLS = ("BTCUSDT", "ETHUSDT")
TF_SLEEVE = 0.5                                   # 50 % BTC, 50 % ETH
TF_SMA_WINDOWS = (20, 50, 100, 150, 200)          # Ensemble = Mittel der Binärsignale Close > SMA(n)
TF_LOOKBACK_DAYS = 300                            # SMA200 + Puffer
TF_DEFAULT_MIN_ORDER_USDT = 1.0                   # PREREG: "Mindestorder Bitget Spot: 1 USDT (BTC/ETH)"
TF_ALARM_DRAWDOWN = 0.50                          # SPEC: Drawdown > 50 %
TF_ALARM_DEVIATION_PP = 5.0                       # SPEC: > 5 Prozentpunkte über 3 Monate
TF_ALARM_TRADES_PER_MONTH = 25                    # SPEC: > 25 Trades/Monat

# ── Gemeinsam ─────────────────────────────────────────────────────────────────
ALARM_WINDOW_DAYS = 90            # "über 3 Monate"
DEFAULT_CAPITAL_USDT = 500.0      # SPEC: Vorschlag je Modul 500 USDT
EQUITY_HISTORY_DAYS = 1500        # Tagesreihe im Zustand (Paper und Schatten)
