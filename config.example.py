"""
Bitget — ein Konto für alle Strategien. Nach config.py kopieren.

  cp config.example.py config.py

config.py steht in .gitignore. Keine echten Keys ins Repo.

Paper ist der Default. Echte Orders nur wenn BEIDE Schalter gesetzt sind
und der Prozess mit --live gestartet wird:

  DRY_RUN = False
  LIVE_TRADING = True
  python -m unified_bot --live
"""

# ── API. Platzhalter reichen für Paper. ──────────────────────────────────────
API_KEY = "your_bitget_api_key"
SECRET_KEY = "your_bitget_secret_key"
PASSPHRASE = "your_bitget_passphrase"

# ── Markt. Hedge ist Pflicht (ein Konto, mehrere Strategien). ────────────────
PRODUCT_TYPE = "USDT-FUTURES"
MARGIN_MODE = "isolated"
MARGIN_COIN = "USDT"
POS_MODE = "hedge"

# ── Modus ─────────────────────────────────────────────────────────────────────
DRY_RUN = True
LIVE_TRADING = False
DEMO_MODE = False
LOG_LEVEL = "INFO"
LOOP_INTERVAL = 20
PAPER_EQUITY = 100.0
STATUS_HOST = "0.0.0.0"
STATUS_PORT = 8767

# ── Telegram. Leer = aus. Alternativ TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID. ─
TELEGRAM_BOT_TOKEN = ""
TELEGRAM_CHAT_ID = ""

# ── Globales Risiko ───────────────────────────────────────────────────────────
GLOBAL_MAX_LEVERAGE = 5
MAX_TOTAL_EXPOSURE = 1.5
DAILY_LOSS_PCT = 0.05
KILL_SWITCH = False
MAKER_FEE = 0.0002
TAKER_FEE = 0.0006
FEE_TP_MULT = 3.0
MIN_NOTIONAL_USDT = 5.0
TAKER_SLIPPAGE_PCT = 0.0002
FUNDING_RATE_8H = 0.0001

# ── Grid-Feinschliff (Sleeve, nicht das ganze Konto) ─────────────────────────
MAX_ACTIVE_GRIDS = 1
MAX_MARGIN_FRACTION = 0.50
MAX_INVENTORY_LEVELS = 3
GRID_HARD_STOP_PCT = 0.06
BREAKOUT_BUFFER_PCT = 0.0025
COOLDOWN_BARS = 6
FEE_SPACING_MULT = 3.0
GRID_LEVELS = 6
MIN_GRID_LEVELS = 3
LEVEL_NOTIONAL_FRACTION = 0.20

# Allokationen zusammen höchstens 1.0. 0 heißt: Sleeve leer, keine Entries.
# enabled=False und entries_paused=True ist die ENTRIES_PAUSED-Semantik.
STRATEGIES = {
    "grid": {
        "enabled": True,
        "entries_paused": False,
        "allocation": 0.50,
        "symbols": ["DOGEUSDT", "SUIUSDT", "SNDKUSDT", "INTCUSDT", "ANTHROPICUSDT"],
        "leverage": 2,
        "max_leverage": 3,
        "priority": 10,
    },
    "reversal": {
        "enabled": False,
        "entries_paused": True,
        "allocation": 0.0,
        "symbols": ["BTCUSDT", "ETHUSDT", "BNBUSDT"],
        "leverage": 3,
        "max_leverage": 3,
        "priority": 20,
    },
    "sniper": {
        "enabled": False,
        "entries_paused": True,
        "allocation": 0.0,
        "symbols": ["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "HYPEUSDT"],
        "leverage": 3,
        "max_leverage": 3,
        "risk_pct": 0.003,
        "max_positions": 2,
        "priority": 30,
    },
    "trendjoin": {
        "enabled": False,
        "entries_paused": True,
        "allocation": 0.0,
        "symbols": [],
        "leverage": 5,
        "max_leverage": 5,
        "risk_pct": 0.01,
        "max_positions": 3,
        "max_trades_per_day": 5,
        "priority": 40,
    },
    "funding_arb": {
        "enabled": False,
        "entries_paused": True,
        "allocation": 0.0,
        "symbols": [],
        "leverage": 1,
        "max_leverage": 3,
        "priority": 50,
    },
    "daily_trend": {
        "enabled": False,
        "entries_paused": True,
        "allocation": 0.0,
        "symbols": [],
        "leverage": 2,
        "max_leverage": 3,
        "priority": 60,
    },
}
