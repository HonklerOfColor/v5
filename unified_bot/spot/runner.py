"""Hält die Spot-Module und ruft sie einmal täglich. Wird vom Bot-Loop angestoßen."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from loguru import logger

from unified_bot.spot.client import BitgetSpotClient
from unified_bot.spot.modules import SpotModule, TrendEnsembleModule, TrendFilterModule


def state_file(state_dir: Path, module_id: str) -> Path:
    return Path(state_dir) / f"spot_{module_id}.json"


class SpotRunner:
    def __init__(
        self,
        settings,
        state_dir: Path,
        notify: Callable[[str], None] | None = None,
        client: BitgetSpotClient | None = None,
        module_classes: tuple[type[SpotModule], ...] = (TrendEnsembleModule, TrendFilterModule),
    ):
        self.settings = settings
        self.state_dir = Path(state_dir)
        # Öffentlicher Client ohne Key: Die Module lesen nur Kerzen, Specs und Ticker.
        self.client = client if client is not None else BitgetSpotClient()
        self.modules: list[SpotModule] = [
            cls(settings, self.client, state_file(self.state_dir, cls.id), notify=notify) for cls in module_classes
        ]
        self.by_id = {module.id: module for module in self.modules}
        self.last_reports: dict[str, dict] = {}
        for module in self.modules:
            logger.info(
                f"Spot-Modul {module.id}: {'an' if module.enabled else 'aus'}, PAPER, Kapital {module.capital:.2f} USDT, "
                f"Zustand {module.state_path}"
            )
        if settings.mode == "live":
            logger.warning("Bot-Modus live: Spot-Module laufen weiterhin nur als Paper und senden keine Orders.")

    def tick(self, now_ms: int) -> list[dict]:
        reports: list[dict] = []
        for module in self.modules:
            report = module.tick(now_ms)
            if report is not None:
                reports.append(report)
                self.last_reports[module.id] = report
        return reports

    def module(self, module_id: str) -> SpotModule | None:
        return self.by_id.get(module_id)

    def index_payload(self) -> dict:
        return {
            "agent": "unified",
            "mode": "paper",
            "bot_mode": self.settings.mode,
            "modules": {
                module.id: {
                    "enabled": module.enabled,
                    "equity": round(module.ledger.equity(module.ledger.last_prices), 4),
                    "start_capital": module.capital,
                    "alarm": module.alarm,
                    "last_run": module.status()["last_run"],
                    "url": f"/api/v5/spot/{module.id}",
                }
                for module in self.modules
            },
        }

    def total_paper_capital(self) -> float:
        return sum(module.ledger.equity(module.ledger.last_prices) for module in self.modules)
