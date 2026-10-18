#!/usr/bin/env python3
"""Bitget USDT-M Grid-Bot.

Default ist Paper: es geht keine Order an die Börse.
Live nur mit DRY_RUN=False und LIVE_TRADING=True in config.py.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from bitget_client import BitgetClient
from gridbot import __version__
from gridbot.candles import closed_only, parse_candle, sort_unique
from gridbot.engine import ActiveGrid, RestingOrder, build_plan
from gridbot.params import keys_look_real, params_from_config, parse_symbols, resolve_mode
from gridbot.payloads import Intent, build_payload
from gridbot.reconcile import absorb_exchange_order, position_mismatch
from gridbot.regime import assess
from gridbot.risk import RiskGuard, kill_file_active
from gridbot.settings import load_user_config
from gridbot.specs import FALLBACK_SPECS, ContractSpec, format_number
from gridbot.state_store import StateStore, export_state, import_grids
import telegram_notify

KILL_PATH = Path("KILL_SWITCH")
STATE_PATH = Path("state/grid_state.json")
MISMATCH_ROUNDS = 2


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )
    Path("logs").mkdir(exist_ok=True)
    logger.add("logs/grid_bot.log", level=level, rotation="10 MB", retention="14 days")


def load_candles(client: BitgetClient, symbol: str, granularity: str, limit: int, now_ms: int | None = None):
    """Nur geschlossene Kerzen, wie im Backtest. Die laufende Kerze fällt weg."""
    rows = client.get_candles(symbol, granularity, limit)
    now_ms = int(time.time() * 1000) if now_ms is None else now_ms
    return closed_only(sort_unique(parse_candle(row) for row in rows), granularity, now_ms)


def load_spec(client: BitgetClient, symbol: str, cache: dict[str, ContractSpec]) -> ContractSpec:
    if symbol in cache:
        return cache[symbol]
    row = client.get_contract(symbol)
    spec = ContractSpec.from_bitget(row) if row else FALLBACK_SPECS.get(symbol)
    if spec is None:
        raise RuntimeError(f"kein Kontrakt für {symbol}")
    cache[symbol] = spec
    return spec


def notify(cfg, text: str) -> None:
    token = getattr(cfg, "TG_TOKEN", "") if cfg else ""
    chat = getattr(cfg, "TG_CHAT_ID", "") if cfg else ""
    telegram_notify.send(text, token=str(token or ""), chat_id=str(chat or ""))


def order_to_intent(order, symbol: str, order_type: str = "limit") -> Intent:
    return Intent(
        symbol=symbol,
        book_side=order.book_side,
        purpose=order.purpose,
        position_side=order.position_side,
        level=order.level,
        price=order.price if order_type == "limit" else None,
        size=order.size,
        order_type=order_type,
        client_oid=order.client_oid,
    )


class Runner:
    def __init__(self, mode: str, cfg, params, symbols):
        self.mode = mode
        self.cfg = cfg
        self.params = params
        self.symbols = symbols
        self.client = BitgetClient(
            api_key=str(getattr(cfg, "API_KEY", "") if cfg else ""),
            secret_key=str(getattr(cfg, "SECRET_KEY", "") if cfg else ""),
            passphrase=str(getattr(cfg, "PASSPHRASE", "") if cfg else ""),
            product_type=params.product_type,
            margin_coin=params.margin_coin,
            margin_mode=params.margin_mode,
            demo_mode=bool(getattr(cfg, "DEMO_MODE", False)) if cfg else False,
        )
        raw = StateStore(STATE_PATH).load()
        saved_mode = raw.get("mode")
        if saved_mode and saved_mode != mode:
            logger.warning(f"Zustand aus Modus {saved_mode} wird ignoriert (jetzt {mode}).")
            raw = {}
        self.risk = RiskGuard.from_dict(raw.get("risk"))
        self.grids = import_grids(raw)
        self.banked = float(raw.get("banked", 0) or 0)
        self.anchor = float(raw.get("equity_anchor") or 0)
        self.frozen = set(raw.get("frozen") or [])
        self.last_1m = {key: int(value) for key, value in (raw.get("last_1m") or {}).items()}
        self.cooldown_until = {key: int(value) for key, value in (raw.get("cooldown_until") or {}).items()}
        self.specs: dict[str, ContractSpec] = {}
        self.stop_sig: dict[str, tuple] = {}
        self.mismatches: dict[str, int] = {}
        self._prepared = False
        self.store = StateStore(STATE_PATH)

    def session_equity(self, marks: dict[str, float]) -> float:
        total = (self.anchor or self.params.paper_equity) + self.banked
        for symbol, grid in self.grids.items():
            mark = marks.get(symbol) or _mid(grid)
            total += grid.net_pnl(mark)
        return total

    def ensure_anchor(self) -> None:
        if self.anchor > 0:
            return
        if keys_look_real(self.cfg):
            equity = self.client.get_equity()
            if equity is not None and equity > 0:
                self.anchor = equity
                logger.info(f"Start-Equity vom Konto: {equity:.2f} USDT")
                return
        self.anchor = self.params.paper_equity
        logger.info(f"Paper-Startkapital: {self.anchor:.2f} USDT")

    def sizing_equity(self, marks: dict[str, float]) -> float | None:
        """Kapital für das Grid-Budget. None heißt: Kontostand unbekannt, nichts ändern.

        Live zählt das Konto-Equity, nicht `available`. `available` hat die Margin
        von Lage und offenen Orders schon abgezogen, `desired_intents` zieht die
        Lage-Margin selbst ab. Mit `available` schrumpfte das Budget nach jedem
        Platzieren, und liegende Orders wurden storniert und neu gesetzt.
        """
        session = self.session_equity(marks)
        if self.mode != "live":
            return session
        equity = self.client.get_equity()
        if equity is None or equity <= 0:
            return None
        return min(session, equity)

    def prepare_live(self) -> None:
        if self.mode != "live" or self._prepared:
            return
        if not keys_look_real(self.cfg):
            raise SystemExit("Live abgelehnt: API-Keys fehlen oder sind Platzhalter.")
        mode_resp = self.client.set_position_mode(self.params.pos_mode)
        logger.info(f"Positionsmodus {self.params.pos_mode}: {mode_resp.get('code')} {mode_resp.get('msg', '')}")
        for sym in self.symbols:
            self.client.set_margin_mode(sym.symbol, self.params.margin_mode)
            for side in ("long", "short"):
                self.client.set_leverage(sym.symbol, sym.leverage, side)
        self._prepared = True

    def reconcile(self) -> None:
        if self.mode != "live":
            logger.info("Paper: Zustand aus state/grid_state.json, keine Börsenorders.")
            return
        known = {oid for grid in self.grids.values() for oid in grid.orders}
        for symbol, grid in list(self.grids.items()):
            pending = self.client.get_open_orders(symbol)
            pending_ids = {str(row.get("clientOid") or "") for row in pending}
            for row in pending:
                oid = str(row.get("clientOid") or "")
                if oid in grid.orders and row.get("orderId"):
                    grid.orders[oid].order_id = str(row["orderId"])
            for order in list(grid.orders.values()):
                detail = self.client.get_order_detail(symbol, order.order_id, order.client_oid)
                state = str(detail.get("state", "live" if order.client_oid in pending_ids else "")).lower()
                if order.client_oid in pending_ids and state in ("", "live", "new", "partially_filled"):
                    state = state or "live"
                note = absorb_exchange_order(
                    grid,
                    order,
                    {
                        "state": state,
                        "filled": float(detail.get("baseVolume") or 0),
                        "avg": float(detail.get("priceAvg") or order.price),
                    },
                    self.params.maker_fee,
                )
                if note not in ("resting", "partial"):
                    logger.info(f"Reconcile {symbol} {order.client_oid}: {note}")
            long_qty, short_qty = _position_qtys(self.client.get_positions(symbol))
            spec = load_spec(self.client, symbol, self.specs)
            if position_mismatch(grid, long_qty, short_qty, spec.qty_step):
                logger.error(
                    f"{symbol}: Lage weicht ab, lokal L={grid.long_qty} S={grid.short_qty}, "
                    f"Börse L={long_qty} S={short_qty}. Keine neuen Orders."
                )
                self.frozen.add(symbol)
                self._cancel_local_orders(grid)
        for sym in self.symbols:
            if sym.symbol in self.grids:
                continue
            if self.client.get_positions(sym.symbol):
                logger.warning(f"{sym.symbol}: fremde Position, wird nicht angefasst.")
                self.frozen.add(sym.symbol)
            for row in self.client.get_open_orders(sym.symbol):
                oid = str(row.get("clientOid") or "")
                if oid.startswith("grd") and oid not in known:
                    logger.warning(f"Verwaiste Order {sym.symbol} {oid} wird storniert.")
                    self.client.cancel_order(sym.symbol, row.get("orderId"), oid)

    def step(self) -> None:
        self.ensure_anchor()
        self.prepare_live()
        now = datetime.now(timezone.utc)
        marks = {}
        for sym in self.symbols:
            ticker = self.client.get_ticker(sym.symbol)
            marks[sym.symbol] = float(ticker.get("lastPr") or 0)
        self.risk.on_day(now.date().isoformat(), self.session_equity(marks))
        self._apply_kill_switch()
        if self.risk.halt_reason == "kill_switch":
            for grid in list(self.grids.values()):
                self.flatten(grid, "kill_switch", marks.get(grid.symbol) or _mid(grid))
            self.save()
            return

        for symbol, grid in list(self.grids.items()):
            self._poll_fills(grid)
            self._check_position(grid)
            mark = marks.get(symbol) or 0.0
            if mark <= 0:
                logger.warning(f"{symbol}: kein Preis")
                continue
            if self.risk.check_daily(self.session_equity(marks), self.params.daily_loss_pct):
                self.flatten(grid, "daily_loss", mark)
                notify(self.cfg, f"Tagesverlust-Limit, Grid {symbol} geschlossen")
                continue
            if grid.outside(mark, self.params.breakout_buffer_pct):
                self.flatten(grid, "breakout", mark)
                continue
            if grid.net_pnl(mark) <= -grid.hard_stop_usdt:
                self.flatten(grid, "hard_stop", mark)
                continue
            regime = assess(
                load_candles(self.client, symbol, "1H", 200),
                load_candles(self.client, symbol, "4H", 120),
                self.params,
            )
            if not regime.ranging:
                self.flatten(grid, "regime", mark)
                continue
            if symbol in self.frozen:
                continue
            spec = load_spec(self.client, symbol, self.specs)
            equity = self.sizing_equity(marks)
            if equity is None:
                logger.warning(f"{symbol}: Kontostand nicht lesbar, Orders bleiben wie sie sind.")
                continue
            cancelled = grid.sync_orders(mark, equity, spec, self.params)
            for order in cancelled:
                self._cancel_and_absorb(grid, order)
            self._push_orders(grid, spec)
            self._exchange_stop(grid, spec)

        now_ms = int(time.time() * 1000)
        equity = None
        if len(self.grids) < self.params.max_active_grids and not self.risk.halted:
            equity = self.sizing_equity(marks)
            if equity is None:
                logger.warning("Kontostand nicht lesbar, kein neues Grid.")
        if equity is not None:
            for sym in self.symbols:
                if sym.symbol in self.grids or sym.symbol in self.frozen:
                    continue
                if now_ms < self.cooldown_until.get(sym.symbol, 0):
                    continue
                candles_1h = load_candles(self.client, sym.symbol, "1H", 200)
                candles_4h = load_candles(self.client, sym.symbol, "4H", 120)
                if len(candles_1h) < self.params.min_bars_1h:
                    logger.warning(f"{sym.symbol}: zu wenig 1h-Kerzen ({len(candles_1h)})")
                    continue
                regime = assess(candles_1h, candles_4h, self.params)
                if not regime.ranging:
                    logger.info(f"{sym.symbol}: kein Grid — {regime.reason_text()}")
                    continue
                spec = load_spec(self.client, sym.symbol, self.specs)
                plan, why = build_plan(candles_1h, spec, equity, self.params, sym.leverage)
                if plan is None:
                    logger.info(f"{sym.symbol}: Range, aber kein Grid ({why})")
                    continue
                grid = ActiveGrid.from_plan(plan, created_ms=now_ms)
                mark = marks.get(sym.symbol) or candles_1h[-1].close
                grid.sync_orders(mark, equity, spec, self.params)
                self.grids[sym.symbol] = grid
                self._push_orders(grid, spec)
                logger.info(
                    f"Grid {sym.symbol} {plan.lower:.6g}–{plan.upper:.6g} "
                    f"n={len(plan.levels)} qty={plan.qty} Abstand={plan.spacing_pct * 100:.3f}%"
                )
                notify(self.cfg, f"Grid gestartet {sym.symbol}")
                if len(self.grids) >= self.params.max_active_grids:
                    break
        self.save()
        logger.info(f"Modus={self.mode} Equity≈{self.session_equity(marks):.2f} Grids={list(self.grids)}")

    def _apply_kill_switch(self) -> None:
        active = self.params.kill_switch or kill_file_active(KILL_PATH)
        if active:
            if self.risk.halt_reason != "kill_switch":
                logger.error("Kill-Switch aktiv")
                notify(self.cfg, "Kill-Switch aktiv")
            self.risk.engage_kill()
        elif self.risk.halt_reason == "kill_switch":
            self.risk.release_kill_if_clear()
            logger.info("Kill-Switch aufgehoben")

    def _absorb_detail(self, grid: ActiveGrid, order: RestingOrder, detail: dict) -> str:
        return absorb_exchange_order(
            grid,
            order,
            {
                "state": str(detail.get("state", "")).lower(),
                "filled": float(detail.get("baseVolume") or 0),
                "avg": float(detail.get("priceAvg") or order.price),
            },
            self.params.maker_fee,
        )

    def _poll_fills(self, grid: ActiveGrid) -> None:
        if self.mode == "live":
            for order in list(grid.orders.values()):
                detail = self.client.get_order_detail(grid.symbol, order.order_id, order.client_oid)
                if detail:
                    self._absorb_detail(grid, order, detail)
            return
        closed = load_candles(self.client, grid.symbol, "1m", 3)
        if not closed:
            return
        last = self.last_1m.get(grid.symbol, 0)
        if last == 0:
            self.last_1m[grid.symbol] = closed[-1].ts
            return
        for candle in closed:
            if candle.ts <= last:
                continue
            for order in list(grid.orders.values()):
                if candle.low <= order.price <= candle.high:
                    grid.apply_fill(order, order.price, order.size, self.params.maker_fee)
                    logger.info(f"[PAPER] Fill {grid.symbol} {order.purpose} {order.book_side} @ {order.price}")
            self.last_1m[grid.symbol] = candle.ts

    def _push_orders(self, grid: ActiveGrid, spec: ContractSpec) -> None:
        ticker = self.client.get_ticker(grid.symbol)
        bid = float(ticker.get("bidPr") or 0)
        ask = float(ticker.get("askPr") or 0)
        for order in list(grid.orders.values()):
            if order.order_id:
                continue
            if order.book_side == "buy" and ask and order.price >= ask:
                logger.info(f"Post-only Buy {grid.symbol} @ {order.price} würde nehmen — verworfen")
                grid.orders.pop(order.client_oid, None)
                continue
            if order.book_side == "sell" and bid and order.price <= bid:
                logger.info(f"Post-only Sell {grid.symbol} @ {order.price} würde nehmen — verworfen")
                grid.orders.pop(order.client_oid, None)
                continue
            if self.mode != "live":
                order.order_id = "paper-" + order.client_oid
                logger.info(
                    f"[PAPER] post-only {order.book_side} {order.purpose} {order.size} {grid.symbol} @ {order.price}"
                )
                continue
            payload = build_payload(
                order_to_intent(order, grid.symbol),
                spec,
                self.params.pos_mode,
                self.params.product_type,
                self.params.margin_mode,
                self.params.margin_coin,
            )
            result = self.client.place_order(payload)
            if result.get("code") == "00000":
                data = result.get("data") or {}
                order.order_id = str(data.get("orderId") or order.client_oid)
                logger.info(f"Order {grid.symbol} {order.purpose} {order.book_side} @ {order.price}")
            else:
                logger.warning(f"Order abgelehnt {grid.symbol}: {result.get('code')} {result.get('msg')}")
                grid.orders.pop(order.client_oid, None)

    def _check_position(self, grid: ActiveGrid) -> None:
        """Live: Börsenlage gegen die lokalen Lots, jede Runde.

        Ein Fill zwischen Order-Abfrage und Positions-Abfrage sieht wie eine
        Abweichung aus und ist in der nächsten Runde verbucht. Eingefroren wird
        deshalb erst, wenn die Abweichung zwei Runden hintereinander steht.
        """
        if self.mode != "live" or grid.symbol in self.frozen:
            return
        long_qty, short_qty = _position_qtys(self.client.get_positions(grid.symbol))
        spec = load_spec(self.client, grid.symbol, self.specs)
        if not position_mismatch(grid, long_qty, short_qty, spec.qty_step):
            self.mismatches.pop(grid.symbol, None)
            return
        seen = self.mismatches.get(grid.symbol, 0) + 1
        self.mismatches[grid.symbol] = seen
        text = (
            f"{grid.symbol}: Lage weicht ab, lokal L={grid.long_qty} S={grid.short_qty}, "
            f"Börse L={long_qty} S={short_qty}"
        )
        if seen < MISMATCH_ROUNDS:
            logger.warning(f"{text}. Prüfe in der nächsten Runde erneut.")
            return
        logger.error(f"{text}. Keine neuen Orders.")
        notify(self.cfg, f"Lage weicht ab, {grid.symbol} eingefroren")
        self.frozen.add(grid.symbol)
        self.mismatches.pop(grid.symbol, None)
        self._cancel_local_orders(grid)

    def _cancel_and_absorb(self, grid: ActiveGrid, order: RestingOrder) -> None:
        """Storniert live und verbucht, was bis zum Storno gefüllt wurde."""
        grid.orders.pop(order.client_oid, None)
        if self.mode != "live":
            return
        result = self.client.cancel_order(grid.symbol, order.order_id, order.client_oid)
        if result.get("code") != "00000":
            logger.warning(f"Storno {grid.symbol} {order.client_oid}: {result.get('code')} {result.get('msg', '')}")
        detail = self.client.get_order_detail(grid.symbol, order.order_id, order.client_oid)
        if not detail:
            return
        before = order.filled_ack
        self._absorb_detail(grid, order, detail)
        if order.filled_ack > before:
            logger.info(f"Fill vor Storno {grid.symbol} {order.client_oid}: {order.filled_ack - before}")

    def _cancel_local_orders(self, grid: ActiveGrid) -> None:
        for order in list(grid.orders.values()):
            self._cancel_and_absorb(grid, order)

    def flatten(self, grid: ActiveGrid, reason: str, mark: float) -> None:
        logger.warning(f"Ausstieg {grid.symbol}: {reason}")
        notify(self.cfg, f"Grid-Ausstieg {grid.symbol}: {reason}")
        self._cancel_local_orders(grid)
        if self.mode == "live" and (grid.long_qty > 0 or grid.short_qty > 0):
            self._flatten_live(grid, mark)
        else:
            grid.flatten(mark, self.params.taker_slippage_pct, self.params.taker_fee)
        self.banked += grid.net_pnl(mark)
        self.cooldown_until[grid.symbol] = int(time.time() * 1000) + self.params.cooldown_bars * 3_600_000
        self.grids.pop(grid.symbol, None)
        self.mismatches.pop(grid.symbol, None)

    def _flatten_live(self, grid: ActiveGrid, mark: float) -> None:
        """Erst Post-only-Close mit Timeout, danach Market-IOC. Danach lokale Lots glattziehen."""
        spec = load_spec(self.client, grid.symbol, self.specs)
        ticker = self.client.get_ticker(grid.symbol)
        bid = float(ticker.get("bidPr") or mark)
        ask = float(ticker.get("askPr") or mark)
        intents = []
        if grid.long_qty > 0:
            intents.append(Intent(grid.symbol, "sell", "close", "long", -1, ask, grid.long_qty, "limit", grid.next_oid(0, "close")))
        if grid.short_qty > 0:
            intents.append(Intent(grid.symbol, "buy", "close", "short", -1, bid, grid.short_qty, "limit", grid.next_oid(0, "close")))
        resting = []
        for intent in intents:
            payload = build_payload(
                intent, spec, self.params.pos_mode, self.params.product_type, self.params.margin_mode, self.params.margin_coin,
            )
            result = self.client.place_order(payload)
            if result.get("code") == "00000":
                resting.append((intent, (result.get("data") or {}).get("orderId")))
        deadline = time.time() + self.params.flatten_maker_timeout_s
        while resting and time.time() < deadline:
            time.sleep(2)
            still = []
            for intent, order_id in resting:
                detail = self.client.get_order_detail(grid.symbol, order_id, intent.client_oid)
                if str(detail.get("state", "")).lower() != "filled":
                    still.append((intent, order_id))
            resting = still
        for intent, order_id in resting:
            self.client.cancel_order(grid.symbol, order_id, intent.client_oid)
        for row in self.client.get_positions(grid.symbol):
            side = str(row.get("holdSide", "")).lower()
            qty = float(row.get("total") or 0)
            if qty <= 0 or side not in ("long", "short"):
                continue
            book = "sell" if side == "long" else "buy"
            intent = Intent(grid.symbol, book, "emergency", side, -1, None, qty, "market", grid.next_oid(0, "emergency"))
            payload = build_payload(
                intent, spec, self.params.pos_mode, self.params.product_type, self.params.margin_mode, self.params.margin_coin,
            )
            result = self.client.place_order(payload)
            logger.warning(f"Notfall-Market {grid.symbol} {side} {qty}: {result.get('code')} {result.get('msg', '')}")
        grid.flatten(mark, self.params.taker_slippage_pct, self.params.taker_fee)

    def _exchange_stop(self, grid: ActiveGrid, spec: ContractSpec) -> None:
        if self.mode != "live" or not self.params.exchange_stop:
            return
        signature = (round(grid.long_qty, 8), round(grid.short_qty, 8))
        if self.stop_sig.get(grid.symbol) == signature:
            return
        self.stop_sig[grid.symbol] = signature
        if grid.long_qty > 0:
            price = format_number(grid.lower * (1.0 - self.params.breakout_buffer_pct), spec.price_place)
            self.client.place_position_stop(grid.symbol, "long", price)
        if grid.short_qty > 0:
            price = format_number(grid.upper * (1.0 + self.params.breakout_buffer_pct), spec.price_place)
            self.client.place_position_stop(grid.symbol, "short", price)

    def save(self) -> None:
        payload = export_state(
            self.mode,
            self.anchor,
            self.risk,
            self.grids,
            {
                "banked": self.banked,
                "frozen": sorted(self.frozen),
                "last_1m": self.last_1m,
                "cooldown_until": self.cooldown_until,
            },
        )
        self.store.save(payload)


def _mid(grid: ActiveGrid) -> float:
    if not grid.levels:
        return 0.0
    return grid.levels[len(grid.levels) // 2]


def _position_qtys(rows: list[dict]) -> tuple[float, float]:
    long_qty = 0.0
    short_qty = 0.0
    for row in rows:
        side = str(row.get("holdSide", "")).lower()
        qty = float(row.get("total") or 0)
        if side == "long":
            long_qty += qty
        elif side == "short":
            short_qty += qty
    return long_qty, short_qty


def main() -> None:
    parser = argparse.ArgumentParser(description="Bitget USDT-M Grid-Bot (Paper ist der Default)")
    parser.add_argument("--once", action="store_true", help="ein Durchlauf, dann Ende")
    parser.add_argument("--paper", action="store_true", help="Paper erzwingen")
    parser.add_argument("--live", action="store_true", help="Live, nur zusammen mit den Config-Schaltern")
    args = parser.parse_args()
    cfg = load_user_config()
    params = params_from_config(cfg)
    mode = resolve_mode(cfg, force_paper=args.paper, force_live=args.live)
    setup_logging(str(getattr(cfg, "LOG_LEVEL", "INFO") if cfg else "INFO"))
    symbols = parse_symbols(cfg, params)
    logger.info(f"Grid-Bot {__version__} Modus={mode} Symbole={[item.symbol for item in symbols]}")
    if mode == "paper":
        logger.info("PAPER: keine echten Orders. Live braucht DRY_RUN=False und LIVE_TRADING=True.")
        dry = bool(getattr(cfg, "DRY_RUN", True)) if cfg else True
        live_flag = bool(getattr(cfg, "LIVE_TRADING", False)) if cfg else False
        if not dry and not live_flag:
            logger.warning("DRY_RUN=False ohne LIVE_TRADING — es bleibt beim Paper-Modus.")
    runner = Runner(mode, cfg, params, symbols)
    runner.reconcile()
    if args.once:
        runner.step()
        return
    while True:
        try:
            runner.step()
        except Exception as exc:
            logger.exception(f"Loop-Fehler: {exc}")
        time.sleep(params.loop_interval)


if __name__ == "__main__":
    main()
