from __future__ import annotations

import argparse
import asyncio
import logging
import os

from dotenv import load_dotenv

from .config import load_settings
from .service import daemon, run_once
from .store import open_store
from .telegram import TelegramNotifier


def main() -> None:
    parser = argparse.ArgumentParser(prog="pisorent")
    parser.add_argument("command", choices=("run", "daemon", "telegram"))
    parser.add_argument("--config", default="config.yaml")
    args = parser.parse_args()
    load_dotenv()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = load_settings(args.config)
    if args.command == "run":
        asyncio.run(run_once(settings))
    elif args.command == "daemon":
        asyncio.run(daemon(settings))
    else:
        token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not token:
            raise RuntimeError("TELEGRAM_BOT_TOKEN is required")
        store = open_store(settings.runtime["database_path"])
        TelegramNotifier(token, os.getenv("TELEGRAM_CHAT_ID", ""), store).run_polling()


if __name__ == "__main__":
    main()
