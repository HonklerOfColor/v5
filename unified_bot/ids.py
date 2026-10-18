"""clientOid-Vorsilben. Bitget nettet je Symbol und Seite — die Vorsilbe ist das Etikett."""

from __future__ import annotations

# Genau drei Zeichen, alphanumerisch, keine Vorsilbe ist Präfix einer anderen.
PREFIXES: dict[str, str] = {
    "reversal": "rv1",
    "sniper": "sn3",
    "grid": "grd",
    "trendjoin": "tj4",
    "funding_arb": "fra",
    "daily_trend": "dtr",
}

_BY_PREFIX = {prefix: strategy_id for strategy_id, prefix in PREFIXES.items()}


def prefix_for(strategy_id: str) -> str:
    try:
        return PREFIXES[strategy_id]
    except KeyError as exc:
        raise KeyError(f"keine clientOid-Vorsilbe für {strategy_id}") from exc


def owner_of(client_oid: str) -> str | None:
    if not client_oid or len(client_oid) < 3:
        return None
    return _BY_PREFIX.get(client_oid[:3])


def make_client_oid(strategy_id: str, seq: int) -> str:
    """Alphanumerisch, kurz genug für Bitget (üblich ≤ 32)."""
    if seq < 0 or seq > 999_999_999:
        raise ValueError("clientOid-Zähler außerhalb des Bereichs")
    return f"{prefix_for(strategy_id)}{seq:09d}"
