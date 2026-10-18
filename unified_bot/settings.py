"""Defaults und das Laden von config.py. Paper, solange nicht beide Live-Schalter an sind."""

from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from types import SimpleNamespace


def _placeholder(value: str) -> bool:
    text = (value or "").strip()
    if not text:
        return True
    return text.startswith("your_") or "your_bitget" in text


@dataclass
class StrategySettings:
    strategy_id: str
    enabled: bool
    entries_paused: bool
    allocation: float
    symbols: list[str]
    leverage: int
    max_leverage: int
    risk_pct: float
    max_positions: int
    max_trades_per_day: int
    priority: int
    note: str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class Settings:
    mode: str
    api_key: str
    secret_key: str
    passphrase: str
    demo_mode: bool
    product_type: str
    margin_mode: str
    margin_coin: str
    pos_mode: str
    paper_equity: float
    global_max_leverage: int
    max_total_exposure: float
    daily_loss_pct: float
    kill_switch: bool
    maker_fee: float
    taker_fee: float
    fee_tp_mult: float
    min_notional_usdt: float
    taker_slippage_pct: float
    funding_rate_8h: float
    loop_interval: int
    status_host: str
    status_port: int
    log_level: str
    telegram_token: str
    telegram_chat_id: str
    account_uid: str
    account_name: str
    strategies: dict[str, StrategySettings]
    grid: dict = field(default_factory=dict)

    def strategy(self, strategy_id: str) -> StrategySettings:
        return self.strategies[strategy_id]

    def keys_look_real(self) -> bool:
        if _placeholder(self.api_key) or _placeholder(self.secret_key) or _placeholder(self.passphrase):
            return False
        return True


def default_strategies() -> dict[str, StrategySettings]:
    """Grid im Paper an. V1/V3 portiert und aus. V4 und die Recherche-Slots zu."""
    return {
        "grid": StrategySettings(
            strategy_id="grid",
            enabled=True,
            entries_paused=False,
            allocation=0.50,
            symbols=["DOGEUSDT", "SUIUSDT", "SNDKUSDT", "INTCUSDT", "ANTHROPICUSDT"],
            leverage=2,
            max_leverage=3,
            risk_pct=0.0,
            max_positions=1,
            max_trades_per_day=0,
            priority=10,
            note="Paper an. Ein Grid zur Zeit, Post-only, Hebel 2, Deckel 3.",
        ),
        "reversal": StrategySettings(
            strategy_id="reversal",
            enabled=False,
            entries_paused=True,
            allocation=0.0,
            symbols=["BTCUSDT", "ETHUSDT", "BNBUSDT"],
            leverage=3,
            max_leverage=3,
            risk_pct=0.0,
            max_positions=3,
            max_trades_per_day=0,
            priority=20,
            note="V1 Reversal. Backtest ohne Edge, deshalb aus.",
        ),
        "sniper": StrategySettings(
            strategy_id="sniper",
            enabled=False,
            entries_paused=True,
            allocation=0.0,
            symbols=["BTCUSDT", "ETHUSDT", "SOLUSDT", "BNBUSDT", "HYPEUSDT"],
            leverage=3,
            max_leverage=3,
            risk_pct=0.003,
            max_positions=2,
            max_trades_per_day=0,
            priority=30,
            note="V3 Sniper. ENTRIES_PAUSED, netto negativ nach Fees.",
        ),
        "trendjoin": StrategySettings(
            strategy_id="trendjoin",
            enabled=False,
            entries_paused=True,
            allocation=0.0,
            symbols=[],
            leverage=5,
            max_leverage=5,
            risk_pct=0.01,
            max_positions=3,
            max_trades_per_day=5,
            priority=40,
            note="V4 TrendJoin. Repo leer, Regeln aktiv, Signal TODO.",
        ),
        "funding_arb": StrategySettings(
            strategy_id="funding_arb",
            enabled=False,
            entries_paused=True,
            allocation=0.0,
            symbols=[],
            leverage=1,
            max_leverage=3,
            risk_pct=0.0,
            max_positions=0,
            max_trades_per_day=0,
            priority=50,
            note="Slot: Funding-Arbitrage Spot+Perp, in Recherche.",
        ),
        "daily_trend": StrategySettings(
            strategy_id="daily_trend",
            enabled=False,
            entries_paused=True,
            allocation=0.0,
            symbols=[],
            leverage=2,
            max_leverage=3,
            risk_pct=0.0,
            max_positions=0,
            max_trades_per_day=1,
            priority=60,
            note="Slot: Daily Trend Following, in Recherche.",
        ),
    }


def _grid_defaults() -> dict:
    return {
        "max_active_grids": 1,
        "max_margin_fraction": 0.50,
        "max_inventory_levels": 3,
        "hard_stop_pct": 0.06,
        "breakout_buffer_pct": 0.0025,
        "cooldown_bars": 6,
        "fee_spacing_mult": 3.0,
        "grid_levels": 6,
        "min_grid_levels": 3,
        "level_notional_fraction": 0.20,
        "adx_max_1h": 22.0,
        "adx_max_4h": 25.0,
    }


def base_settings() -> Settings:
    return Settings(
        mode="paper",
        api_key="",
        secret_key="",
        passphrase="",
        demo_mode=False,
        product_type="USDT-FUTURES",
        margin_mode="isolated",
        margin_coin="USDT",
        pos_mode="hedge",
        paper_equity=100.0,
        global_max_leverage=5,
        max_total_exposure=1.5,
        daily_loss_pct=0.05,
        kill_switch=False,
        maker_fee=0.0002,
        taker_fee=0.0006,
        fee_tp_mult=3.0,
        min_notional_usdt=5.0,
        taker_slippage_pct=0.0002,
        funding_rate_8h=0.0001,
        loop_interval=20,
        status_host="0.0.0.0",
        status_port=8767,
        log_level="INFO",
        telegram_token="",
        telegram_chat_id="",
        account_uid="9711026741",
        account_name="at-HNK",
        strategies=default_strategies(),
        grid=_grid_defaults(),
    )


def _get(cfg: object | None, name: str, default):
    if cfg is None or not hasattr(cfg, name):
        return default
    value = getattr(cfg, name)
    return default if value is None else value


def _strategy_from_raw(base: StrategySettings, raw: dict) -> StrategySettings:
    symbols = raw.get("symbols", base.symbols)
    if symbols is None:
        symbols = list(base.symbols)
    return StrategySettings(
        strategy_id=base.strategy_id,
        enabled=bool(raw.get("enabled", base.enabled)),
        entries_paused=bool(raw.get("entries_paused", base.entries_paused)),
        allocation=float(raw.get("allocation", base.allocation)),
        symbols=[str(item).upper() for item in symbols],
        leverage=int(raw.get("leverage", base.leverage)),
        max_leverage=int(raw.get("max_leverage", base.max_leverage)),
        risk_pct=float(raw.get("risk_pct", base.risk_pct)),
        max_positions=int(raw.get("max_positions", base.max_positions)),
        max_trades_per_day=int(raw.get("max_trades_per_day", base.max_trades_per_day)),
        priority=int(raw.get("priority", base.priority)),
        note=str(raw.get("note", base.note)),
        extra={key: value for key, value in raw.items() if key not in {
            "enabled", "entries_paused", "allocation", "symbols", "leverage",
            "max_leverage", "risk_pct", "max_positions", "max_trades_per_day",
            "priority", "note",
        }},
    )


def resolve_mode(cfg: object | None, force_live: bool = False) -> str:
    """Paper, außer DRY_RUN ist False und LIVE_TRADING explizit True."""
    dry = bool(_get(cfg, "DRY_RUN", True))
    live_flag = bool(_get(cfg, "LIVE_TRADING", False))
    if force_live:
        if dry or not live_flag:
            raise SystemExit(
                "Live abgelehnt: in config.py DRY_RUN=False und LIVE_TRADING=True setzen."
            )
        return "live"
    if (not dry) and live_flag:
        return "live"
    return "paper"


def load_settings(cfg: object | None = None, force_live: bool = False) -> Settings:
    settings = base_settings()
    if cfg is None:
        cfg = load_user_config()
    settings.mode = resolve_mode(cfg, force_live=force_live)
    settings.api_key = str(_get(cfg, "API_KEY", "") or "")
    settings.secret_key = str(_get(cfg, "SECRET_KEY", "") or "")
    settings.passphrase = str(_get(cfg, "PASSPHRASE", "") or "")
    settings.demo_mode = bool(_get(cfg, "DEMO_MODE", False))
    settings.product_type = str(_get(cfg, "PRODUCT_TYPE", settings.product_type))
    settings.margin_mode = str(_get(cfg, "MARGIN_MODE", settings.margin_mode))
    settings.margin_coin = str(_get(cfg, "MARGIN_COIN", settings.margin_coin))
    settings.pos_mode = str(_get(cfg, "POS_MODE", settings.pos_mode))
    settings.paper_equity = float(_get(cfg, "PAPER_EQUITY", settings.paper_equity))
    settings.global_max_leverage = int(_get(cfg, "GLOBAL_MAX_LEVERAGE", settings.global_max_leverage))
    settings.max_total_exposure = float(_get(cfg, "MAX_TOTAL_EXPOSURE", settings.max_total_exposure))
    settings.daily_loss_pct = float(_get(cfg, "DAILY_LOSS_PCT", settings.daily_loss_pct))
    settings.kill_switch = bool(_get(cfg, "KILL_SWITCH", False))
    settings.maker_fee = float(_get(cfg, "MAKER_FEE", settings.maker_fee))
    settings.taker_fee = float(_get(cfg, "TAKER_FEE", settings.taker_fee))
    settings.fee_tp_mult = float(_get(cfg, "FEE_TP_MULT", settings.fee_tp_mult))
    settings.min_notional_usdt = float(_get(cfg, "MIN_NOTIONAL_USDT", settings.min_notional_usdt))
    settings.taker_slippage_pct = float(_get(cfg, "TAKER_SLIPPAGE_PCT", settings.taker_slippage_pct))
    settings.funding_rate_8h = float(_get(cfg, "FUNDING_RATE_8H", settings.funding_rate_8h))
    settings.loop_interval = int(_get(cfg, "LOOP_INTERVAL", settings.loop_interval))
    settings.status_host = str(_get(cfg, "STATUS_HOST", settings.status_host))
    settings.status_port = int(_get(cfg, "STATUS_PORT", settings.status_port))
    settings.log_level = str(_get(cfg, "LOG_LEVEL", settings.log_level))
    settings.telegram_token = str(_get(cfg, "TELEGRAM_BOT_TOKEN", "") or "")
    settings.telegram_chat_id = str(_get(cfg, "TELEGRAM_CHAT_ID", "") or "")
    settings.account_uid = str(_get(cfg, "ACCOUNT_UID", settings.account_uid) or "")
    settings.account_name = str(_get(cfg, "ACCOUNT_NAME", settings.account_name) or "")
    raw_strats = _get(cfg, "STRATEGIES", None) or {}
    merged: dict[str, StrategySettings] = {}
    for strategy_id, base in settings.strategies.items():
        raw = raw_strats.get(strategy_id) if isinstance(raw_strats, dict) else None
        merged[strategy_id] = _strategy_from_raw(base, raw or {})
    settings.strategies = merged
    grid = dict(settings.grid)
    for key, attr in (
        ("max_active_grids", "MAX_ACTIVE_GRIDS"),
        ("max_margin_fraction", "MAX_MARGIN_FRACTION"),
        ("max_inventory_levels", "MAX_INVENTORY_LEVELS"),
        ("hard_stop_pct", "GRID_HARD_STOP_PCT"),
        ("breakout_buffer_pct", "BREAKOUT_BUFFER_PCT"),
        ("cooldown_bars", "COOLDOWN_BARS"),
        ("fee_spacing_mult", "FEE_SPACING_MULT"),
        ("grid_levels", "GRID_LEVELS"),
        ("min_grid_levels", "MIN_GRID_LEVELS"),
        ("level_notional_fraction", "LEVEL_NOTIONAL_FRACTION"),
    ):
        if cfg is not None and hasattr(cfg, attr):
            grid[key] = getattr(cfg, attr)
    settings.grid = grid
    validate_settings(settings)
    return settings


def validate_settings(settings: Settings) -> None:
    if settings.pos_mode != "hedge":
        raise SystemExit(
            "POS_MODE muss hedge sein. One-Way nettet Long und Short auf demselben "
            "Symbol zu einer Börsenposition; dieses Konto führt die Strategien im Hedge."
        )
    if settings.global_max_leverage < 1:
        raise SystemExit("GLOBAL_MAX_LEVERAGE muss mindestens 1 sein.")
    total = 0.0
    for item in settings.strategies.values():
        if item.allocation < 0:
            raise SystemExit(f"{item.strategy_id}: Allokation darf nicht negativ sein.")
        if item.leverage > settings.global_max_leverage:
            raise SystemExit(
                f"{item.strategy_id}: Hebel {item.leverage} über dem globalen Deckel "
                f"{settings.global_max_leverage}."
            )
        if item.leverage > item.max_leverage:
            raise SystemExit(f"{item.strategy_id}: Hebel über dem Strategie-Deckel.")
        total += item.allocation
    if total > 1.0 + 1e-9:
        raise SystemExit(f"Allokationen summieren sich auf {total:.2%}, mehr als 100 %.")
    if settings.mode == "live" and not settings.keys_look_real():
        raise SystemExit("Live abgelehnt: API-Keys fehlen oder sind Platzhalter.")
    if settings.account_uid != "9711026741":
        raise SystemExit(
            "Nur das Konto UID 9711026741 (at-HNK) ist zugelassen. "
            f"config.py hat ACCOUNT_UID={settings.account_uid or 'leer'}."
        )


def load_user_config():
    try:
        return importlib.import_module("config")
    except ImportError:
        return None


def namespace_from(mapping: dict) -> SimpleNamespace:
    return SimpleNamespace(**mapping)
