"""Die zwei Spot-Module. Paper only: Es gibt keinen Pfad, der eine Spot-Order an Bitget schickt.

Tageslauf (einmal je UTC-Tag, nach 00:05 UTC, idempotent über Neustarts):
1. Specs live laden (API-Fehler bricht den Lauf ab, später neuer Versuch).
2. Abgeschlossene Tageskerzen holen, Kerze des Vortags t ist die Signalkerze. Die laufende Kerze fliegt in closed_only() raus.
3. Zielgewichte und Flags exakt wie die Referenz (signals.py, universe.py).
4. Paper: Umschichtung mit Ticker-Kurs, Gebühr, Slippage, Mindestorder, Rundung (broker.py).
5. Schatten: derselbe Tagesschritt mit idealisierten Kosten zum Schlusskurs t (engine.py).
6. Equity-Reihe, Drawdown, Abweichung, Alarme, Zustand speichern.
"""

from __future__ import annotations

import json
import math
import os
import traceback
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from loguru import logger

from unified_bot.spot import params as P
from unified_bot.spot.broker import PaperSpotBroker
from unified_bot.spot.candles import (
    DailySeries,
    day_iso,
    day_of_ms,
    previous_month_end,
    series_from_candles,
)
from unified_bot.spot.client import SpotApiError
from unified_bot.spot.engine import ShadowState, decide_trades
from unified_bot.spot.ledger import SpotLedger
from unified_bot.spot.signals import ensemble_signal, sigma_annualized, trend_weights
from unified_bot.spot.specs import SpotSpec
from unified_bot.spot.universe import excluded_by_name, rank_candidates, select_universe

NAN = float("nan")


class RetryLater(RuntimeError):
    """Daten noch nicht vollständig (z. B. Kerze von gestern fehlt). Lauf später wiederholen."""


@dataclass
class DailyInput:
    series: dict[str, DailySeries]
    targets: dict[str, float]
    flags: dict[str, bool]
    meta: dict = field(default_factory=dict)
    commit: dict = field(default_factory=dict)   # Zustand, der erst nach erfolgreichem Lauf gilt


def _finite(value) -> bool:
    try:
        return value == value and not math.isinf(float(value))
    except (TypeError, ValueError):
        return False


class SpotModule:
    id = ""
    title = ""
    prereg = ""
    alarm_drawdown = 0.0
    alarm_deviation_pp = 0.0
    alarm_trades_per_month: int | None = None
    default_min_order_usdt = 10.0
    parameters: dict = {}

    def __init__(
        self,
        settings,
        client,
        state_path: Path,
        notify: Callable[[str], None] | None = None,
        capital: float | None = None,
        enabled: bool | None = None,
        broker: PaperSpotBroker | None = None,
    ):
        self.settings = settings
        self.client = client
        self.state_path = Path(state_path)
        self.notify = notify
        self.capital = float(capital if capital is not None else settings.spot_capital.get(self.id, P.DEFAULT_CAPITAL_USDT))
        self.enabled = bool(enabled if enabled is not None else settings.spot_enabled.get(self.id, True))
        self.broker = broker or PaperSpotBroker()
        if getattr(self.broker, "mode", "") != "paper":
            raise SystemExit(f"{self.id}: nur der Paper-Broker ist zugelassen.")
        self.ledger = SpotLedger.fresh(self.capital)
        self.shadow = ShadowState(equity=self.capital)
        self.equity_history: list[dict] = []
        self.last_run_day: int | None = None
        self.last_run_ms: int = 0
        self.last_processed_day: int | None = None
        self.next_attempt_ms: int = 0
        self.last_error: str = ""
        self.alarm: bool = False
        self.alarm_reasons: list[str] = []
        self.alarm_since: str = ""
        self.notes: list[str] = []
        self.last_targets: dict[str, float] = {}
        self.last_meta: dict = {}
        self.specs: dict[str, SpotSpec] = {}
        self.extra: dict = {}
        self.load_state()

    # ── Zustand ─────────────────────────────────────────────────────────────
    def state_dict(self) -> dict:
        return {
            "version": 1,
            "module": self.id,
            "mode": "paper",
            "capital": self.capital,
            "ledger": self.ledger.to_dict(),
            "shadow": self.shadow.to_dict(),
            "equity_history": self.equity_history[-P.EQUITY_HISTORY_DAYS :],
            "last_run_day": self.last_run_day,
            "last_run_ms": self.last_run_ms,
            "last_processed_day": self.last_processed_day,
            "next_attempt_ms": self.next_attempt_ms,
            "last_error": self.last_error,
            "alarm": self.alarm,
            "alarm_reasons": list(self.alarm_reasons),
            "alarm_since": self.alarm_since,
            "notes": self.notes[-40:],
            "last_targets": dict(self.last_targets),
            "last_meta": self.last_meta,
            "extra": self.extra,
        }

    def persist(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.state_path.with_suffix(self.state_path.suffix + ".tmp")
        temporary.write_text(json.dumps(self.state_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.state_path)

    def load_state(self) -> None:
        if not self.state_path.is_file():
            return
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(f"{self.id}: Zustand nicht lesbar ({exc}), Start mit leerem Ledger")
            return
        if not isinstance(raw, dict) or raw.get("module") != self.id:
            return
        if raw.get("mode") not in (None, "paper"):
            logger.warning(f"{self.id}: Zustand hat Modus {raw.get('mode')}, ignoriert")
            return
        saved_capital = float(raw.get("capital") or self.capital)
        if abs(saved_capital - self.capital) > 1e-9:
            logger.warning(
                f"{self.id}: Startkapital in config ({self.capital:.2f}) weicht vom Zustand ({saved_capital:.2f}) ab. "
                "Der Zustand behält sein Kapital; für ein neues Kapital die Zustandsdatei löschen."
            )
            self.capital = saved_capital
        self.ledger = SpotLedger.from_dict(raw.get("ledger"), self.capital)
        self.shadow = ShadowState.from_dict(raw.get("shadow"), self.capital)
        self.equity_history = list(raw.get("equity_history") or [])
        self.last_run_day = raw.get("last_run_day")
        self.last_run_ms = int(raw.get("last_run_ms") or 0)
        self.last_processed_day = raw.get("last_processed_day")
        self.next_attempt_ms = int(raw.get("next_attempt_ms") or 0)
        self.last_error = str(raw.get("last_error") or "")
        self.alarm = bool(raw.get("alarm", False))
        self.alarm_reasons = list(raw.get("alarm_reasons") or [])
        self.alarm_since = str(raw.get("alarm_since") or "")
        self.notes = list(raw.get("notes") or [])
        self.last_targets = {str(k): float(v) for k, v in (raw.get("last_targets") or {}).items()}
        self.last_meta = dict(raw.get("last_meta") or {})
        self.extra = dict(raw.get("extra") or {})
        self.load_extra(self.extra)

    def load_extra(self, extra: dict) -> None:
        return None

    # ── Takt ────────────────────────────────────────────────────────────────
    def due(self, now_ms: int) -> bool:
        if not self.enabled:
            return False
        today = day_of_ms(now_ms)
        if now_ms < today * P.DAY_MS + P.RUN_AFTER_UTC_MINUTES * 60_000:
            return False
        if self.last_run_day is not None and int(self.last_run_day) >= today:
            return False
        if now_ms < self.next_attempt_ms:
            return False
        return True

    def tick(self, now_ms: int) -> dict | None:
        if not self.due(now_ms):
            return None
        return self.run(now_ms)

    def run(self, now_ms: int) -> dict:
        try:
            return self._run(now_ms)
        except (SpotApiError, RetryLater) as exc:
            self.last_error = str(exc)
            self.next_attempt_ms = now_ms + P.RETRY_AFTER_MINUTES * 60_000
            logger.warning(f"{self.id}: Tageslauf verschoben ({exc}); neuer Versuch in {P.RETRY_AFTER_MINUTES} min")
            self.persist()
            return {"module": self.id, "ok": False, "error": str(exc)}
        except Exception as exc:  # noqa: BLE001 - der Perp-Loop darf nicht an Spot sterben
            self.last_error = f"{type(exc).__name__}: {exc}"
            self.next_attempt_ms = now_ms + P.RETRY_AFTER_MINUTES * 60_000
            logger.error(f"{self.id}: Tageslauf abgebrochen: {self.last_error}\n{traceback.format_exc()}")
            self.persist()
            return {"module": self.id, "ok": False, "error": self.last_error}

    # ── Tageslauf ───────────────────────────────────────────────────────────
    def compute(self, t: int, since: int, now_ms: int, specs: dict[str, SpotSpec]) -> DailyInput:
        raise NotImplementedError

    def _run(self, now_ms: int) -> dict:
        today = day_of_ms(now_ms)
        t = today - 1
        notes: list[str] = []
        if self.settings.mode == "live":
            text = (
                f"{self.id}: Bot läuft LIVE, dieses Spot-Modul bleibt trotzdem PAPER. "
                "Es werden keine Spot-Orders gesendet (Live-Spot ist nicht gebaut)."
            )
            logger.warning(text)
            notes.append(text)
        if self.last_processed_day is not None and int(self.last_processed_day) >= t:
            self.last_run_day = today
            self.last_run_ms = now_ms
            self.next_attempt_ms = 0
            self.persist()
            return {"module": self.id, "ok": True, "skipped": "already_processed", "day": day_iso(t)}
        since = t if self.last_processed_day is None else int(self.last_processed_day) + 1
        since = max(since, t - P.MAX_SKIPPED_DAYS_FOR_FLAGS)

        specs = self.client.get_symbols()
        self.specs = specs
        data = self.compute(t, since, now_ms, specs)
        try:
            tickers = self.client.get_tickers()
        except SpotApiError as exc:
            tickers = {}
            notes.append(f"Ticker nicht lesbar ({exc.code}), Ausführung zum Schlusskurs {day_iso(t)}")

        symbols = sorted(set(data.targets) | set(self.ledger.holdings))
        exec_prices: dict[str, float | None] = {}
        close_prices: dict[str, float | None] = {}
        for symbol in symbols:
            series = data.series.get(symbol)
            close = series.close_at(t) if series is not None else NAN
            close_prices[symbol] = close if _finite(close) else None
            ticker_last = float((tickers.get(symbol) or {}).get("last") or 0.0)
            if _finite(close):
                exec_prices[symbol] = ticker_last if ticker_last > 0 else close
            else:
                exec_prices[symbol] = None   # delisted oder ohne Kerze: Glattstellung zum letzten Kurs

        # Paper: Bewertung zum Ausführungskurs, Entscheidung wie run_engine mit Mindestorder
        valuation = {symbol: price for symbol, price in exec_prices.items() if price}
        positions = self.ledger.position_values(valuation)
        equity_before = self.ledger.equity(valuation)
        min_notional = {
            symbol: (specs[symbol].min_trade_usdt if symbol in specs and specs[symbol].min_trade_usdt > 0 else self.default_min_order_usdt)
            for symbol in symbols
        }
        decisions = decide_trades(
            equity_before, positions, exec_prices, data.targets, data.flags, min_notional=min_notional
        )
        executed = []
        for decision in sorted(decisions, key=lambda item: (item.delta > 0, item.symbol)):
            if not decision.trade:
                if decision.reason == "below_min":
                    text = (
                        f"{decision.symbol}: Umschichtung {decision.delta:+.2f} USDT unter Mindestorder "
                        f"{min_notional.get(decision.symbol, self.default_min_order_usdt):g} USDT, übersprungen"
                    )
                    notes.append(text)
                    logger.info(f"{self.id}: {text}")
                continue
            price = exec_prices.get(decision.symbol)
            if price is None:
                series = data.series.get(decision.symbol)
                price = series.last_close_before(t) if series is not None else None
                if price is None:
                    price = self.ledger.price_for(decision.symbol, None)
                notes.append(f"{decision.symbol}: kein Kurs für {day_iso(t)}, Glattstellung zum letzten Kurs {price}")
            result = self.broker.execute(
                self.ledger, decision, price, specs.get(decision.symbol), now_ms, self.default_min_order_usdt
            )
            if result.trade is None:
                notes.append(result.note)
                logger.info(f"{self.id}: {result.note}")
                continue
            executed.append(result.trade)
            logger.info(
                f"{self.id}: PAPER {result.trade.side} {result.trade.symbol} {result.trade.qty:g} @ {result.trade.price:.6g} "
                f"= {result.trade.value_usdt:.2f} USDT, Gebühr {result.trade.fee:.4f} ({decision.reason})"
            )

        # Schatten: derselbe Tag ohne Mindestorder, Kosten 0,15 % auf den Umsatz, Schlusskurs t
        shadow_decisions = self.shadow.step(close_prices, data.targets, data.flags)

        valuation = {symbol: price for symbol, price in exec_prices.items() if price}
        self.ledger.last_prices.update(valuation)
        paper_equity = self.ledger.equity(valuation)
        exposure = self.ledger.exposure(valuation)
        self.equity_history.append(
            {
                "day": t,
                "date": day_iso(t),
                "paper": round(paper_equity, 8),
                "shadow": round(self.shadow.equity, 8),
                "exposure": round(exposure, 6),
                "shadow_exposure": round(self.shadow.gross_exposure(), 6),
                "cash": round(self.ledger.cash, 8),
                "trades": len(executed),
            }
        )
        self.equity_history = self.equity_history[-P.EQUITY_HISTORY_DAYS :]
        self.last_targets = dict(data.targets)
        self.last_meta = data.meta
        for key, value in data.commit.items():
            self.extra[key] = value
        self.last_processed_day = t
        self.last_run_day = today
        self.last_run_ms = now_ms
        self.next_attempt_ms = 0
        self.last_error = ""
        self.notes = notes
        self._evaluate_alarms(t)
        self.persist()
        report = {
            "module": self.id,
            "ok": True,
            "day": day_iso(t),
            "equity": round(paper_equity, 4),
            "shadow_equity": round(self.shadow.equity, 4),
            "trades": [trade.to_dict() for trade in executed],
            "shadow_trades": [item.symbol for item in shadow_decisions if item.trade],
            "alarm": self.alarm,
            "notes": notes,
        }
        logger.info(
            f"{self.id}: Tageslauf {day_iso(t)} PAPER Equity {paper_equity:.2f} Schatten {self.shadow.equity:.2f} "
            f"Exposure {exposure:.0%} Trades {len(executed)} Alarm {self.alarm}"
        )
        return report

    # ── Kennzahlen und Alarme ───────────────────────────────────────────────
    def drawdown(self) -> float:
        peak = self.capital
        last = self.capital
        for row in self.equity_history:
            value = float(row.get("paper") or 0.0)
            peak = max(peak, value)
            last = value
        if peak <= 0:
            return 0.0
        return max(0.0, 1.0 - last / peak)

    def deviation_pp(self, window_days: int = P.ALARM_WINDOW_DAYS) -> tuple[float, int]:
        """Paper-Rendite minus Schatten-Rendite über das Fenster, in Prozentpunkten."""
        if not self.equity_history:
            return 0.0, 0
        last = self.equity_history[-1]
        cutoff = int(last["day"]) - window_days
        base_paper, base_shadow, base_day = self.capital, self.capital, None
        for row in self.equity_history:
            if int(row["day"]) <= cutoff:
                base_paper, base_shadow, base_day = float(row["paper"]), float(row["shadow"]), int(row["day"])
            else:
                break
        if base_paper <= 0 or base_shadow <= 0:
            return 0.0, 0
        span = int(last["day"]) - (base_day if base_day is not None else int(self.equity_history[0]["day"]) - 1)
        pp = (float(last["paper"]) / base_paper - float(last["shadow"]) / base_shadow) * 100.0
        return pp, span

    def alarm_checks(self, t: int) -> list[str]:
        reasons: list[str] = []
        drawdown = self.drawdown()
        if drawdown > self.alarm_drawdown:
            reasons.append(f"Drawdown {drawdown:.1%} > {self.alarm_drawdown:.0%}")
        pp, span = self.deviation_pp()
        if abs(pp) > self.alarm_deviation_pp:
            reasons.append(f"Abweichung Paper vs. Schatten {pp:+.2f} pp über {span} Tage > {self.alarm_deviation_pp:g} pp")
        if self.alarm_trades_per_month is not None:
            month = day_iso(t)[:7]
            count = self.ledger.trades_in_month(month)
            if count > self.alarm_trades_per_month:
                reasons.append(f"{count} Trades im Monat {month} > {self.alarm_trades_per_month}")
        return reasons

    def _evaluate_alarms(self, t: int) -> None:
        reasons = self.alarm_checks(t)
        new = [reason for reason in reasons if reason not in self.alarm_reasons]
        was = self.alarm
        self.alarm = bool(reasons)
        self.alarm_reasons = reasons
        if self.alarm and not was:
            self.alarm_since = day_iso(t)
        if not self.alarm:
            self.alarm_since = ""
            if was:
                logger.info(f"{self.id}: Alarm aufgehoben")
        if new:
            text = f"ALARM {self.id} (Paper): " + "; ".join(new)
            logger.error(text)
            if self.notify is not None:
                try:
                    self.notify(text)
                except Exception as exc:  # noqa: BLE001
                    logger.warning(f"{self.id}: Alarm nicht gesendet ({exc})")

    # ── Status ──────────────────────────────────────────────────────────────
    def status(self) -> dict:
        valuation = dict(self.ledger.last_prices)
        equity = self.ledger.equity(valuation)
        positions = []
        values = self.ledger.position_values(valuation)
        for symbol, qty in sorted(self.ledger.holdings.items()):
            value = values.get(symbol, 0.0)
            positions.append(
                {
                    "symbol": symbol,
                    "qty": qty,
                    "price": valuation.get(symbol),
                    "value_usdt": round(value, 6),
                    "weight": round(value / equity, 6) if equity > 0 else 0.0,
                    "target_weight": round(self.last_targets.get(symbol, 0.0), 6),
                }
            )
        pp, span = self.deviation_pp()
        history = self.equity_history
        last = history[-1] if history else None
        return {
            "module": self.id,
            "title": self.title,
            "mode": "paper",
            "paper": True,
            "bot_mode": self.settings.mode,
            "enabled": self.enabled,
            "prereg": self.prereg,
            "parameters": self.parameters,
            "start_capital": self.capital,
            "equity": round(equity, 6),
            "cash": round(self.ledger.cash, 6),
            "exposure": round(self.ledger.exposure(valuation), 6),
            "positions": positions,
            "targets": {k: round(v, 6) for k, v in sorted(self.last_targets.items())},
            "trades": {
                "count": len(self.ledger.trades),
                "this_month": self.ledger.trades_in_month(day_iso(int(last["day"]))[:7]) if last else 0,
                "fees_total": round(self.ledger.fees_total, 6),
                "last": [trade.to_dict() for trade in self.ledger.trades[-20:]],
            },
            "drawdown": round(self.drawdown(), 6),
            "shadow": {
                "equity": round(self.shadow.equity, 6),
                "exposure": round(self.shadow.gross_exposure(), 6),
                "positions": {k: round(v, 6) for k, v in sorted(self.shadow.positions.items())},
                "costs_total": round(self.shadow.costs_total, 6),
            },
            "deviation_pp": round(pp, 4),
            "deviation_window_days": span,
            "alarm": self.alarm,
            "alarm_reasons": list(self.alarm_reasons),
            "alarm_since": self.alarm_since,
            "alarm_rules": {
                "drawdown": self.alarm_drawdown,
                "deviation_pp": self.alarm_deviation_pp,
                "deviation_window_days": P.ALARM_WINDOW_DAYS,
                "trades_per_month": self.alarm_trades_per_month,
            },
            "last_run": {
                "run_day": day_iso(int(self.last_run_day)) if self.last_run_day is not None else None,
                "signal_day": day_iso(int(self.last_processed_day)) if self.last_processed_day is not None else None,
                "ts_ms": self.last_run_ms,
            },
            "next_attempt_ms": self.next_attempt_ms,
            "last_error": self.last_error,
            "notes": list(self.notes),
            "signals": self.last_meta,
            "equity_history": history[-31:],
            **self.extra_status(),
        }

    def extra_status(self) -> dict:
        return {}


# ── Modul 1 ───────────────────────────────────────────────────────────────────
class TrendEnsembleModule(SpotModule):
    id = P.TREND_ID
    title = "Trend-Ensemble (Donchian 9 Fenster, Top-10 Spot)"
    prereg = "docs/spot_modules/PREREG_trend_ensemble.md (Primärvariante: alle 9 Fenster, B=10, VT=25 %, Cap 1,0)"
    alarm_drawdown = P.TREND_ALARM_DRAWDOWN
    alarm_deviation_pp = P.TREND_ALARM_DEVIATION_PP
    alarm_trades_per_month = None
    default_min_order_usdt = P.TREND_DEFAULT_MIN_ORDER_USDT
    parameters = {
        "windows": list(P.TREND_WINDOWS),
        "B": P.TREND_B,
        "VT": P.TREND_VT,
        "cap": P.TREND_CAP,
        "sigma_days": P.TREND_SIGMA_DAYS,
        "rebalance_threshold": P.REBALANCE_THRESHOLD,
        "universe_volume_days": P.TREND_UNIVERSE_VOLUME_DAYS,
        "universe_min_median_usdt": P.TREND_UNIVERSE_MIN_MEDIAN_USDT,
        "min_history_days": P.TREND_MIN_HISTORY_DAYS,
        "fee": P.FEE_RATE,
        "slippage": P.SLIPPAGE_RATE,
        "granularity": P.GRANULARITY,
    }

    def __init__(self, *args, **kwargs):
        self.universe: list[str] = []
        self.universe_month: str = ""
        self.universe_selected_at: str = ""
        self.universe_report: list[dict] = []
        self.effective_universe: list[str] = []
        super().__init__(*args, **kwargs)

    def load_extra(self, extra: dict) -> None:
        self.universe = list(extra.get("universe") or [])
        self.universe_month = str(extra.get("universe_month") or "")
        self.universe_selected_at = str(extra.get("universe_selected_at") or "")
        self.universe_report = list(extra.get("universe_report") or [])
        self.effective_universe = list(extra.get("effective_universe") or [])

    def _history(self, symbol: str, days: int, now_ms: int):
        try:
            return self.client.get_daily_history(symbol, days, now_ms)
        except SpotApiError as exc:
            if exc.unknown_symbol:
                return []
            raise

    def select_universe(self, t: int, specs: dict[str, SpotSpec], now_ms: int) -> list[str]:
        """Am Monatsende (= Vortag des 1.) Top-B nach 30-Tage-Median-Quote-Volumen, mit Ausschlüssen."""
        month_end = previous_month_end(t)
        tickers = self.client.get_tickers()
        pool = [
            spec for spec in specs.values()
            if spec.quote == "USDT" and spec.online and not excluded_by_name(spec.base)
        ]
        pool.sort(key=lambda spec: -float((tickers.get(spec.symbol) or {}).get("usdt_volume") or 0.0))
        candidates = [spec.symbol for spec in pool[: P.TREND_UNIVERSE_PREFILTER]]
        for symbol in list(self.universe) + list(self.ledger.holdings):
            if symbol in specs and symbol not in candidates:
                candidates.append(symbol)
        series: dict[str, DailySeries] = {}
        first_listed: dict[str, int] = {}
        for symbol in candidates:
            candles = self._history(symbol, P.TREND_UNIVERSE_CANDLES, now_ms)
            built = series_from_candles(symbol, candles, month_end)
            if built is None:
                continue
            series[symbol] = built
            spec = specs.get(symbol)
            if spec is not None and spec.open_time_ms > 0:
                first_listed[symbol] = spec.open_time_ms // P.DAY_MS
        excluded = {symbol for symbol in series if symbol in specs and excluded_by_name(specs[symbol].base)}
        ranked = rank_candidates(series, month_end, excluded, first_listed)
        universe = select_universe(ranked, P.TREND_B)
        report = sorted(
            (item for item in ranked if item.eligible or item.symbol in self.universe),
            key=lambda item: (-(item.median_volume if item.median_volume == item.median_volume else -1.0), item.symbol),
        )
        self.universe = universe
        self.universe_month = day_iso(t)[:7]
        self.universe_selected_at = day_iso(month_end)
        self.universe_report = [
            {
                "symbol": item.symbol,
                "median_volume": round(item.median_volume, 2) if item.median_volume == item.median_volume else None,
                "history_days": item.history_days,
                "eligible": item.eligible,
                "reason": item.reason,
                "selected": item.symbol in universe,
            }
            for item in report[:25]
        ]
        logger.info(f"{self.id}: Universum für {self.universe_month} (Stand {self.universe_selected_at}): {', '.join(universe) or '—'}")
        return universe

    def compute(self, t: int, since: int, now_ms: int, specs: dict[str, SpotSpec]) -> DailyInput:
        month = day_iso(t)[:7]
        if self.universe_month != month or not self.universe:
            self.select_universe(t, specs, now_ms)
        needed = sorted(set(self.universe) | set(self.ledger.holdings))
        series: dict[str, DailySeries] = {}
        for symbol in needed:
            candles = self._history(symbol, P.TREND_LOOKBACK_DAYS, now_ms)
            built = series_from_candles(symbol, candles, t)
            if built is not None:
                series[symbol] = built
        for symbol in self.universe:
            spec = specs.get(symbol)
            built = series.get(symbol)
            if spec is not None and spec.online and (built is None or not _finite(built.close_at(t))):
                raise RetryLater(f"{symbol}: Tageskerze {day_iso(t)} noch nicht verfügbar")
        effective = [symbol for symbol in self.universe if symbol in series and _finite(series[symbol].close_at(t))]
        previous = set(self.effective_universe)
        targets: dict[str, float] = {}
        flags: dict[str, bool] = {}
        meta: dict = {"universe": list(self.universe), "effective_universe": effective, "coins": {}}
        for symbol in needed:
            built = series.get(symbol)
            universe_flag = (symbol in effective) != (symbol in previous)
            if built is None:
                targets[symbol] = 0.0
                flags[symbol] = True
                meta["coins"][symbol] = {"weight": 0.0, "note": "keine Kerzen (delisted?)"}
                continue
            weights, changed, state = trend_weights(built.closes)
            index = built.index_of(t)
            weight = weights[index] if index is not None else 0.0
            in_universe = symbol in effective
            targets[symbol] = weight / P.TREND_B if in_universe else 0.0
            start = built.index_of(max(since, built.first_day))
            flag = False
            if index is not None and start is not None:
                flag = any(changed[start : index + 1])
            flags[symbol] = flag or universe_flag
            sigma = sigma_annualized(built.closes)
            meta["coins"][symbol] = {
                "weight": round(weight, 8),
                "target": round(targets[symbol], 8),
                "sigma90": round(sigma[index], 8) if index is not None and _finite(sigma[index]) else None,
                "windows_long": [window for window, (pos, _) in state.items() if pos == 1],
                "stops": {str(window): stop for window, (pos, stop) in state.items() if pos == 1 and _finite(stop)},
                "close": built.close_at(t),
                "in_universe": in_universe,
                "flag": flags[symbol],
            }
        return DailyInput(
            series=series,
            targets=targets,
            flags=flags,
            meta=meta,
            commit={
                "universe": list(self.universe),
                "universe_month": self.universe_month,
                "universe_selected_at": self.universe_selected_at,
                "universe_report": self.universe_report,
                "effective_universe": effective,
            },
        )

    def extra_status(self) -> dict:
        return {
            "universe": list(self.universe),
            "universe_month": self.universe_month,
            "universe_selected_at": self.universe_selected_at,
            "universe_report": self.universe_report,
        }


# ── Modul 2 ───────────────────────────────────────────────────────────────────
class TrendFilterModule(SpotModule):
    id = P.TF_ID
    title = "Trendfilter BTC+ETH (SMA-Ensemble, Long/Cash)"
    prereg = "docs/spot_modules/PREREG_trendfilter_dca.md (Test 1 Primärvariante: Ensemble, täglich, 50/50)"
    alarm_drawdown = P.TF_ALARM_DRAWDOWN
    alarm_deviation_pp = P.TF_ALARM_DEVIATION_PP
    alarm_trades_per_month = P.TF_ALARM_TRADES_PER_MONTH
    default_min_order_usdt = P.TF_DEFAULT_MIN_ORDER_USDT
    parameters = {
        "symbols": list(P.TF_SYMBOLS),
        "sleeve": P.TF_SLEEVE,
        "sma_windows": list(P.TF_SMA_WINDOWS),
        "rebalance_threshold": P.REBALANCE_THRESHOLD,
        "fee": P.FEE_RATE,
        "slippage": P.SLIPPAGE_RATE,
        "granularity": P.GRANULARITY,
    }

    def compute(self, t: int, since: int, now_ms: int, specs: dict[str, SpotSpec]) -> DailyInput:
        series: dict[str, DailySeries] = {}
        targets: dict[str, float] = {}
        flags: dict[str, bool] = {}
        meta: dict = {"coins": {}}
        for symbol in P.TF_SYMBOLS:
            candles = self.client.get_daily_history(symbol, P.TF_LOOKBACK_DAYS, now_ms)
            built = series_from_candles(symbol, candles, t)
            if built is None or not _finite(built.close_at(t)):
                raise RetryLater(f"{symbol}: Tageskerze {day_iso(t)} noch nicht verfügbar")
            series[symbol] = built
            ensemble = ensemble_signal(built.closes)
            weights = [value * P.TF_SLEEVE if _finite(value) else NAN for value in ensemble]
            index = built.index_of(t)
            weight = weights[index] if index is not None and _finite(weights[index]) else 0.0
            targets[symbol] = weight
            start = built.index_of(max(since, built.first_day))
            flag = False
            if index is not None and start is not None:
                for position in range(max(start, 1), index + 1):
                    a, b = weights[position - 1], weights[position]
                    if _finite(a) and _finite(b) and a != b:
                        flag = True
                        break
            flags[symbol] = flag
            meta["coins"][symbol] = {
                "ensemble": round(ensemble[index], 6) if index is not None and _finite(ensemble[index]) else None,
                "target": round(weight, 6),
                "close": built.close_at(t),
                "flag": flag,
            }
        for symbol in self.ledger.holdings:
            if symbol not in targets:
                targets[symbol] = 0.0
                flags[symbol] = True
        return DailyInput(series=series, targets=targets, flags=flags, meta=meta)
