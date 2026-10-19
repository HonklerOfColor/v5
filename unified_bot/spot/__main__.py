"""Werkzeuge für die Spot-Module. Keines sendet Orders.

  python3 -m unified_bot.spot export-trades --module spot_trend_ensemble [--out trades.csv]
  python3 -m unified_bot.spot status --module spot_trendfilter_btceth
  python3 -m unified_bot.spot check-account      # nur lesend, nutzt den Key aus config.py
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from unified_bot.settings import load_settings
from unified_bot.spot.account_check import check_spot_account
from unified_bot.spot.export import trades_to_csv
from unified_bot.spot.modules import TrendEnsembleModule, TrendFilterModule
from unified_bot.spot.runner import state_file

MODULES = {TrendEnsembleModule.id: TrendEnsembleModule, TrendFilterModule.id: TrendFilterModule}


def _load_module(settings, module_id: str, state_dir: Path):
    cls = MODULES[module_id]
    return cls(settings, client=None, state_path=state_file(state_dir, module_id))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Spot-Module (Paper): Export, Status, Konto-Check.")
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export-trades", help="Paper-Trades als CSV (Semikolon)")
    export.add_argument("--module", required=True, choices=sorted(MODULES))
    export.add_argument("--state-dir", default="state")
    export.add_argument("--out", default="-")
    status = sub.add_parser("status", help="Status-JSON eines Moduls aus der Zustandsdatei")
    status.add_argument("--module", required=True, choices=sorted(MODULES))
    status.add_argument("--state-dir", default="state")
    sub.add_parser("check-account", help="Spot-Fähigkeit von at-HNK prüfen (nur lesend)")
    args = parser.parse_args(argv)
    settings = load_settings()
    if args.command == "export-trades":
        module = _load_module(settings, args.module, Path(args.state_dir))
        text = trades_to_csv(module.ledger.trades, module.id)
        if args.out == "-":
            sys.stdout.write(text)
        else:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"{len(module.ledger.trades)} Trades nach {args.out} geschrieben.")
        return 0
    if args.command == "status":
        module = _load_module(settings, args.module, Path(args.state_dir))
        print(json.dumps(module.status(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "check-account":
        result = check_spot_account(settings)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if not result["errors"] else 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
