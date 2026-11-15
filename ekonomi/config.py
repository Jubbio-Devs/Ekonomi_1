from __future__ import annotations

import os

VERSION = "1.0.0"

TOKEN = os.environ.get("BOT_TOKEN", "")
BOT_NAME = os.environ.get("BOT_NAME", "Ekonomi Botu")
PREFIX = os.environ.get("PREFIX", ".")
PREFIXES = tuple(os.environ.get("PREFIXES", f"{PREFIX} /").split())
OWNER_ID = os.environ.get("OWNER_ID", "")
DATA_DIR = os.environ.get("DATA_DIR", os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data"))
SUPPORT_INVITE = os.environ.get("SUPPORT_INVITE", "")
LOGO_URL = os.environ.get("LOGO_URL", "")
COLOR = int(os.environ.get("COLOR", "F3A921"), 16)

CURRENCY = os.environ.get("CURRENCY", "coin")
CURRENCY_EMOJI = os.environ.get("CURRENCY_EMOJI", "🪙")

WORK_MIN, WORK_MAX = 50, 150
WORK_COOLDOWN = 24 * 3600
TRANSFER_FEE = 0.05
TKM_COOLDOWN = 5
TKM_MAX_BET = 5_000
STOCK_FEE = 0.01
STOCK_TICK = 10 * 60

COMPANY_COST = 1_000
COMPANY_PRODUCE_COOLDOWN = 60 * 60
MARKET_FEE = 0.02

PRO_WORK_MULTIPLIER = 1.5
PRO_WORK_COOLDOWN = 12 * 3600
PRO_TKM_MAX_BET = 25_000
PRO_PRODUCE_COOLDOWN = 30 * 60
PRO_PRODUCE_BONUS = 1.25
