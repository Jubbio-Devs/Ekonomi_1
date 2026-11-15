from __future__ import annotations

import random
import re
import time
from typing import Any, Dict, Optional

from jubbiopy import ActionRowBuilder, ButtonBuilder, ButtonStyle, Colors

from .. import config
from ..core import CommandError, Ctx, Bot
from ..economy_data import (
    COMPANY_DUMP_RATE,
    MATERIALS,
    MAX_LEVEL,
    PRICE_MAX,
    PRICE_MIN,
    PRODUCTION_COST,
    find_material,
    material_label,
)
from ..utils import embed, err, fmt_duration, fold, money, ok, parse_amount, progress_bar

NAME_RE = re.compile(r"^[\wçğıöşüÇĞİÖŞÜ .&'-]{3,24}$")


def upgrade_cost(level: int) -> Dict[str, int]:
    return {"money": 1500 * level, "odun": 25 * level, "tas": 20 * level, "demir": 10 * level}


class Company:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        bot.component("co:")(self.on_component)
        self.register()

    @property
    def economy(self):
        return self.bot.modules["economy"]

    def of(self, user_id: str) -> Optional[Any]:
        return self.db.one("SELECT * FROM companies WHERE owner_id = ?", (user_id,))

    def find(self, text: Optional[str]) -> Optional[Any]:
        if not text:
            return None
        return (self.db.one("SELECT * FROM companies WHERE ticker = ?", (text.upper(),))
                or self.db.one("SELECT * FROM companies WHERE name = ?", (text,)))

    def make_ticker(self, name: str) -> str:
        letters = re.sub(r"[^A-Z]", "", fold(name).upper()) or "SRKT"
        base = letters[:4].ljust(3, "X")
        ticker, n = base, 1
        while self.db.one("SELECT 1 FROM stocks WHERE symbol = ?", (ticker,)):
            n += 1
            ticker = f"{base[:3]}{n}"
        return ticker

    def produce_cooldown(self, user_id: str) -> int:
        return config.PRO_PRODUCE_COOLDOWN if self.bot.is_pro(user_id) else config.COMPANY_PRODUCE_COOLDOWN

    def info_embed(self, c: Any):
        label, emoji, base, _ = MATERIALS[c["material"]]
        market = self.economy.commodity_price(c["material"])
        stock_row = self.db.one("SELECT price FROM stocks WHERE symbol = ?", (c["ticker"],))
        ready_at = c["last_produce"] + self.produce_cooldown(c["owner_id"])
        return (embed(f"🏢 {c['name']} (`{c['ticker']}`)", f"Sahibi: <@{c['owner_id']}>"
                      + (" 💎" if self.bot.is_pro(c["owner_id"]) else ""))
                .add_fields({"name": "Üretim", "value": f"{emoji} {label}", "inline": True},
                            {"name": "Seviye", "value": f"{c['level']}/{MAX_LEVEL} {progress_bar(c['level'], MAX_LEVEL, 5)}",
                             "inline": True},
                            {"name": "Kasa", "value": money(c["vault"]), "inline": True},
                            {"name": "Stok", "value": f"{c['stock']} adet", "inline": True},
                            {"name": "Satış fiyatı", "value": f"{money(c['price'])} (pazar: {money(market)})", "inline": True},
                            {"name": "Hisse fiyatı", "value": money(stock_row["price"]) if stock_row else "—", "inline": True},
                            {"name": "Toplam satış", "value": f"{c['sold']} adet • {money(c['revenue'])}", "inline": True},
                            {"name": "Üretim", "value": "✅ Hazır" if ready_at <= time.time() else f"<t:{int(ready_at)}:R>",
                             "inline": True},
                            {"name": "Kuruluş", "value": f"<t:{int(c['created'])}:D>", "inline": True}))

    async def on_component(self, interaction: Any) -> None:
        cid = interaction.custom_id
        if not cid.startswith("co:close:"):
            return
        _, _, owner, action = cid.split(":")
        if interaction.user.id != owner:
            return await self.bot.respond(interaction, embeds=[err("Bu buton senin için değil.")], ephemeral=True)
        if action == "no":
            return await interaction.update(embeds=[embed(description="Şirket kapatma iptal edildi.", color=Colors.Grey)],
                                            components=[])
        c = self.of(owner)
        if c is None:
            return await interaction.update(embeds=[err("Şirketin yok.")], components=[])
        stock = self.db.one("SELECT price FROM stocks WHERE symbol = ?", (c["ticker"],))
        price = int(stock["price"]) if stock else 0
        with self.db.transaction():
            for h in self.db.all("SELECT user_id, qty FROM holdings WHERE symbol = ? AND qty > 0", (c["ticker"],)):
                self.db.add_balance(h["user_id"], h["qty"] * price)
            self.db.execute("DELETE FROM holdings WHERE symbol = ?", (c["ticker"],))
            self.db.execute("DELETE FROM stocks WHERE symbol = ?", (c["ticker"],))
            self.db.execute("DELETE FROM companies WHERE id = ?", (c["id"],))
            self.db.add_balance(owner, c["vault"])
        await interaction.update(embeds=[ok(f"🏢 **{c['name']}** kapatıldı. Kasadaki **{money(c['vault'])}** cüzdanına aktarıldı.")],
                                 components=[])

    def register(self) -> None:
        cmd = self.bot.command

        @cmd("şirket", category="sirket",
             usage="<kur|bilgi|üret|fiyat|sat|yatır|çek|yükselt|kapat> ...", aliases=("sirket", "company", "firma"),
             description="Kendi şirketini kur, malzeme üret ve sat.",
             examples=('şirket kur "Demir Çelik A.Ş." demir', "şirket üret", "şirket fiyat 80",
                       "şirket yatır 500", "şirket sat 50", "şirket yükselt", "şirket bilgi @ali"))
        async def company(ctx: Ctx) -> None:
            sub = fold(ctx.arg(0, "bilgi"))
            handler = {
                "kur": self.create, "olustur": self.create, "uret": self.produce, "fiyat": self.set_price,
                "yatir": self.deposit, "cek": self.withdraw, "yukselt": self.upgrade, "sat": self.dump,
                "kapat": self.close, "sil": self.close,
            }.get(sub)
            if handler:
                return await handler(ctx)
            target = ctx.arg(1) if sub == "bilgi" else ctx.arg(0)
            c = None
            if target:
                user_id = target.strip("<@!>") if target.startswith("<@") else None
                c = self.of(user_id) if user_id else self.find(target)
            elif sub == "bilgi":
                c = self.of(ctx.author.id)
                if c is None:
                    raise CommandError(f"Henüz şirketin yok. Kurmak için ({money(config.COMPANY_COST)}):\n"
                                       '`.şirket kur "Şirket Adı" <malzeme>`\nMalzemeler: '
                                       + ", ".join(f"{e} {lbl}" + (" 💎" if p else "") for lbl, e, _, p in MATERIALS.values()))
            if c is None:
                raise CommandError("Şirket bulunamadı.")
            await ctx.send(embed=self.info_embed(c))

        @cmd("market", category="sirket", usage="[malzeme]", aliases=("magaza", "sirketler", "companies"),
             description="Oyuncu şirketlerinin satışa sunduğu malzemeler.", examples=("market", "market demir"))
        async def market(ctx: Ctx) -> None:
            key = find_material(ctx.arg(0)) if ctx.arg(0) else None
            sql = "SELECT * FROM companies WHERE stock > 0" + (" AND material = ?" if key else "") + " ORDER BY price LIMIT 15"
            rows = self.db.all(sql, (key,) if key else ())
            lines = [f"`{r['ticker']}` **{r['name']}** — {material_label(r['material'])} • {money(r['price'])}/adet • "
                     f"stok {r['stock']}" for r in rows]
            total = self.db.one("SELECT COUNT(*) AS n FROM companies")["n"]
            await ctx.send(embed=embed("🛒 Şirket Pazarı", "\n".join(lines) or "Şu an satışta malzeme yok.")
                           .set_footer(text=f"{total} şirket • Satın al: .satınal <sembol> <adet>"))

        @cmd("satınal", category="sirket", usage="<şirket sembolü> <adet>", aliases=("satinal", "buy", "al"),
             description="Bir şirketten malzeme satın alır.", examples=("satınal DEMR 20",))
        async def buy(ctx: Ctx) -> None:
            c = self.find(ctx.arg(0))
            if c is None:
                raise CommandError("Şirket bulunamadı. Liste için: `.market`")
            if c["owner_id"] == ctx.author.id:
                raise CommandError("Kendi şirketinden alım yapamazsın. Stok zaten senin. 🙂")
            qty = parse_amount(ctx.arg(1), c["stock"])
            if not qty:
                raise CommandError(f"Kaç adet alacağını yaz. Örnek: `.satınal {c['ticker']} 10`")
            total = c["price"] * qty
            income = total - int(total * config.MARKET_FEE)
            with self.db.transaction():
                cur = self.db.execute("UPDATE companies SET stock = stock - ?, vault = vault + ?, sold = sold + ?, "
                                      "revenue = revenue + ? WHERE id = ? AND stock >= ?",
                                      (qty, income, qty, total, c["id"], qty))
                if cur.rowcount != 1:
                    raise CommandError(f"Stokta sadece **{c['stock']}** adet var.")
                if not self.db.take_balance(ctx.author.id, total):
                    raise CommandError(f"Yeterli paran yok. Gereken: **{money(total)}**")
                self.db.add_item(ctx.author.id, c["material"], qty)
            await ctx.send(embed=ok(f"**{c['name']}** şirketinden {material_label(c['material'])} × {qty} aldın: "
                                    f"**-{money(total)}**"))

    def mine(self, ctx: Ctx) -> Any:
        c = self.of(ctx.author.id)
        if c is None:
            raise CommandError('Şirketin yok. Kurmak için: `.şirket kur "Şirket Adı" <malzeme>`')
        return c

    async def create(self, ctx: Ctx) -> None:
        if self.of(ctx.author.id):
            raise CommandError("Zaten bir şirketin var. Bilgi için: `.şirket`")
        if len(ctx.args) < 3:
            raise CommandError('Kullanım: `.şirket kur "Şirket Adı" <malzeme>`\nMalzemeler: '
                               + ", ".join(f"{e} {lbl}" + (" 💎" if p else "") for lbl, e, _, p in MATERIALS.values()))
        key = find_material(ctx.args[-1])
        name = " ".join(ctx.args[1:-1]).strip()
        if key is None:
            raise CommandError("Malzeme bulunamadı. Seçenekler: " + ", ".join(m[0] for m in MATERIALS.values()))
        if MATERIALS[key][3] and not self.bot.is_pro(ctx.author.id):
            raise CommandError(f"{material_label(key)} üretimi sadece **Pro** üyelere açık. 💎 Bilgi: `.pro`")
        if not NAME_RE.match(name):
            raise CommandError("Şirket adı 3-24 karakter olmalı (harf, rakam, boşluk, . & ' -).")
        if self.db.one("SELECT 1 FROM companies WHERE name = ?", (name,)):
            raise CommandError("Bu isimde bir şirket zaten var.")
        ticker = self.make_ticker(name)
        base = MATERIALS[key][2]
        with self.db.transaction():
            if not self.db.take_balance(ctx.author.id, config.COMPANY_COST):
                raise CommandError(f"Şirket kurmak için **{money(config.COMPANY_COST)}** gerekiyor. "
                                   f"Bakiyen: {money(self.db.balance(ctx.author.id))}\n`.çalış` ile para kazanabilirsin!")
            self.db.execute("INSERT INTO companies (owner_id, name, ticker, material, price, vault, created) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)", (ctx.author.id, name, ticker, key, base, 200, time.time()))
            self.db.execute("INSERT INTO stocks (symbol, name, kind, price, base, volatility, updated, history) "
                            "VALUES (?, ?, 'sirket', 100, 100, 0.04, ?, '[100]')", (ticker, name, time.time()))
        await ctx.send(embed=embed("🎉 Şirket Kuruldu!", f"**{name}** (`{ticker}`) artık {material_label(key)} üretiyor.",
                                   Colors.Green).add_fields(
            {"name": "Başlangıç kasası", "value": money(200), "inline": True},
            {"name": "Hisse", "value": f"Borsada `{ticker}` olarak işlem görüyor", "inline": True},
            {"name": "Sıradaki adımlar", "value": "`.şirket üret` → `.şirket fiyat <fiyat>` → oyuncular `.satınal` ile alır\n"
                                                  "veya `.şirket sat <adet>` ile stoğu pazara sat"}))

    async def produce(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        cooldown = self.produce_cooldown(ctx.author.id)
        remaining = c["last_produce"] + cooldown - time.time()
        if remaining > 0:
            raise CommandError(f"Fabrika çalışıyor ⚙️ Sonraki üretim: **{fmt_duration(remaining)}** sonra.")
        pro = self.bot.is_pro(ctx.author.id)
        units = int(random.randint(8, 15) * c["level"] * (config.PRO_PRODUCE_BONUS if pro else 1))
        unit_cost = max(1, int(MATERIALS[c["material"]][2] * PRODUCTION_COST))
        affordable = c["vault"] // unit_cost
        units = min(units, affordable)
        if units <= 0:
            raise CommandError(f"Kasada üretim için yeterli para yok (birim maliyet {money(unit_cost)}).\n"
                               f"Kasaya para koy: `.şirket yatır <miktar>`")
        cost = units * unit_cost
        self.db.execute("UPDATE companies SET stock = stock + ?, vault = vault - ?, last_produce = ? WHERE id = ?",
                        (units, cost, time.time(), c["id"]))
        await ctx.send(embed=ok(f"🏭 {material_label(c['material'])} × **{units}** üretildi (maliyet {money(cost)}).\n"
                                f"Stok: {c['stock'] + units} • Kasa: {money(c['vault'] - cost)}"
                                + ("\n💎 Pro üretim bonusu uygulandı." if pro else "")))

    async def set_price(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        base = MATERIALS[c["material"]][2]
        low, high = int(base * PRICE_MIN), int(base * PRICE_MAX)
        price = parse_amount(ctx.arg(1))
        if not price or not low <= price <= high:
            raise CommandError(f"Fiyat {money(low)} ile {money(high)} arasında olmalı. "
                               f"Pazar fiyatı: {money(self.economy.commodity_price(c['material']))}")
        self.db.execute("UPDATE companies SET price = ? WHERE id = ?", (price, c["id"]))
        await ctx.send(embed=ok(f"{material_label(c['material'])} satış fiyatı: **{money(price)}**"))

    async def deposit(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        amount = parse_amount(ctx.arg(1), self.db.balance(ctx.author.id))
        if not amount:
            raise CommandError("Kullanım: `.şirket yatır <miktar|hepsi>`")
        with self.db.transaction():
            if not self.db.take_balance(ctx.author.id, amount):
                raise CommandError("Yeterli paran yok.")
            self.db.execute("UPDATE companies SET vault = vault + ? WHERE id = ?", (amount, c["id"]))
        await ctx.send(embed=ok(f"Kasaya **{money(amount)}** yatırıldı. Kasa: {money(c['vault'] + amount)}"))

    async def withdraw(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        amount = parse_amount(ctx.arg(1), c["vault"])
        if not amount:
            raise CommandError("Kullanım: `.şirket çek <miktar|hepsi>`")
        with self.db.transaction():
            cur = self.db.execute("UPDATE companies SET vault = vault - ? WHERE id = ? AND vault >= ?",
                                  (amount, c["id"], amount))
            if cur.rowcount != 1:
                raise CommandError(f"Kasada sadece **{money(c['vault'])}** var.")
            self.db.add_balance(ctx.author.id, amount)
        await ctx.send(embed=ok(f"Kasadan **{money(amount)}** çekildi."))

    async def dump(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        qty = parse_amount(ctx.arg(1), c["stock"])
        if not qty:
            raise CommandError("Kullanım: `.şirket sat <adet|hepsi>`")
        price = self.economy.commodity_price(c["material"]) * COMPANY_DUMP_RATE
        total = int(price * qty)
        cur = self.db.execute("UPDATE companies SET stock = stock - ?, vault = vault + ?, sold = sold + ?, revenue = revenue + ? "
                              "WHERE id = ? AND stock >= ?", (qty, total, qty, total, c["id"], qty))
        if cur.rowcount != 1:
            raise CommandError(f"Stokta sadece **{c['stock']}** adet var.")
        await ctx.send(embed=ok(f"{material_label(c['material'])} × {qty} toptan pazara satıldı: kasaya **+{money(total)}** "
                                f"(pazar fiyatının %{int(COMPANY_DUMP_RATE * 100)}'i)"))

    async def upgrade(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        if c["level"] >= MAX_LEVEL:
            raise CommandError("Şirketin zaten en yüksek seviyede! 🏆")
        need = upgrade_cost(c["level"])
        inventory = self.db.inventory(ctx.author.id)
        missing = []
        if c["vault"] < need["money"]:
            missing.append(f"Kasa: {money(c['vault'])} / {money(need['money'])}")
        for key in ("odun", "tas", "demir"):
            if inventory.get(key, 0) < need[key]:
                missing.append(f"{material_label(key)}: {inventory.get(key, 0)} / {need[key]}")
        if missing:
            raise CommandError(f"Seviye {c['level'] + 1} için eksikler:\n" + "\n".join(f"• {m}" for m in missing)
                               + "\n\nMalzemeleri `.market` üzerinden diğer şirketlerden alabilirsin.")
        with self.db.transaction():
            for key in ("odun", "tas", "demir"):
                if not self.db.take_item(ctx.author.id, key, need[key]):
                    raise CommandError("Malzemeler yetersiz.")
            self.db.execute("UPDATE companies SET level = level + 1, vault = vault - ? WHERE id = ?", (need["money"], c["id"]))
        await ctx.send(embed=ok(f"🏗️ **{c['name']}** seviye **{c['level'] + 1}** oldu! Üretim kapasitesi arttı."))

    async def close(self, ctx: Ctx) -> None:
        c = self.mine(ctx)
        buttons = ActionRowBuilder().add_components(
            ButtonBuilder().set_custom_id(f"co:close:{ctx.author.id}:yes").set_label("Evet, kapat").set_style(ButtonStyle.Danger),
            ButtonBuilder().set_custom_id(f"co:close:{ctx.author.id}:no").set_label("Vazgeç").set_style(ButtonStyle.Secondary))
        await ctx.send(embed=embed("⚠️ Şirketi Kapat", f"**{c['name']}** kalıcı olarak kapatılacak. Kasadaki para cüzdanına "
                                                       "aktarılır, stok ve kuruluş ücreti geri gelmez. Emin misin?",
                                   Colors.Orange), components=[buttons])


def setup(bot: Bot) -> Company:
    return Company(bot)
