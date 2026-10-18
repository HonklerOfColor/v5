"""Paper-Loop. Live nur mit --live und beiden Schaltern in config.py."""

from __future__ import annotations

import argparse
import threading
import time
from pathlib import Path

from loguru import logger

from unified_bot.runner import Bot, setup_logging
from unified_bot.settings import load_settings
from unified_bot.status_server import start_status_server


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Einheitlicher Bitget-Bot. Default ist Paper.")
    parser.add_argument("--once", action="store_true", help="ein Zyklus, dann Ende")
    parser.add_argument("--live", action="store_true", help="echte Orders, nur mit DRY_RUN=False und LIVE_TRADING=True")
    parser.add_argument("--port", type=int, default=None)
    parser.add_argument("--state", default="state/unified_state.json")
    args = parser.parse_args(argv)
    settings = load_settings(force_live=args.live)
    if args.port is not None:
        settings.status_port = args.port
    setup_logging(settings.log_level)
    bot = Bot(settings, state_path=Path(args.state))
    server = start_status_server(bot, settings.status_host, settings.status_port)
    thread = threading.Thread(target=server.serve_forever, name="status", daemon=True)
    thread.start()
    logger.info(
        f"Status auf http://127.0.0.1:{settings.status_port}  Modus {settings.mode}. "
        "Paper sendet keine Orders."
    )
    try:
        while True:
            bot.run_cycle()
            if args.once:
                break
            time.sleep(settings.loop_interval)
    except KeyboardInterrupt:
        logger.warning("Stop.")
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
