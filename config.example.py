"""
Bitget-Konfiguration — nach config.py kopieren und ausfüllen.

  cp config.example.py config.py

Dieselbe Schnittstelle wie bitget_bot_v2, damit die API-Keys des
Subaccounts at-HNKHNK direkt eingesetzt werden können:

  API_KEY, SECRET_KEY, PASSPHRASE, DEMO_MODE, DRY_RUN,
  PRODUCT_TYPE, MARGIN_MODE, MARGIN_COIN, SYMBOLS

config.py wird nicht committed (.gitignore).

PAPER ist der Default. Echte Orders nur wenn BEIDE Schalter gesetzt sind:
  DRY_RUN = False
  LIVE_TRADING = True
Ein altes V2-config.py mit DRY_RUN = False bleibt dadurch im Paper-Modus,
solange LIVE_TRADING fehlt.
"""

# ── API (gleiche Namen wie V2) ────────────────────────────────────────────────
API_KEY = "your_bitget_api_key"
SECRET_KEY = "your_bitget_secret_key"
PASSPHRASE = "your_bitget_passphrase"

# ── Markt ─────────────────────────────────────────────────────────────────────
PRODUCT_TYPE = "USDT-FUTURES"
MARGIN_MODE = "isolated"
MARGIN_COIN = "USDT"
# Hedge wie V2/V3: tradeSide open/close. One-Way nur wenn das Konto wirklich
# one-way ist ("one_way") — dann werden Exits mit reduceOnly=YES gesendet.
POS_MODE = "hedge"

# ── Symbole. Hebel wird auf MAX_LEVERAGE gedeckelt.
# Universum-Backtest 18.06.–16.10.2026, BTC/ETH/BNB ausgeschlossen, Default-Parameter.
# Nur Coins, die in den ersten 80 Tagen und in den letzten 40 Tagen nach Fees positiv waren.
# Reihenfolge: schwächerer der beiden Abschnitte. Details: backtest/universe_report.md
# DOGE und SUI sind Krypto-Perps. SNDK, INTC und ANTHROPIC sind Aktien-Perps auf Bitget.
SYMBOLS = [
    {"symbol": "DOGEUSDT", "leverage": 2},
    {"symbol": "SUIUSDT", "leverage": 2},
    {"symbol": "SNDKUSDT", "leverage": 2},
    {"symbol": "INTCUSDT", "leverage": 2},
    {"symbol": "ANTHROPICUSDT", "leverage": 2},
]

# ── Bot-Modus ─────────────────────────────────────────────────────────────────
DRY_RUN = True
LIVE_TRADING = False
DEMO_MODE = True  # paptrading-Header, nur relevant im Live-Modus
LOG_LEVEL = "INFO"
LOOP_INTERVAL = 20
PAPER_EQUITY = 50.0  # Fallback, wenn keine Keys / Paper ohne Kontostand

# ── Optional Telegram. Leer lassen = aus. Niemals Tokens committen. ──────────
TG_TOKEN = ""
TG_CHAT_ID = ""

# ── Risiko ────────────────────────────────────────────────────────────────────
MAX_LEVERAGE = 3
DEFAULT_LEVERAGE = 2
MAX_ACTIVE_GRIDS = 1
MAX_MARGIN_FRACTION = 0.50
MAX_INVENTORY_LEVELS = 3
DAILY_LOSS_PCT = 0.05
GRID_HARD_STOP_PCT = 0.06
BREAKOUT_BUFFER_PCT = 0.0025  # Stunden-Schluss jenseits Range + Puffer → Ausstieg
BREAKOUT_HARD_PCT = 0.01  # Preis jenseits Range + 1 % → sofort, auch innerhalb der Stunde
TAKER_SLIPPAGE_PCT = 0.0002
COOLDOWN_BARS = 6
FLATTEN_MAKER_TIMEOUT_S = 20

# ── Fees (Konto at-HNKHNK, Stand aus der Historie / Bitget-Defaults) ─────────
MAKER_FEE = 0.0002
TAKER_FEE = 0.0006
FEE_SPACING_MULT = 3.0  # Abstand >= 3 × Round-Trip-Maker
FUNDING_RATE_8H = 0.0001  # pauschaler Backtest-Abschlag, kein historisches Funding

# ── Regime (1h + 4h) ──────────────────────────────────────────────────────────
ADX_PERIOD = 14
ADX_MAX_1H = 22.0
ADX_MAX_4H = 25.0
BB_PERIOD = 20
BB_MULT = 2.0
BB_WIDTH_MAX = 0.06
ATR_PERIOD = 14
ATR_PCT_MAX = 0.015
ER_LOOKBACK = 24
ER_MAX = 0.35
# Optionale Hysterese für ein laufendes Grid. Default aus: Ausstieg, sobald ein
# Einstiegsfilter fehlt. Getestet wurden 6 / 0.15 / True — weniger Regime-
# Ausstiege, mehr Breakouts, nicht robust besser. backtest/exit_variants.md
ADX_EXIT_MARGIN = 0.0  # ADX-Ausstieg bei Schwelle + Aufschlag
ER_EXIT_MARGIN = 0.0  # ER-Ausstieg bei Schwelle + Aufschlag
EXIT_TREND_ONLY = False  # True: beim Halten nur ADX und ER, ohne Kompression/Kreuzungen
MIN_MID_CROSSES = 3
SWING_LOOKBACK = 48
MIN_RANGE_PCT = 0.008
MAX_RANGE_PCT = 0.08
EDGE_INSET = 0.15

# ── Grid ──────────────────────────────────────────────────────────────────────
GRID_LEVELS = 6
MIN_GRID_LEVELS = 3
LEVEL_NOTIONAL_FRACTION = 0.20
KILL_SWITCH = False
EXCHANGE_STOP = True
