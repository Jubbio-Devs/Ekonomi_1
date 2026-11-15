from __future__ import annotations

import random
import time
from typing import Dict

from jubbiopy import Colors

from .. import config
from ..core import CommandError, Ctx, Bot
from ..economy_data import MATERIALS, WORK_TEXTS, commodity_symbol, find_material, material_label
from ..utils import embed, fmt_duration, money, ok, parse_amount


class Economy:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.register()

    def work_cooldown(self, user_id: str) -> int:
        return config.PRO_WORK_COOLDOWN if self.bot.is_pro(user_id) else config.WORK_COOLDOWN

    def commodity_price(self, key: str) -> float:
        row = self.db.one("SELECT price FROM stocks WHERE symbol = ?", (commodity_symbol(key),))
        return float(row["price"]) if row else float(MATERIALS[key][2])

    def net_worth(self, user_id: str) -> Dict[str, int]:
        balance = self.db.balance(user_id)
        items = sum(int(self.commodity_price(k) * q) for k, q in self.db.inventory(user_id).items() if k in MATERIALS)
        stocks = 0
        for row in self.db.all("SELECT h.qty, s.price FROM holdings h JOIN stocks s ON s.symbol = h.symbol "
                               "WHERE h.user_id = ?", (user_id,)):
            stocks += int(row["qty"] * row["price"])
        company = self.db.one("SELECT vault, stock, material FROM companies WHERE owner_id = ?", (user_id,))
        company_value = 0
        if company:
            company_value = int(company["vault"] + company["stock"] * self.commodity_price(company["material"]))
        total = balance + items + stocks + company_value
        return {"balance": balance, "items": items, "stocks": stocks, "company": company_value, "total": total}

    def register(self) -> None:
        cmd = self.bot.command

        @cmd("çalış", category="ekonomi", aliases=("calis", "work", "is"),
             description=f"Çalışıp {config.WORK_MIN}-{config.WORK_MAX} {config.CURRENCY} kazanırsın (günde 1 kez, Pro: 12 saatte bir ×1.5).")
        async def work(ctx: Ctx) -> None:
            user = self.db.user(ctx.author.id)
            cooldown = self.work_cooldown(ctx.author.id)
            remaining = user["last_work"] + cooldown - time.time()
            if remaining > 0:
                raise CommandError(f"Yorgunsun! 😴 Tekrar çalışabilmek için **{fmt_duration(remaining)}** beklemelisin.")
            pro = self.bot.is_pro(ctx.author.id)
            amount = random.randint(config.WORK_MIN, config.WORK_MAX)
            bonus = int(amount * (config.PRO_WORK_MULTIPLIER - 1)) if pro else 0
            total = amount + bonus
            self.db.execute("UPDATE users SET balance = balance + ?, earned = earned + ?, last_work = ? WHERE user_id = ?",
                            (total, total, time.time(), ctx.author.id))
            text = f"{random.choice(WORK_TEXTS)} ve **{money(amount)}** kazandın!"
            if bonus:
                text += f"\n💎 Pro bonusu: **+{money(bonus)}**"
            e = (embed("💼 Mesai Bitti", text, Colors.Green)
                 .add_fields({"name": "Bakiye", "value": money(self.db.balance(ctx.author.id)), "inline": True},
                             {"name": "Sonraki mesai", "value": f"<t:{int(time.time() + cooldown)}:R>", "inline": True}))
            await ctx.send(embed=e)

        @cmd("bakiye", category="ekonomi", usage="[@kullanıcı]", aliases=("para", "cuzdan", "bal", "balance"),
             description="Norm bakiyeni gösterir.")
        async def balance(ctx: Ctx) -> None:
            user = await self.bot.resolve_user(ctx, ctx.arg(0), default_self=True)
            worth = self.net_worth(user.id)
            badge = " 💎" if self.bot.is_pro(user.id) else ""
            await ctx.send(embed=embed(f"{config.CURRENCY_EMOJI} {user.username}{badge}").add_fields(
                {"name": "Cüzdan", "value": money(worth["balance"]), "inline": True},
                {"name": "Toplam servet", "value": money(worth["total"]), "inline": True}))

        @cmd("gönder", category="ekonomi", usage="@kullanıcı <miktar>", aliases=("gonder", "transfer", "pay", "ode"),
             description=f"Başka birine {config.CURRENCY} gönderir (%{int(config.TRANSFER_FEE * 100)} kesinti, Pro'da kesinti yok).",
             examples=("gönder @ali 500", "gönder @ali 1,5k"))
        async def give(ctx: Ctx) -> None:
            target = await self.bot.resolve_user(ctx, ctx.arg(0))
            if target is None:
                raise CommandError(f"Kullanım: {ctx.usage()}")
            if target.id == ctx.author.id or getattr(target, "bot", False):
                raise CommandError("Kendine veya botlara para gönderemezsin.")
            amount = parse_amount(ctx.arg(1), self.db.balance(ctx.author.id))
            if not amount:
                raise CommandError("Geçerli bir miktar yaz. Örnek: `.gönder @ali 500`")
            fee = 0 if self.bot.is_pro(ctx.author.id) else int(amount * config.TRANSFER_FEE)
            with self.db.transaction():
                if not self.db.take_balance(ctx.author.id, amount):
                    raise CommandError(f"Yeterli paran yok. Bakiye: **{money(self.db.balance(ctx.author.id))}**")
                self.db.add_balance(target.id, amount - fee)
            text = f"<@{target.id}> kullanıcısına **{money(amount - fee)}** gönderildi."
            if fee:
                text += f"\n💸 Transfer kesintisi: {money(fee)} (Pro üyelerde kesinti yok)"
            await ctx.send(embed=ok(text))

        @cmd("zenginler", category="ekonomi", aliases=("siralama", "top", "lb", "leaderboard"),
             description="En zengin 10 kişi (cüzdan).")
        async def leaderboard(ctx: Ctx) -> None:
            rows = self.db.all("SELECT user_id, balance FROM users WHERE balance > 0 ORDER BY balance DESC LIMIT 10")
            medals = ["🥇", "🥈", "🥉"]
            lines = [f"{medals[i] if i < 3 else f'`{i + 1}.`'} <@{r['user_id']}>"
                     f"{' 💎' if self.bot.is_pro(r['user_id']) else ''} — **{money(r['balance'])}**"
                     for i, r in enumerate(rows)]
            rank = self.db.one("SELECT COUNT(*) + 1 AS n FROM users WHERE balance > ?",
                               (self.db.balance(ctx.author.id),))["n"]
            await ctx.send(embed=embed("🏆 En Zenginler", "\n".join(lines) or "Henüz kimse para kazanmadı.")
                           .set_footer(text=f"Senin sıran: {rank}"))

        @cmd("profil", category="ekonomi", usage="[@kullanıcı]", aliases=("profile", "p"),
             description="Ekonomi profilin: servet, şirket, Pro durumu, oyun istatistikleri.")
        async def profile(ctx: Ctx) -> None:
            user = await self.bot.resolve_user(ctx, ctx.arg(0), default_self=True)
            data = self.db.user(user.id)
            worth = self.net_worth(user.id)
            company = self.db.one("SELECT name, ticker, level FROM companies WHERE owner_id = ?", (user.id,))
            pro, until = self.db.pro_until(user.id)
            if self.bot.is_owner(user.id):
                pro_text = "👑 Bot sahibi"
            elif pro:
                pro_text = "💎 Kalıcı" if until is None else f"💎 <t:{int(until)}:R> bitiyor"
            else:
                pro_text = "Yok"
            next_work = data["last_work"] + self.work_cooldown(user.id)
            e = (embed(f"👤 {user.username}{' 💎' if self.bot.is_pro(user.id) else ''}")
                 .add_fields({"name": "Cüzdan", "value": money(worth["balance"]), "inline": True},
                             {"name": "Hisseler", "value": money(worth["stocks"]), "inline": True},
                             {"name": "Envanter", "value": money(worth["items"]), "inline": True},
                             {"name": "Şirket", "value": f"🏢 {company['name']} (`{company['ticker']}`) Sv.{company['level']}"
                              if company else "Yok", "inline": True},
                             {"name": "Toplam servet", "value": f"**{money(worth['total'])}**", "inline": True},
                             {"name": "Pro", "value": pro_text, "inline": True},
                             {"name": "Toplam kazanç", "value": money(data["earned"]), "inline": True},
                             {"name": "TKM", "value": f"{data['tkm_win']} G / {data['tkm_loss']} M", "inline": True},
                             {"name": "Çalışma", "value": "✅ Hazır" if next_work <= time.time()
                              else f"<t:{int(next_work)}:R>", "inline": True}))
            avatar = getattr(user, "avatar_url", None)
            if avatar:
                e.set_thumbnail(avatar)
            await ctx.send(embed=e)

        @cmd("envanter", category="ekonomi", usage="[@kullanıcı]", aliases=("env", "inv", "inventory", "canta"),
             description="Sahip olduğun malzemeler ve pazar değerleri.")
        async def inventory(ctx: Ctx) -> None:
            user = await self.bot.resolve_user(ctx, ctx.arg(0), default_self=True)
            items = self.db.inventory(user.id)
            lines, total = [], 0
            for key, qty in items.items():
                if key not in MATERIALS:
                    continue
                value = int(self.commodity_price(key) * qty)
                total += value
                lines.append(f"{material_label(key)} × **{qty}** — {money(value)}")
            await ctx.send(embed=embed(f"🎒 {user.username} — Envanter", "\n".join(lines) or
                                       "Envanter boş. Şirketlerden malzeme almak için: `.market`")
                           .set_footer(text=f"Toplam pazar değeri: {money(total)}"))

        @cmd("sat", category="sirket", usage="<malzeme> <adet|hepsi>", aliases=("sell",),
             description="Envanterindeki malzemeyi pazara güncel fiyattan satar.", examples=("sat demir 20", "sat odun hepsi"))
        async def sell(ctx: Ctx) -> None:
            key = find_material(ctx.arg(0))
            if key is None:
                raise CommandError("Malzeme bulunamadı. Malzemeler: " + ", ".join(m[0] for m in MATERIALS.values()))
            have = self.db.inventory(ctx.author.id).get(key, 0)
            qty = parse_amount(ctx.arg(1), have)
            if not qty:
                raise CommandError(f"Kaç tane satacağını yaz. Kullanım: {ctx.usage()}")
            price = self.commodity_price(key)
            total = int(price * qty)
            with self.db.transaction():
                if not self.db.take_item(ctx.author.id, key, qty):
                    raise CommandError(f"Yeterli {material_label(key)} yok (sende {have} var).")
                self.db.add_balance(ctx.author.id, total)
            await ctx.send(embed=ok(f"{material_label(key)} × {qty} pazara satıldı: **+{money(total)}** "
                                    f"(birim {money(price)})"))


def setup(bot: Bot) -> Economy:
    return Economy(bot)
