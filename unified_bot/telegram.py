"""Telegram bleibt stumm, solange Token und Chat leer sind. Der Token wird nicht geloggt."""

from __future__ import annotations

import os

import requests


def send(text: str, token: str = "", chat_id: str = "") -> bool:
    token = (token or os.getenv("TELEGRAM_BOT_TOKEN", "")).strip()
    chat_id = (chat_id or os.getenv("TELEGRAM_CHAT_ID", "")).strip()
    if not token or not chat_id:
        return False
    try:
        response = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            data={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10,
        )
        body = response.json()
        return bool(body.get("ok"))
    except (requests.RequestException, ValueError):
        return False
