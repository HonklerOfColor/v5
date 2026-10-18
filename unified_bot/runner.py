"""Ein Loop, ein Konto. Strategien sehen nur ihr Sleeve."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

from loguru import logger

from unified_bot.book import Book
from unified_bot.broker import LiveBroker, PaperBroker
from unified_bot.client import BitgetClient
from unified_bot.gridcore.candles import parse_candle, sort_unique
from unified_bot.gridcore.specs import FALLBACK_SPECS, ContractSpec
from unified_bot.market import CycleContext, SymbolView
from unified_bot.models import Fill, OrderIntent
from unified_bot.orders import OrderManager
from unified_bot.reconcile import reconcile
from unified_bot.risk import RiskManager, kill_file_active
from unified_bot.settings import Settings
from unified_bot.state_store import export_payload, load_state, restore_book, save_state
from unified_bot.strategies.registry import build_strategies
from unified_bot import telegram

FUNDING_MS = 8 * 3_600_000


def setup_logging(level: str) -> None:
    logger.remove()
    logger.add(
        sys.stdout,
        level=level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
    )
    Path("logs").mkdir(exist_ok=True)
    logger.add("logs/unified_bot.log", level=level, rotation="10 MB", retention="14 days")


class Bot:
    def __init__(
        self,
        settings: Settings,
        broker=None,
        state_path: Path | None = None,
        kill_path: Path | None = None,
        public_client: BitgetClient | None = None,
    ):
        self.settings = settings
        self.state_path = state_path or Path("state/unified_state.json")
        self.kill_path = kill_path or Path("KILL_SWITCH")
        self.strategies = build_strategies(settings)
        self.by_id = {item.id: item for item in self.strategies}
        allocations = {item.id: settings.strategy(item.id).allocation for item in self.strategies}
        raw = load_state(self.state_path)
        book, risk_state, strat_state, funding, notes = restore_book(
            raw, settings.mode, allocations, settings.paper_equity
        )
        if book.anchor <= 0:
            book.anchor = settings.paper_equity
        self._try_account_anchor(book, settings, anchor=not raw)
        for strategy in self.strategies:
            strategy.load_state(strat_state.get(strategy.id) or {})
        self.book = book
        self.risk = RiskManager(settings, risk_state)
        self.public = public_client if public_client is not None else BitgetClient(
            product_type=settings.product_type,
            margin_coin=settings.margin_coin,
            margin_mode=settings.margin_mode,
            demo_mode=settings.demo_mode,
        )
        if broker is not None:
            self.broker = broker
        elif settings.mode == "live":
            self.broker = LiveBroker(
                BitgetClient(
                    api_key=settings.api_key,
                    secret_key=settings.secret_key,
                    passphrase=settings.passphrase,
                    product_type=settings.product_type,
                    margin_coin=settings.margin_coin,
                    margin_mode=settings.margin_mode,
                    demo_mode=settings.demo_mode,
                ),
                settings,
            )
        else:
            self.broker = PaperBroker(settings)
        self.manager = OrderManager(settings, self.risk, self.book, self.broker)
        self.last_funding_bucket: dict[str, int] = {
            key: int(value) // FUNDING_MS for key, value in funding.items()
        }
        self.notes = notes
        self.last_cycle: dict = {}
        self.specs: dict[str, ContractSpec] = dict(FALLBACK_SPECS)
        self._prepared_live = False
        self._specs_loaded: set[str] = set()
        self.last_marks: dict[str, float] = {}
        self._halt_notified = False
        for note in notes:
            logger.warning(note)

    @staticmethod
    def _try_account_anchor(book: Book, settings: Settings, anchor: bool = True) -> None:
        """Prüft bei jedem Start die UID. Die Start-Equity wird nur ohne Zustandsdatei gelesen."""
        if not settings.keys_look_real():
            logger.info(
                f"Konto {settings.account_name} UID {settings.account_uid}. "
                "Secret oder Passphrase fehlen, das Konto wird nicht signiert abgefragt."
            )
            return
        try:
            client = BitgetClient(
                api_key=settings.api_key,
                secret_key=settings.secret_key,
                passphrase=settings.passphrase,
                product_type=settings.product_type,
                margin_coin=settings.margin_coin,
                margin_mode=settings.margin_mode,
                demo_mode=settings.demo_mode,
            )
            user_id = client.get_user_id()
            if user_id and user_id != settings.account_uid:
                raise SystemExit(
                    f"Key gehört zu UID {user_id}, zugelassen ist nur {settings.account_uid} "
                    f"({settings.account_name})."
                )
            if not user_id and settings.mode == "live":
                raise SystemExit(
                    f"UID von {settings.account_name} nicht lesbar. Live ohne Abgleich abgelehnt."
                )
            equity = client.get_equity() if anchor else 0.0
        except SystemExit:
            raise
        except Exception as exc:
            if settings.mode == "live":
                raise SystemExit(f"Konto nicht prüfbar ({exc}). Live ohne UID-Abgleich abgelehnt.") from exc
            logger.warning(f"Kontostand nicht lesbar ({exc}). Paper-Equity bleibt {book.anchor:.2f}.")
            return
        logger.info(f"Key geprüft gegen UID {settings.account_uid} ({settings.account_name}).")
        if anchor and equity and equity > 0:
            book.anchor = equity
            logger.info(f"Start-Equity vom Konto: {equity:.2f} USDT")

    def symbols(self) -> list[str]:
        found: list[str] = []
        for strategy in self.strategies:
            if not self.settings.strategy(strategy.id).enabled:
                continue
            for symbol in self.settings.strategy(strategy.id).symbols:
                if symbol not in found:
                    found.append(symbol)
        for pos in self.book.positions:
            if pos.symbol not in found:
                found.append(pos.symbol)
        return found

    def fetch_views(self) -> dict[str, SymbolView]:
        views: dict[str, SymbolView] = {}
        for symbol in self.symbols():
            views[symbol] = self._fetch_symbol(symbol)
        return views

    def _fetch_symbol(self, symbol: str) -> SymbolView:
        try:
            rows = self.public.get_candles(symbol, "1H", 200)
            candles = sort_unique(parse_candle(row) for row in rows)
            ticker = self.public.get_ticker(symbol) or {}
            last = _f(ticker.get("lastPr") or ticker.get("markPrice"))
            bid = _f(ticker.get("bidPr")) or last
            ask = _f(ticker.get("askPr")) or last
            funding = ticker.get("fundingRate")
            funding_rate = float(funding) if funding not in (None, "") else None
            depth = self.public.get_orderbook(symbol, 15)
            data = depth.get("data") or {}
            bids = data.get("bids") or data.get("b") or []
            asks = data.get("asks") or data.get("a") or []
            if bids and not bid:
                bid = float(bids[0][0])
            if asks and not ask:
                ask = float(asks[0][0])
            spec = self.specs.get(symbol)
            if symbol not in self._specs_loaded:
                try:
                    spec = self.public.get_spec(symbol)
                    self._specs_loaded.add(symbol)
                except Exception as exc:
                    logger.warning(f"{symbol}: Kontrakt nicht von Bitget geladen ({exc}), Fallback-Spec")
                    spec = spec or FALLBACK_SPECS.get(symbol)
            if spec is not None:
                self.specs[symbol] = spec
            if not candles and last <= 0:
                return SymbolView(symbol, [], bid, ask, last, funding_rate, spec, bids, asks, "keine Kerzen")
            return SymbolView(symbol, candles, bid, ask, last, funding_rate, spec, bids, asks, "")
        except Exception as exc:
            return SymbolView(symbol, [], 0, 0, 0, None, self.specs.get(symbol), [], [], str(exc))

    def run_cycle(self, views: dict[str, SymbolView] | None = None, now_ms: int | None = None) -> dict:
        now_ms = int(now_ms if now_ms is not None else datetime.now(timezone.utc).timestamp() * 1000)
        if views is None:
            views = self.fetch_views()
        for view in views.values():
            if view.spec is not None:
                self.specs[view.symbol] = view.spec
        marks = _marks(views)
        self.last_marks.update(marks)
        self._match_paper(views, now_ms)
        self._enforce_halt(marks, now_ms)
        self._reconcile(now_ms)
        cycle_notes: list[str] = []
        placed = 0
        rejected: list[dict] = []
        for strategy in self.strategies:
            ctx = self._context(strategy.id, views, now_ms)
            plan = strategy.plan(ctx)
            cycle_notes.extend(plan.notes)
            for cancel in plan.cancels:
                self.manager.cancel(cancel.symbol, cancel.client_oid, cancel.order_id)
                grid = getattr(strategy, "grids", None)
                if grid and cancel.symbol in grid:
                    grid[cancel.symbol].orders.pop(cancel.client_oid, None)
            for stop in plan.stops:
                self._apply_stop(stop)
            for intent in plan.orders:
                view = views.get(intent.symbol)
                spec = (view.spec if view and view.spec is not None else None) or self.specs.get(intent.symbol)
                if spec is None:
                    rejected.append({"strategy": intent.strategy_id, "symbol": intent.symbol, "reason": "no_spec"})
                    strategy.on_reject(intent, "no_spec")
                    continue
                mark = marks.get(intent.symbol) or (intent.price or 0)
                result = self.manager.submit(
                    intent,
                    spec,
                    mark=mark,
                    bid=view.bid if view else 0,
                    ask=view.ask if view else 0,
                    ts_ms=now_ms,
                )
                if not result.accepted:
                    rejected.append(
                        {"strategy": intent.strategy_id, "symbol": intent.symbol, "reason": result.reason}
                    )
                    strategy.on_reject(intent, result.reason)
                    logger.info(f"abgelehnt {intent.strategy_id} {intent.symbol} {intent.purpose}: {result.reason}")
                    continue
                placed += 1
                if result.fill is not None:
                    strategy.consume_fill(result.fill, self.book)
                    self._protect_after_fill(result.fill)
                    self._notify_fill(result.fill)
        self._funding(views, now_ms)
        self._persist()
        report = {
            "mode": self.settings.mode,
            "equity": round(self.book.account_equity(marks), 4),
            "placed": placed,
            "rejected": rejected,
            "notes": cycle_notes,
            "halted": self.risk.state.halted,
            "halt_reason": self.risk.state.halt_reason,
            "locks": dict(self.book.locks),
        }
        self.last_cycle = report
        self.notes = cycle_notes
        logger.info(
            f"Zyklus {self.settings.mode} Equity {report['equity']:.2f} "
            f"Orders {placed} abgelehnt {len(rejected)} "
            f"Halt {self.risk.state.halt_reason or 'nein'}"
        )
        return report

    def _context(self, strategy_id: str, views: dict[str, SymbolView], now_ms: int) -> CycleContext:
        marks = _marks(views)
        day = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date().isoformat()
        wanted = set(self.settings.strategy(strategy_id).symbols)
        for pos in self.book.positions_of(strategy_id):
            wanted.add(pos.symbol)
        subset = {symbol: views[symbol] for symbol in wanted if symbol in views}
        return CycleContext(
            now_ms=now_ms,
            mode=self.settings.mode,
            sleeve_equity=self.book.sleeve_cash(strategy_id),
            free_margin=self.book.free_margin(strategy_id, marks),
            entries_allowed=not self.risk.state.entries_blocked(),
            views=subset,
            positions=self.book.positions_of(strategy_id),
            orders=[order for order in self.book.orders.values() if order.strategy_id == strategy_id],
            frozen=set(self.risk.state.frozen_symbols),
            day=day,
            entries_today=self.book.entries_today(strategy_id, day),
            last_stop_ms=dict(self.book.ledger(strategy_id).last_stop_ms),
        )

    def _match_paper(self, views: dict[str, SymbolView], now_ms: int) -> None:
        if not hasattr(self.broker, "match"):
            return
        for symbol, view in views.items():
            if view.last <= 0:
                continue
            for row in self.broker.match(symbol, view.last):
                order = self.book.orders.get(row["clientOid"])
                if order is None:
                    continue
                price = float(row.get("avg") or row.get("price") or view.last)
                qty = float(row.get("filled") or order.size)
                fee_rate = self.settings.maker_fee
                fill = Fill(
                    strategy_id=order.strategy_id,
                    client_oid=order.client_oid,
                    symbol=order.symbol,
                    book_side=order.book_side,
                    position_side=order.position_side,
                    purpose=order.purpose,
                    price=price,
                    qty=qty,
                    fee=price * qty * fee_rate,
                    fee_rate=fee_rate,
                    liquidity="maker",
                    ts_ms=now_ms,
                    leverage=order.leverage,
                    reason=order.reason or order.purpose,
                    market=order.market,
                )
                self.book.apply_fill(fill)
                self.by_id[order.strategy_id].consume_fill(fill, self.book)
                self._notify_fill(fill)

    def _enforce_halt(self, marks: dict[str, float], now_ms: int) -> None:
        if kill_file_active(self.kill_path) or self.settings.kill_switch:
            self.risk.state.engage_kill()
        elif self.risk.state.halt_reason == "kill_switch":
            self.risk.state.release_kill_if_clear()
        day = datetime.fromtimestamp(now_ms / 1000, tz=timezone.utc).date().isoformat()
        equity = self.book.account_equity(marks)
        self.risk.state.on_day(day, equity)
        self.risk.state.check_daily(equity, self.settings.daily_loss_pct)
        if self.risk.state.halted:
            self._flatten_all(marks, now_ms, self.risk.state.halt_reason)
            if not self._halt_notified:
                self._notify(f"Halt {self.risk.state.halt_reason}. Entries zu, Lage wird geschlossen.")
                self._halt_notified = True
        else:
            self._halt_notified = False

    def _flatten_all(self, marks: dict[str, float], now_ms: int, reason: str) -> None:
        for order in list(self.book.orders.values()):
            self.manager.cancel(order.symbol, order.client_oid, order.order_id)
        for strategy in self.strategies:
            grids = getattr(strategy, "grids", None)
            if not grids:
                continue
            for grid in grids.values():
                grid.orders.clear()
        for pos in list(self.book.positions):
            if pos.qty <= 0:
                continue
            intent = OrderIntent(
                strategy_id=pos.strategy_id,
                symbol=pos.symbol,
                market=pos.market,
                book_side="sell" if pos.side == "long" else "buy",
                position_side=pos.side,
                purpose="emergency",
                order_type="market",
                size=pos.qty,
                leverage=pos.leverage,
                post_only=False,
                reason=reason,
            )
            spec = self.specs.get(pos.symbol) or FALLBACK_SPECS.get(pos.symbol)
            if spec is None:
                continue
            result = self.manager.submit(
                intent, spec, mark=marks.get(pos.symbol) or pos.entry, ts_ms=now_ms
            )
            if result.fill is not None:
                self.by_id[pos.strategy_id].consume_fill(result.fill, self.book)

    def _reconcile(self, now_ms: int) -> None:
        if hasattr(self.broker, "adopt"):
            self.broker.adopt(self.book)
        if hasattr(self.broker, "mirror_positions"):
            self.broker.mirror_positions(self._position_rows())
        fills: list[Fill] = []
        frozen: set[str] = set()
        notes = reconcile(
            self.book, self.broker, self.specs, self.settings.maker_fee, now_ms, fills=fills, frozen=frozen
        )
        self.risk.state.frozen_symbols = frozen
        for fill in fills:
            self.by_id[fill.strategy_id].consume_fill(fill, self.book)
            self._protect_after_fill(fill)
            self._notify_fill(fill)
        for note in notes:
            logger.warning(note)
        if self.settings.mode == "live" and not self._prepared_live:
            client = self.broker.client
            self._log_prepare("Hedge-Modus", client.set_position_mode())
            for strategy in self.strategies:
                cfg = self.settings.strategy(strategy.id)
                if not cfg.enabled:
                    continue
                for symbol in cfg.symbols:
                    self._log_prepare(f"{symbol} Margin", client.set_margin_mode(symbol))
                    for side in ("long", "short"):
                        self._log_prepare(f"{symbol} {side} Hebel", client.set_leverage(symbol, cfg.leverage, side))
            self._prepared_live = True

    @staticmethod
    def _log_prepare(label: str, response) -> None:
        code = str((response or {}).get("code", "")) if isinstance(response, dict) else ""
        if code and code != "00000":
            logger.warning(f"Live-Vorbereitung {label}: {response}")

    def _protect_after_fill(self, fill: Fill) -> None:
        """Live: Stop und Ziel einer neuen Lage liegen sofort auch auf der Börse."""
        if self.settings.mode != "live" or fill.purpose != "open" or not hasattr(self.broker, "client"):
            return
        pos = self.book.find_position(fill.strategy_id, fill.symbol, fill.position_side)
        if pos is None or pos.stop is None:
            return
        tp = f"{pos.take_profit}" if pos.take_profit is not None else None
        response = self.broker.client.place_position_stop(fill.symbol, pos.side, f"{pos.stop}", tp)
        self._log_prepare(f"{fill.symbol} Stop", response)

    def _apply_stop(self, stop) -> None:
        pos = self.book.find_position(stop.strategy_id, stop.symbol, stop.position_side)
        if pos is None:
            return
        if pos.side == "long" and pos.stop is not None and stop.new_stop <= pos.stop:
            return
        if pos.side == "short" and pos.stop is not None and stop.new_stop >= pos.stop:
            return
        pos.stop = stop.new_stop
        pos.breakeven_armed = True
        if self.settings.mode == "live" and hasattr(self.broker, "client"):
            self.broker.client.place_position_stop(stop.symbol, pos.side, f"{stop.new_stop}")

    def _funding(self, views: dict[str, SymbolView], now_ms: int) -> None:
        bucket = now_ms // FUNDING_MS
        symbols = {pos.symbol for pos in self.book.positions}
        for strategy in self.strategies:
            grids = getattr(strategy, "grids", {}) or {}
            symbols.update(grids.keys())
        for symbol in symbols:
            previous = self.last_funding_bucket.get(symbol)
            self.last_funding_bucket[symbol] = bucket
            if previous is None or previous == bucket:
                continue
            view = views.get(symbol)
            mark = view.last if view else 0.0
            if mark <= 0:
                continue
            owner = self.book.symbol_owner(symbol)
            strategy = self.by_id.get(owner) if owner else None
            if strategy is not None and hasattr(strategy, "on_funding"):
                strategy.on_funding(self.book, symbol, mark, self.settings.funding_rate_8h)
            elif owner:
                self.book.accrue_funding(owner, symbol, mark, self.settings.funding_rate_8h)

    def _persist(self) -> None:
        payload = export_payload(
            self.settings.mode,
            self.book,
            self.risk.state,
            {item.id: item.export_state() for item in self.strategies},
            {symbol: bucket * FUNDING_MS for symbol, bucket in self.last_funding_bucket.items()},
        )
        save_state(self.state_path, payload)

    def _position_rows(self) -> list[dict]:
        return [
            {"symbol": pos.symbol, "side": pos.side, "qty": pos.qty, "entry": pos.entry, "leverage": pos.leverage}
            for pos in self.book.positions
            if pos.qty > 0
        ]

    def _notify(self, text: str) -> None:
        telegram.send(text, self.settings.telegram_token, self.settings.telegram_chat_id)

    def _notify_fill(self, fill: Fill) -> None:
        self._notify(
            f"{fill.strategy_id} {fill.symbol} {fill.purpose} {fill.position_side} "
            f"{fill.qty} @ {fill.price:.6g} ({fill.reason})"
        )

    def status_payload(self) -> dict:
        marks = dict(self.last_marks)
        equity = self.book.account_equity(marks)
        sleeves = {}
        for strategy_id, ledger in self.book.ledgers.items():
            cfg = self.settings.strategy(strategy_id)
            sleeves[strategy_id] = {
                "enabled": cfg.enabled,
                "entries_paused": cfg.entries_paused,
                "allocation": cfg.allocation,
                "symbols": cfg.symbols,
                "note": cfg.note,
                "sleeve_cash": round(self.book.sleeve_cash(strategy_id), 6),
                "realized": round(ledger.realized, 6),
                "fees": round(ledger.fees, 6),
                "funding": round(ledger.funding, 6),
                "unrealized": round(self.book.unrealized(strategy_id, marks), 6),
            }
        key_set = bool(self.settings.api_key) and not self.settings.api_key.startswith("your_")
        return {
            "agent": "unified",
            "mode": self.settings.mode,
            "paper": self.settings.mode != "live",
            "account": {
                "uid": self.settings.account_uid,
                "name": self.settings.account_name,
                "key_configured": key_set,
                "secret_configured": self.settings.keys_look_real(),
            },
            "equity": round(equity, 6),
            "anchor": self.book.anchor,
            "halted": self.risk.state.halted,
            "halt_reason": self.risk.state.halt_reason,
            "frozen": sorted(self.risk.state.frozen_symbols),
            "locks": self.book.locks,
            "conflict_policy": "symbol_lock",
            "sleeves": sleeves,
            "positions": [pos.to_dict() for pos in self.book.positions if pos.qty > 0],
            "orders": [order.to_dict() for order in self.book.orders.values()],
            "notes": self.notes,
            "last_cycle": self.last_cycle,
        }

    def closed_payload(self) -> dict:
        trades = [trade.to_dict() for trade in self.book.closed]
        return {
            "agent": "unified",
            "mode": self.settings.mode,
            "count": len(trades),
            "trades": trades,
        }


def _marks(views: dict[str, SymbolView]) -> dict[str, float]:
    marks = {}
    for symbol, view in views.items():
        if view.last > 0:
            marks[symbol] = view.last
        elif view.mid > 0:
            marks[symbol] = view.mid
    return marks


def _f(value) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
