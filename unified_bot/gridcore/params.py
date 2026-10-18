"""Parameter. Fehlende Felder in einem eingeworfenen V2-config.py bekommen Defaults."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class GridParams:
    maker_fee: float = 0.0002
    taker_fee: float = 0.0006
    fee_spacing_mult: float = 3.0
    funding_rate_8h: float = 0.0001
    adx_period: int = 14
    adx_max_1h: float = 22.0
    adx_max_4h: float = 25.0
    bb_period: int = 20
    bb_mult: float = 2.0
    bb_width_max: float = 0.06
    atr_period: int = 14
    atr_pct_max: float = 0.015
    er_lookback: int = 24
    er_max: float = 0.35
    min_mid_crosses: int = 3
    swing_lookback: int = 48
    min_range_pct: float = 0.008
    max_range_pct: float = 0.08
    edge_inset: float = 0.15
    grid_levels: int = 6
    min_grid_levels: int = 3
    leverage: int = 2
    max_leverage: int = 3
    max_margin_fraction: float = 0.50
    max_inventory_levels: int = 3
    level_notional_fraction: float = 0.20
    breakout_buffer_pct: float = 0.0025
    hard_stop_pct: float = 0.06
    daily_loss_pct: float = 0.05
    taker_slippage_pct: float = 0.0002
    cooldown_bars: int = 6
    min_bars_1h: int = 80
    min_bars_4h: int = 30
    max_active_grids: int = 1
    paper_equity: float = 50.0
    loop_interval: int = 20
    flatten_maker_timeout_s: int = 20
    pos_mode: str = "hedge"
    product_type: str = "USDT-FUTURES"
    margin_mode: str = "isolated"
    margin_coin: str = "USDT"
    exchange_stop: bool = True
    kill_switch: bool = False

    @property
    def min_spacing_pct(self) -> float:
        """Mindestabstand zweier Grid-Levels: Vielfaches der Maker-Round-Trip-Fee."""
        return (2.0 * self.maker_fee) * self.fee_spacing_mult


def _get(cfg: object | None, name: str, default):
    if cfg is None or not hasattr(cfg, name):
        return default
    value = getattr(cfg, name)
    return default if value is None else value


def params_from_config(cfg: object | None) -> GridParams:
    base = GridParams()
    maker = float(_get(cfg, "MAKER_FEE", base.maker_fee))
    taker = float(_get(cfg, "TAKER_FEE", base.taker_fee))
    return GridParams(
        maker_fee=maker,
        taker_fee=taker,
        fee_spacing_mult=float(_get(cfg, "FEE_SPACING_MULT", base.fee_spacing_mult)),
        funding_rate_8h=float(_get(cfg, "FUNDING_RATE_8H", base.funding_rate_8h)),
        adx_period=int(_get(cfg, "ADX_PERIOD", base.adx_period)),
        adx_max_1h=float(_get(cfg, "ADX_MAX_1H", base.adx_max_1h)),
        adx_max_4h=float(_get(cfg, "ADX_MAX_4H", base.adx_max_4h)),
        bb_period=int(_get(cfg, "BB_PERIOD", base.bb_period)),
        bb_mult=float(_get(cfg, "BB_MULT", base.bb_mult)),
        bb_width_max=float(_get(cfg, "BB_WIDTH_MAX", base.bb_width_max)),
        atr_period=int(_get(cfg, "ATR_PERIOD", base.atr_period)),
        atr_pct_max=float(_get(cfg, "ATR_PCT_MAX", base.atr_pct_max)),
        er_lookback=int(_get(cfg, "ER_LOOKBACK", base.er_lookback)),
        er_max=float(_get(cfg, "ER_MAX", base.er_max)),
        min_mid_crosses=int(_get(cfg, "MIN_MID_CROSSES", base.min_mid_crosses)),
        swing_lookback=int(_get(cfg, "SWING_LOOKBACK", base.swing_lookback)),
        min_range_pct=float(_get(cfg, "MIN_RANGE_PCT", base.min_range_pct)),
        max_range_pct=float(_get(cfg, "MAX_RANGE_PCT", base.max_range_pct)),
        edge_inset=float(_get(cfg, "EDGE_INSET", base.edge_inset)),
        grid_levels=int(_get(cfg, "GRID_LEVELS", base.grid_levels)),
        min_grid_levels=int(_get(cfg, "MIN_GRID_LEVELS", base.min_grid_levels)),
        leverage=int(_get(cfg, "DEFAULT_LEVERAGE", base.leverage)),
        max_leverage=int(_get(cfg, "MAX_LEVERAGE", base.max_leverage)),
        max_margin_fraction=float(_get(cfg, "MAX_MARGIN_FRACTION", base.max_margin_fraction)),
        max_inventory_levels=int(_get(cfg, "MAX_INVENTORY_LEVELS", base.max_inventory_levels)),
        level_notional_fraction=float(_get(cfg, "LEVEL_NOTIONAL_FRACTION", base.level_notional_fraction)),
        breakout_buffer_pct=float(_get(cfg, "BREAKOUT_BUFFER_PCT", base.breakout_buffer_pct)),
        hard_stop_pct=float(_get(cfg, "GRID_HARD_STOP_PCT", base.hard_stop_pct)),
        daily_loss_pct=float(_get(cfg, "DAILY_LOSS_PCT", base.daily_loss_pct)),
        taker_slippage_pct=float(_get(cfg, "TAKER_SLIPPAGE_PCT", base.taker_slippage_pct)),
        cooldown_bars=int(_get(cfg, "COOLDOWN_BARS", base.cooldown_bars)),
        max_active_grids=int(_get(cfg, "MAX_ACTIVE_GRIDS", base.max_active_grids)),
        paper_equity=float(_get(cfg, "PAPER_EQUITY", base.paper_equity)),
        loop_interval=int(_get(cfg, "LOOP_INTERVAL", base.loop_interval)),
        flatten_maker_timeout_s=int(_get(cfg, "FLATTEN_MAKER_TIMEOUT_S", base.flatten_maker_timeout_s)),
        pos_mode=str(_get(cfg, "POS_MODE", base.pos_mode)),
        product_type=str(_get(cfg, "PRODUCT_TYPE", base.product_type)),
        margin_mode=str(_get(cfg, "MARGIN_MODE", base.margin_mode)),
        margin_coin=str(_get(cfg, "MARGIN_COIN", base.margin_coin)),
        exchange_stop=bool(_get(cfg, "EXCHANGE_STOP", base.exchange_stop)),
        kill_switch=bool(_get(cfg, "KILL_SWITCH", base.kill_switch)),
    )


@dataclass(frozen=True)
class SymbolConfig:
    symbol: str
    leverage: int


def parse_symbols(cfg: object | None, params: GridParams) -> list[SymbolConfig]:
    raw = _get(cfg, "SYMBOLS", None)
    if not raw:
        raw = [
            {"symbol": "BTCUSDT", "leverage": params.leverage},
            {"symbol": "ETHUSDT", "leverage": params.leverage},
            {"symbol": "BNBUSDT", "leverage": params.leverage},
        ]
    out: list[SymbolConfig] = []
    for item in raw:
        if isinstance(item, str):
            symbol = item
            leverage = params.leverage
        else:
            symbol = str(item.get("symbol", "")).upper()
            leverage = int(item.get("leverage", params.leverage))
        if not symbol.endswith("USDT"):
            continue
        leverage = max(1, min(leverage, params.max_leverage))
        out.append(SymbolConfig(symbol=symbol, leverage=leverage))
    return out


def resolve_mode(cfg: object | None, force_paper: bool = False, force_live: bool = False) -> str:
    """Paper, außer DRY_RUN ist False und LIVE_TRADING explizit True."""
    if force_paper and force_live:
        raise ValueError("paper und live schließen sich aus")
    if force_paper:
        return "paper"
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


def keys_look_real(cfg: object | None) -> bool:
    if cfg is None:
        return False
    key = str(_get(cfg, "API_KEY", "") or "")
    secret = str(_get(cfg, "SECRET_KEY", "") or "")
    phrase = str(_get(cfg, "PASSPHRASE", "") or "")
    if not key or not secret or not phrase:
        return False
    if key.startswith("your_") or "your_bitget" in secret or phrase.startswith("your_"):
        return False
    return True
