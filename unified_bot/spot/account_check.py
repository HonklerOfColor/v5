"""Prüft nur lesend, ob der vorhandene Key für at-HNK (UID 9711026741) ein Spot-Konto mit Handelsrecht sieht.

Wird NICHT automatisch ausgeführt. Aufruf von Hand:  python3 -m unified_bot.spot check-account
Es wird keine Order gesendet, kein Transfer ausgelöst. Der Key wird nicht ausgegeben.
"""

from __future__ import annotations

from unified_bot.spot.client import BitgetSpotClient, SpotApiError


def check_spot_account(settings, client: BitgetSpotClient | None = None) -> dict:
    result: dict = {
        "account_uid_expected": settings.account_uid,
        "account_name": settings.account_name,
        "keys_configured": settings.keys_look_real(),
        "uid_matches": None,
        "spot_account_readable": False,
        "spot_trade_permission": None,
        "authorities": [],
        "usdt_available": None,
        "assets_count": None,
        "btcusdt_online": None,
        "ethusdt_online": None,
        "errors": [],
        "verdict": "",
    }
    if not settings.keys_look_real():
        result["errors"].append("API-Key, Secret oder Passphrase fehlen oder sind Platzhalter (config.py).")
        result["verdict"] = "nicht prüfbar"
        return result
    client = client or BitgetSpotClient(settings.api_key, settings.secret_key, settings.passphrase)
    try:
        info = client.get_account_info()
        result["spot_account_readable"] = True
        user_id = str(info.get("userId") or info.get("uid") or "")
        result["uid_matches"] = (user_id == settings.account_uid) if user_id else None
        authorities = info.get("authorities") or []
        if isinstance(authorities, str):
            authorities = [authorities]
        result["authorities"] = [str(item) for item in authorities]
        lowered = [item.lower() for item in result["authorities"]]
        if lowered:
            result["spot_trade_permission"] = any("spot" in item and "trade" in item for item in lowered) or "trade" in lowered
        result["parent_id"] = str(info.get("parentId") or "")
        result["trader_type"] = str(info.get("traderType") or "")
    except SpotApiError as exc:
        result["errors"].append(f"account/info: {exc.code} {exc.msg}")
    try:
        assets = client.get_spot_assets()
        result["assets_count"] = len(assets)
        for row in assets:
            if str(row.get("coin") or "").upper() == "USDT":
                try:
                    result["usdt_available"] = float(row.get("available") or 0)
                except (TypeError, ValueError):
                    result["usdt_available"] = None
    except SpotApiError as exc:
        result["errors"].append(f"account/assets: {exc.code} {exc.msg}")
    try:
        specs = client.get_symbols()
        result["btcusdt_online"] = specs.get("BTCUSDT").online if "BTCUSDT" in specs else False
        result["ethusdt_online"] = specs.get("ETHUSDT").online if "ETHUSDT" in specs else False
    except SpotApiError as exc:
        result["errors"].append(f"public/symbols: {exc.code} {exc.msg}")
    if result["uid_matches"] is False:
        result["verdict"] = "Key gehört zu einer anderen UID"
    elif result["spot_account_readable"] and result["usdt_available"] is not None:
        if result["spot_trade_permission"] is False:
            result["verdict"] = "Spot-Konto lesbar, aber kein Spot-Handelsrecht auf dem Key"
        else:
            result["verdict"] = "Spot-Konto lesbar; Handelsrecht laut Key-Rechten: " + (
                "ja" if result["spot_trade_permission"] else "unbekannt (Rechte nicht lesbar)"
            )
    elif result["spot_account_readable"]:
        result["verdict"] = "Spot-Konto lesbar, Bestände nicht lesbar"
    else:
        result["verdict"] = "Spot-Konto nicht lesbar"
    return result
