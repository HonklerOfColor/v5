"""Kleiner Status. /api/agent/closed ist die Trade-Liste mit Strategie-Etikett."""

from __future__ import annotations

import html
import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def start_status_server(bot, host: str, port: int) -> ThreadingHTTPServer:
    handler = _handler(bot)
    server = ThreadingHTTPServer((host, port), handler)
    server.daemon_threads = True
    return server


def _handler(bot):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path in ("/api/agent/closed", "/api/agent/closed/"):
                self._json(bot.closed_payload())
                return
            if path in ("/api/agent/status", "/api/status", "/api/health"):
                body = bot.status_payload()
                if path == "/api/health":
                    body = {"ok": True, "mode": body["mode"], "equity": body["equity"]}
                self._json(body)
                return
            if path in ("/", "/index.html"):
                self._html(_page(bot.status_payload(), bot.closed_payload(), bot.spot_index_payload()))
                return
            if path.startswith("/api/v5/spot"):
                self._spot(path)
                return
            self._json({"error": "not_found"}, status=404)

        def _spot(self, path: str) -> None:
            parts = [part for part in path.split("/") if part]
            # parts: api, v5, spot[, <modul>[, trades.csv]]
            if len(parts) == 3:
                index = bot.spot_index_payload()
                if index is None:
                    self._json({"error": "spot_modules_not_attached"}, status=404)
                else:
                    self._json(index)
                return
            module_id = parts[3]
            if len(parts) == 5 and parts[4] == "trades.csv":
                text = bot.spot_trades_csv(module_id)
                if text is None:
                    self._json({"error": "unknown_module"}, status=404)
                    return
                raw = text.encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/csv; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="{module_id}_trades.csv"')
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)
                return
            if len(parts) == 4:
                body = bot.spot_payload(module_id)
                if body is None:
                    self._json({"error": "unknown_module"}, status=404)
                else:
                    self._json(body)
                return
            self._json({"error": "not_found"}, status=404)

        def log_message(self, fmt: str, *args) -> None:
            return

        def _json(self, payload: dict, status: int = 200) -> None:
            raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

        def _html(self, page: str) -> None:
            raw = page.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)

    return Handler


def _spot_section(spot: dict | None) -> str:
    if not spot:
        return "<h2>Spot-Module (Paper)</h2><p>Nicht angehängt.</p>"
    rows = []
    for module_id, info in (spot.get("modules") or {}).items():
        last = (info.get("last_run") or {}).get("signal_day") or "—"
        rows.append(
            "<tr>"
            f"<td><a href=\"/api/v5/spot/{html.escape(str(module_id))}\">{html.escape(str(module_id))}</a></td>"
            f"<td>{'an' if info.get('enabled') else 'aus'}</td>"
            f"<td>{float(info.get('start_capital') or 0):.2f}</td>"
            f"<td>{float(info.get('equity') or 0):.2f}</td>"
            f"<td>{html.escape(str(last))}</td>"
            f"<td>{'ALARM' if info.get('alarm') else 'nein'}</td>"
            f"<td><a href=\"/api/v5/spot/{html.escape(str(module_id))}/trades.csv\">CSV</a></td>"
            "</tr>"
        )
    return (
        "<h2>Spot-Module (Paper)</h2>"
        f"<p>Modus <strong>paper</strong>, Bot-Modus {html.escape(str(spot.get('bot_mode')))}. "
        "Eigene Ledger, keine Spot-Orders. <a href=\"/api/v5/spot\">/api/v5/spot</a></p>"
        "<table><thead><tr><th>Modul</th><th>Status</th><th>Start</th><th>Equity</th>"
        "<th>Signaltag</th><th>Alarm</th><th>Trades</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _page(status: dict, closed: dict, spot: dict | None = None) -> str:
    rows = []
    for strategy_id, sleeve in status.get("sleeves", {}).items():
        flag = "an" if sleeve["enabled"] and not sleeve["entries_paused"] else "aus"
        rows.append(
            "<tr>"
            f"<td>{strategy_id}</td>"
            f"<td>{flag}</td>"
            f"<td>{sleeve['allocation']:.0%}</td>"
            f"<td>{sleeve['sleeve_cash']:.2f}</td>"
            f"<td>{sleeve['realized']:.4f}</td>"
            f"<td>{sleeve['fees']:.4f}</td>"
            f"<td>{sleeve['funding']:.4f}</td>"
            f"<td>{', '.join(sleeve['symbols']) or '—'}</td>"
            f"<td>{sleeve['note']}</td>"
            "</tr>"
        )
    trades = closed.get("trades") or []
    trade_rows = []
    for trade in trades[-30:][::-1]:
        trade_rows.append(
            "<tr>"
            f"<td>{trade['strategy']}</td>"
            f"<td>{trade['symbol']}</td>"
            f"<td>{trade['side']}</td>"
            f"<td>{trade['net_pnl']:.4f}</td>"
            f"<td>{trade['exit_reason']}</td>"
            "</tr>"
        )
    if not trade_rows:
        trade_rows.append("<tr><td colspan='5'>Noch keine geschlossenen Trades.</td></tr>")
    notes = "".join(f"<li>{note}</li>" for note in (status.get("notes") or [])[:12])
    if not notes:
        notes = "<li>Keine Notiz aus dem letzten Zyklus.</li>"
    halt = status.get("halt_reason") or "nein"
    return f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Bitget Unified — Paper</title>
<style>
  body {{ font: 15px/1.45 ui-sans-serif, system-ui, sans-serif; margin: 0; background: #10140f; color: #e7ecdf; }}
  main {{ max-width: 1100px; margin: 0 auto; padding: 24px 16px 48px; }}
  h1 {{ font-size: 1.4rem; margin-bottom: 0.2rem; }}
  p {{ color: #b7c2ae; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 0.92rem; }}
  th, td {{ text-align: left; padding: 8px 6px; border-bottom: 1px solid #2a3326; vertical-align: top; }}
  a {{ color: #d2e38a; }}
  code {{ color: #d2e38a; }}
</style>
</head>
<body>
<main>
  <h1>Ein Konto, alle Strategien</h1>
  <p>Konto <strong>{(status.get('account') or {}).get('name', '')}</strong>
  UID {(status.get('account') or {}).get('uid', '')} ·
  Modus <strong>{status.get('mode')}</strong> · Equity {status.get('equity')} USDT ·
  Halt: {halt} · Konflikte: exklusive Symbol-Sperre.</p>
  <p>JSON: <a href="/api/agent/status">/api/agent/status</a> ·
  <a href="/api/agent/closed">/api/agent/closed</a></p>
  <h2>Strategien</h2>
  <table>
    <thead><tr><th>Strategie</th><th>Entries</th><th>Anteil</th><th>Sleeve</th><th>Realisiert</th><th>Fees</th><th>Funding</th><th>Symbole</th><th>Hinweis</th></tr></thead>
    <tbody>{''.join(rows)}</tbody>
  </table>
  <h2>Letzter Zyklus</h2>
  <ul>{notes}</ul>
  {_spot_section(spot)}
  <h2>Geschlossene Trades ({closed.get('count', 0)})</h2>
  <table>
    <thead><tr><th>Strategie</th><th>Symbol</th><th>Seite</th><th>Netto</th><th>Grund</th></tr></thead>
    <tbody>{''.join(trade_rows)}</tbody>
  </table>
</main>
</body>
</html>"""
