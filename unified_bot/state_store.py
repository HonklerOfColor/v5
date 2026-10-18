"""Atomarer Zustand. Paper und Live werden nicht vermischt."""

from __future__ import annotations

import json
import os
from pathlib import Path

from unified_bot.book import Book
from unified_bot.risk import RiskState


def save_state(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def load_state(path: Path) -> dict:
    if not path.is_file():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return raw if isinstance(raw, dict) else {}


def export_payload(
    mode: str,
    book: Book,
    risk: RiskState,
    strategy_state: dict,
    last_funding_ms: dict,
) -> dict:
    return {
        "version": 1,
        "mode": mode,
        "book": book.to_dict(),
        "risk": risk.to_dict(),
        "strategies": strategy_state,
        "last_funding_ms": last_funding_ms,
    }


def restore_book(raw: dict, mode: str, allocations: dict[str, float], anchor_fallback: float) -> tuple[Book, RiskState, dict, dict, list[str]]:
    notes: list[str] = []
    if not raw:
        book = Book(anchor_fallback, allocations)
        return book, RiskState(), {}, {}, notes
    saved_mode = raw.get("mode")
    if saved_mode and saved_mode != mode:
        notes.append(f"Zustand aus Modus {saved_mode} ignoriert (jetzt {mode}).")
        book = Book(anchor_fallback, allocations)
        return book, RiskState(), {}, {}, notes
    body = raw.get("book") or {}
    if not body.get("anchor"):
        body = dict(body)
        body["anchor"] = anchor_fallback
    book = Book.from_dict(body, allocations)
    book.sync_allocations(allocations)
    risk = RiskState.from_dict(raw.get("risk"))
    strategies = raw.get("strategies") or {}
    funding = {str(k): int(v) for k, v in (raw.get("last_funding_ms") or {}).items()}
    return book, risk, strategies, funding, notes
