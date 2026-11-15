from __future__ import annotations

import json
import math
import random
import time
from typing import Any, Dict, List, Optional

from jubbiopy import Colors

from .. import config
from ..core import CommandError, Ctx, Bot
from ..economy_data import COMMODITY_VOLATILITY, MATERIALS, STOCKS, commodity_symbol
from ..utils import embed, fold, money, ok, parse_amount, sparkline

HISTORY = 24
MAX_ORDER = 100_000


def step_price(price: float, base: float, volatility: float, boost: float = 0.0) -> float:
    reversion = 0.05 * (math.log(base) - math.log(price))
    price *= math.exp(random.gauss(0, volatility) + reversion + boost)
    return min(max(price, base * 0.2), base * 5)


def change_text(history: List[float], price: float) -> str:
    if not history:
        return "—"
    first = history[0]
    pct = (price - first) / first * 100 if first else 0
    arrow = "🟢 ▲" if pct > 0.05 else "🔴 ▼" if pct < -0.05 else "⚪ ="
    return f"{arrow} %{abs(pct):.1f}"


class Market:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.last_sold: Dict[str, int] = {}
        self.seed()
        bot.every(60, self.tick)
        self.register()

    def seed(self) -> None:
        now = time.time()
        for row in self.db.all("SELECT symbol, price FROM stocks WHERE kind = 'hisse'"):
            if row["symbol"] not in STOCKS:
                with self.db.transaction():
                    for h in self.db.all("SELECT user_id, qty FROM holdings WHERE symbol = ? AND qty > 0", (row["symbol"],)):
                        self.db.add_balance(h["user_id"], int(h["qty"] * row["price"]))
                    self.db.execute("DELETE FROM holdings WHERE symbol = ?", (row["symbol"],))
                    self.db.execute("DELETE FROM stocks WHERE symbol = ?", (row["symbol"],))
        for symbol, (name, base, vol) in STOCKS.items():
            self.db.execute("INSERT OR IGNORE INTO stocks (symbol, name, kind, price, base, volatility, updated, history) "
                            "VALUES (?, ?, 'hisse', ?, ?, ?, ?, ?)", (symbol, name, base, base, vol, now, json.dumps([base])))
        for key, (label, _, base, _) in MATERIALS.items():
            self.db.execute("INSERT OR IGNORE INTO stocks (symbol, name, kind, price, base, volatility, updated, history) "
                            "VALUES (?, ?, 'emtia', ?, ?, ?, ?, ?)",
                            (commodity_symbol(key), label, base, base, COMMODITY_VOLATILITY, now, json.dumps([base])))

    async def tick(self) -> None:
        now = time.time()
        companies = {r["ticker"]: r for r in self.db.all("SELECT ticker, level, sold FROM companies")}
        with self.db.transaction():
            for row in self.db.all("SELECT * FROM stocks"):
                steps = min(HISTORY, int((now - row["updated"]) // config.STOCK_TICK))
                if steps <= 0:
                    continue
                price, base, history = row["price"], row["base"], json.loads(row["history"])
                boost = 0.0
                if row["kind"] == "sirket" and row["symbol"] in companies:
                    company = companies[row["symbol"]]
                    base = 100.0 * company["level"]
                    sold_now = company["sold"]
                    sold_before = self.last_sold.get(row["symbol"], sold_now)
                    self.last_sold[row["symbol"]] = sold_now
                    boost = min(0.03, (sold_now - sold_before) / 2000)
                for i in range(steps):
                    price = step_price(price, base, row["volatility"], boost if i == 0 else 0.0)
                    history = (history + [round(price, 2)])[-HISTORY:]
                self.db.execute("UPDATE stocks SET price = ?, base = ?, history = ?, updated = updated + ? WHERE symbol = ?",
                                (price, base, json.dumps(history), steps * config.STOCK_TICK, row["symbol"]))

    def stock(self, symbol: Optional[str]) -> Optional[Any]:
        if not symbol:
            return None
        return self.db.one("SELECT * FROM stocks WHERE symbol = ? AND kind != 'emtia'", (symbol.upper().strip("$"),))

    def register(self) -> None:
        cmd = self.bot.command

        @cmd("borsa", category="borsa", usage="[al|sat <sembol> <adet|hepsi>] | [sembol]", aliases=("stock", "stocks", "hisse"),
             description="Hisse senedi al-sat. Fiyatlar 10 dakikada bir değişir.",
             examples=("borsa", "borsa HLDG", "borsa al HLDG 10", "borsa sat KRPT hepsi"))
        async def borsa(ctx: Ctx) -> None:
            sub = fold(ctx.arg(0, ""))
            if sub in ("al", "buy"):
                return await self.trade(ctx, True)
            if sub in ("sat", "sell"):
                return await self.trade(ctx, False)
            if sub and self.stock(ctx.arg(0)):
                return await self.detail(ctx, self.stock(ctx.arg(0)))
            rows = self.db.all("SELECT * FROM stocks WHERE kind = 'hisse' ORDER BY symbol")
            companies = self.db.all("SELECT * FROM stocks WHERE kind = 'sirket' ORDER BY price DESC LIMIT 10")

            def line(r) -> str:
                history = json.loads(r["history"])
                return (f"`{r['symbol']:<5}` **{money(r['price'])}** {change_text(history, r['price'])} "
                        f"{sparkline(history[-12:])}\n└ {r['name']}")

            e = embed(f"📈 {config.BOT_NAME} Borsası", "\n".join(line(r) for r in rows), Colors.Blurple)
            if companies:
                e.add_fields({"name": "🏢 Oyuncu Şirketleri", "value": "\n".join(line(r) for r in companies)[:1024]})
            fee = "Pro'da komisyon yok 💎" if self.bot.is_pro(ctx.author.id) else f"Komisyon %{config.STOCK_FEE * 100:g}"
            e.set_footer(text=f"Değişim: son 4 saat • {fee} • .borsa al <sembol> <adet>")
            await ctx.send(embed=e)

        @cmd("portföy", category="borsa", usage="[@kullanıcı]", aliases=("portfoy", "portfolio", "hisselerim"),
             description="Sahip olduğun hisseler, kâr / zarar.")
        async def portfolio(ctx: Ctx) -> None:
            user = await self.bot.resolve_user(ctx, ctx.arg(0), default_self=True)
            rows = self.db.all("SELECT h.symbol, h.qty, h.cost, s.price, s.name FROM holdings h "
                               "JOIN stocks s ON s.symbol = h.symbol WHERE h.user_id = ? AND h.qty > 0 ORDER BY h.symbol",
                               (user.id,))
            lines, value, cost = [], 0, 0
            for r in rows:
                now = int(r["qty"] * r["price"])
                pnl = now - r["cost"]
                value += now
                cost += r["cost"]
                lines.append(f"`{r['symbol']}` × {r['qty']} — {money(now)} "
                             f"({'🟢 +' if pnl >= 0 else '🔴 '}{money(pnl)})")
            total_pnl = value - cost
            await ctx.send(embed=embed(f"💼 {user.username} — Portföy", "\n".join(lines) or
                                       "Hissen yok. Almak için: `.borsa al <sembol> <adet>`")
                           .set_footer(text=f"Toplam: {money(value)} • Kâr/Zarar: {'+' if total_pnl >= 0 else ''}"
                                            f"{money(total_pnl)}"))

        @cmd("pazar", category="sirket", aliases=("emtia", "fiyatlar"),
             description="Malzemelerin güncel pazar fiyatları (.sat ile bu fiyattan satarsın).")
        async def bazaar(ctx: Ctx) -> None:
            lines = []
            for key, (label, emoji, base, pro_only) in MATERIALS.items():
                row = self.db.one("SELECT price, history FROM stocks WHERE symbol = ?", (commodity_symbol(key),))
                price = row["price"] if row else base
                history = json.loads(row["history"]) if row else []
                lines.append(f"{emoji} **{label}** — {money(price)} {change_text(history, price)}"
                             + (" 💎" if pro_only else ""))
            await ctx.send(embed=embed("🏪 Pazar Fiyatları", "\n".join(lines))
                           .set_footer(text="💎 = sadece Pro şirketler üretebilir • .sat <malzeme> <adet>"))

    async def detail(self, ctx: Ctx, row: Any) -> None:
        history = json.loads(row["history"])
        held = self.db.one("SELECT qty, cost FROM holdings WHERE user_id = ? AND symbol = ?", (ctx.author.id, row["symbol"]))
        e = (embed(f"📊 {row['name']} ({row['symbol']})", f"```\n{sparkline(history) or '—'}\n```")
             .add_fields({"name": "Fiyat", "value": money(row["price"]), "inline": True},
                         {"name": "Değişim", "value": change_text(history, row["price"]), "inline": True},
                         {"name": "En düşük / yüksek", "value": f"{money(min(history or [row['price']]))} / "
                                                                  f"{money(max(history or [row['price']]))}", "inline": True}))
        if held and held["qty"]:
            e.add_fields({"name": "Sende", "value": f"{held['qty']} adet — {money(held['qty'] * row['price'])}"})
        await ctx.send(embed=e)

    async def trade(self, ctx: Ctx, buy: bool) -> None:
        row = self.stock(ctx.arg(1))
        if row is None:
            raise CommandError("Böyle bir hisse yok. Liste için: `.borsa`")
        symbol, price = row["symbol"], float(row["price"])
        unit = math.ceil(price) if buy else math.floor(price)
        pro = self.bot.is_pro(ctx.author.id)
        fee_rate = 0 if pro else config.STOCK_FEE
        held = self.db.one("SELECT qty, cost FROM holdings WHERE user_id = ? AND symbol = ?", (ctx.author.id, symbol))
        have = held["qty"] if held else 0
        if buy:
            affordable = int(self.db.balance(ctx.author.id) // max(1, unit * (1 + fee_rate)))
            qty = parse_amount(ctx.arg(2), affordable)
        else:
            qty = parse_amount(ctx.arg(2), have)
        if not qty or qty > MAX_ORDER:
            raise CommandError(f"Geçerli bir adet yaz (1 - {MAX_ORDER}). Örnek: `.borsa {'al' if buy else 'sat'} {symbol} 10`")
        gross = unit * qty
        fee = math.ceil(gross * fee_rate)
        with self.db.transaction():
            if buy:
                if not self.db.take_balance(ctx.author.id, gross + fee):
                    raise CommandError(f"Yeterli paran yok. Gereken: **{money(gross + fee)}**")
                self.db.execute("INSERT INTO holdings (user_id, symbol, qty, cost) VALUES (?, ?, ?, ?) "
                                "ON CONFLICT(user_id, symbol) DO UPDATE SET qty = qty + excluded.qty, cost = cost + excluded.cost",
                                (ctx.author.id, symbol, qty, gross + fee))
            else:
                if have < qty:
                    raise CommandError(f"Elinde sadece **{have}** adet `{symbol}` var.")
                cost_part = int(held["cost"] * qty / have)
                self.db.execute("UPDATE holdings SET qty = qty - ?, cost = cost - ? WHERE user_id = ? AND symbol = ?",
                                (qty, cost_part, ctx.author.id, symbol))
                self.db.add_balance(ctx.author.id, gross - fee)
        verb = "aldın" if buy else "sattın"
        text = f"**{qty}** adet `{symbol}` {verb}. Birim: {money(unit)} • Toplam: **{money(gross)}**"
        if fee:
            text += f"\nKomisyon: {money(fee)} (Pro üyelerde komisyon yok 💎)"
        if not buy:
            text += f"\nAlış maliyetine göre: {'🟢 +' if gross - fee >= cost_part else '🔴 '}{money(gross - fee - cost_part)}"
        await ctx.send(embed=ok(text))


def setup(bot: Bot) -> Market:
    return Market(bot)
