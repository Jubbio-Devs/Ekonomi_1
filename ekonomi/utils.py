from __future__ import annotations

import re
import shlex
from typing import Any, List, Optional

from jubbiopy import Colors, EmbedBuilder

from . import config

_FOLD = str.maketrans("çğıöşüÇĞİÖŞÜâîû", "cgiosuCGIOSUaiu")
DURATION_RE = re.compile(r"(\d+)\s*(sn|sa|dk|hf|ay|yil|yıl|s|m|h|g|d|w|y)", re.IGNORECASE)
UNITS = {"s": 1, "sn": 1, "m": 60, "dk": 60, "h": 3600, "sa": 3600, "d": 86400, "g": 86400,
         "w": 604800, "hf": 604800, "ay": 30 * 86400, "y": 365 * 86400, "yil": 365 * 86400, "yıl": 365 * 86400}
ID_RE = re.compile(r"^<?[@#]?[!&]?(\d{1,25})>?$")


def fold(text: str) -> str:
    return text.replace("I", "ı").replace("İ", "i").lower().translate(_FOLD)


def split_args(text: str) -> List[str]:
    try:
        return shlex.split(text)
    except ValueError:
        return text.split()


def parse_id(value: Any) -> Optional[str]:
    if value is None:
        return None
    match = ID_RE.match(str(value).strip())
    return match.group(1) if match else None


def parse_duration(text: Optional[str]) -> Optional[int]:
    if not text:
        return None
    text = text.strip().lower()
    if text.isdigit():
        return int(text) * 60
    total, consumed = 0, 0
    for match in DURATION_RE.finditer(text):
        total += int(match.group(1)) * UNITS[match.group(2).lower()]
        consumed += len(match.group(0))
    if total <= 0 or consumed < len(text.replace(" ", "")):
        return None
    return total


def fmt_duration(seconds: float) -> str:
    seconds = int(max(0, seconds))
    parts = []
    for name, size in (("gün", 86400), ("saat", 3600), ("dakika", 60), ("saniye", 1)):
        if seconds >= size:
            parts.append(f"{seconds // size} {name}")
            seconds %= size
    return " ".join(parts[:2]) or "0 saniye"


def money(amount: float) -> str:
    return f"{int(amount):,}".replace(",", ".") + f" {config.CURRENCY}"


def parse_amount(text: Optional[str], available: Optional[int] = None) -> Optional[int]:
    if not text:
        return None
    text = fold(text.strip())
    if text in ("hepsi", "tum", "tumu", "all", "max") and available is not None:
        return available
    multiplier = 1
    if text[-1:] in ("k", "b"):
        multiplier, text = 1_000, text[:-1]
    elif text[-1:] == "m":
        multiplier, text = 1_000_000, text[:-1]
    text = text.replace(".", "").replace(",", ".") if multiplier == 1 else text.replace(",", ".")
    try:
        value = int(float(text) * multiplier)
    except ValueError:
        return None
    return value if value > 0 else None


def embed(title: Optional[str] = None, description: Optional[str] = None, color: int = config.COLOR) -> EmbedBuilder:
    e = EmbedBuilder().set_color(color)
    if title:
        e.set_title(title)
    if description:
        e.set_description(description)
    return e


def ok(text: str) -> EmbedBuilder:
    return embed(description=f"✅ {text}", color=Colors.Green)


def err(text: str) -> EmbedBuilder:
    return embed(description=f"❌ {text}", color=Colors.Red)


def warn(text: str) -> EmbedBuilder:
    return embed(description=f"⚠️ {text}", color=Colors.Orange)


def progress_bar(value: float, total: float, size: int = 10) -> str:
    filled = 0 if total <= 0 else round(size * min(1.0, value / total))
    return "▰" * filled + "▱" * (size - filled)


SPARK = "▁▂▃▄▅▆▇█"


def sparkline(values: List[float]) -> str:
    if len(values) < 2:
        return ""
    low, high = min(values), max(values)
    span = (high - low) or 1
    return "".join(SPARK[int((v - low) / span * (len(SPARK) - 1))] for v in values)
