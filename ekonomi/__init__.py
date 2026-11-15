from __future__ import annotations

import os
from importlib import import_module
from typing import Any

from . import config
from .core import Bot
from .db import Database

__version__ = config.VERSION

MODULES = ("info", "economy", "market", "company", "games", "pro")


def create_bot(db_path: str = "", **client_options: Any) -> Bot:
    bot = Bot(Database(db_path or os.path.join(config.DATA_DIR, "ekonomi.db")), **client_options)
    for name in MODULES:
        bot.modules[name] = import_module(f".modules.{name}", __name__).setup(bot)
    return bot
