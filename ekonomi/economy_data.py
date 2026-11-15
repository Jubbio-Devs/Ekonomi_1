from __future__ import annotations

from typing import Dict, Optional, Tuple

from .utils import fold

MATERIALS: Dict[str, Tuple[str, str, int, bool]] = {
    "odun": ("Odun", "🪵", 20, False),
    "tas": ("Taş", "🪨", 25, False),
    "kumas": ("Kumaş", "🧵", 35, False),
    "bakir": ("Bakır", "🟠", 50, False),
    "demir": ("Demir", "⛓️", 70, False),
    "altin": ("Altın", "🥇", 150, False),
    "elektronik": ("Elektronik", "💾", 220, True),
    "elmas": ("Elmas", "💎", 400, True),
}

STOCKS: Dict[str, Tuple[str, float, float]] = {
    "HLDG": ("Anadolu Holding", 250, 0.025),
    "BLTK": ("Bulut Teknoloji", 180, 0.03),
    "YZLM": ("Yazılım A.Ş.", 120, 0.035),
    "TKNO": ("Anadolu Teknoloji", 140, 0.035),
    "PYTH": ("PyTech", 90, 0.04),
    "ENRJ": ("Anadolu Enerji", 75, 0.03),
    "KRPT": ("Kripto Madencilik", 60, 0.08),
}

COMMODITY_VOLATILITY = 0.04

PRODUCTION_COST = 0.4
PRICE_MIN, PRICE_MAX = 0.5, 3.0
COMPANY_DUMP_RATE = 0.85
MAX_LEVEL = 10

WORK_TEXTS = [
    "💻 Bir müşteri için Jubbio botu yazdın",
    "🧱 İnşaatta tuğla taşıdın",
    "☕ Kafede barista olarak çalıştın",
    "📦 Kargo dağıttın",
    "🎨 Bir şirketin logosunu tasarladın",
    "🛠️ Komşunun bilgisayarını tamir ettin",
    "📚 Özel ders verdin",
    "🚕 Taksi şoförlüğü yaptın",
    "🌾 Tarlada hasat yaptın",
    "🎮 Turnuvada oyun yayını yaptın",
    "🍕 Pizza kuryeliği yaptın",
    "🐍 JubbioPy ile otomasyon scripti yazdın",
]


def find_material(text: Optional[str]) -> Optional[str]:
    if not text:
        return None
    key = fold(text.strip())
    for suffix in ("lar", "ler"):
        if key.endswith(suffix) and key[:-3] in MATERIALS:
            key = key[:-3]
    if key in MATERIALS:
        return key
    for name, (label, emoji, _, _) in MATERIALS.items():
        if key == fold(label) or text.strip() == emoji:
            return name
    return None


def material_label(key: str) -> str:
    label, emoji, _, _ = MATERIALS[key]
    return f"{emoji} {label}"


def commodity_symbol(key: str) -> str:
    return key.upper()
