from __future__ import annotations

import time

from jubbiopy import ActionRowBuilder, ButtonBuilder, ButtonStyle, Colors

from .. import config
from ..core import CommandError, Ctx, Bot
from ..utils import embed, fmt_duration, fold, money, ok, parse_duration, parse_id

PERMANENT = {"kalici", "sinirsiz", "suresiz", "omurboyu", "perm", "permanent", "sonsuz"}

FEATURES = [
    ("💼", "Çalışma bonusu", f"`.çalış` ile **×{config.PRO_WORK_MULTIPLIER:g}** kazanç ve **12 saatte bir** çalışma"),
    ("💸", "Kesintisiz transfer", "`.gönder` ile para gönderirken kesinti yok"),
    ("📈", "Komisyonsuz borsa", "Hisse alım-satımlarında komisyon yok"),
    ("🏭", "Hızlı fabrika", f"Şirket üretimi **30 dakikada bir** ve **+%{int((config.PRO_PRODUCE_BONUS - 1) * 100)}** fazla"),
    ("💎", "Özel malzemeler", "Şirketinle **Elektronik** ve **Elmas** üretebilme"),
    ("🎮", "Yüksek bahis", f"`.tkm` bahis sınırı **{money(config.PRO_TKM_MAX_BET)}**"),
    ("✨", "Pro rozeti", "Profilde, sıralamada ve şirketinde 💎 rozeti"),
]


class Pro:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.register()

    def register(self) -> None:
        cmd = self.bot.command

        @cmd("pro", category="pro", usage="[@kullanıcı]", aliases=("premium", "vip"),
             description="Pro özelliklerini ve Pro durumunu gösterir.", guild_only=False)
        async def pro(ctx: Ctx) -> None:
            user = await self.bot.resolve_user(ctx, ctx.arg(0), default_self=True)
            active, until = self.db.pro_until(user.id)
            if self.bot.is_owner(user.id):
                status = "👑 Bot sahibi — tüm Pro özellikleri açık"
            elif active:
                status = "💎 **Pro aktif** — " + ("kalıcı" if until is None else f"bitiş <t:{int(until)}:F> (<t:{int(until)}:R>)")
            elif until:
                status = f"Pro süresi <t:{int(until)}:R> doldu."
            else:
                status = "Pro değil."
            e = embed(f"💎 {config.BOT_NAME} Pro", status).add_fields(
                *[{"name": f"{emoji} {name}", "value": text, "inline": True} for emoji, name, text in FEATURES])
            if config.LOGO_URL:
                e.set_thumbnail(config.LOGO_URL)
            components = None
            if not active and not self.bot.is_owner(user.id) and config.SUPPORT_INVITE:
                e.set_footer(text="Pro almak için destek sunucumuza katıl.")
                components = [ActionRowBuilder().add_components(
                    ButtonBuilder().set_label("Destek Sunucusu").set_emoji("💬").set_style(ButtonStyle.Link)
                    .set_url(config.SUPPORT_INVITE))]
            await ctx.send(embed=e, components=components)

        @cmd("proekle", category="pro", usage="<ID|@kullanıcı> <süre|kalıcı>", aliases=("addpro", "prover"),
             description="Kullanıcıya Pro ekler (sadece bot sahibi). Süre varsa mevcut süreye eklenir.",
             owner_only=True, guild_only=False, examples=("proekle 123 30g", "proekle @ali 1ay", "proekle 123 kalıcı"))
        async def add_pro(ctx: Ctx) -> None:
            user_id = parse_id(ctx.arg(0))
            if not user_id:
                raise CommandError(f"Kullanım: {ctx.usage()}\nSüre örnekleri: `7g`, `12sa`, `1ay`, `1y`, `kalıcı`")
            text = ctx.arg(1, "")
            if fold(text) in PERMANENT:
                until = None
            else:
                seconds = parse_duration(text)
                if not seconds:
                    raise CommandError("Geçerli bir süre yaz: `7g`, `12sa`, `1ay`, `1y` veya `kalıcı`")
                active, current = self.db.pro_until(user_id)
                if active and current is None:
                    raise CommandError("Bu kullanıcının zaten **kalıcı** Pro'su var.")
                start = current if active and current else time.time()
                until = start + seconds
            self.db.execute("INSERT INTO pro (user_id, until, added_by, added) VALUES (?, ?, ?, ?) "
                            "ON CONFLICT(user_id) DO UPDATE SET until = excluded.until, added_by = excluded.added_by, "
                            "added = excluded.added", (user_id, until, ctx.author.id, time.time()))
            when = "**kalıcı**" if until is None else f"<t:{int(until)}:F> tarihine kadar ({fmt_duration(until - time.time())})"
            await ctx.send(embed=ok(f"<@{user_id}> (`{user_id}`) artık 💎 **Pro** — {when}."))
            try:
                await self.bot.rest.create_dm_message(user_id, {"embeds": [
                    embed(f"💎 {config.BOT_NAME} Pro'ya hoş geldin!", f"Pro üyeliğin {when} aktif. Özellikler için `.pro` yaz.", Colors.Gold)]})
            except Exception:
                pass

        @cmd("prosil", category="pro", usage="<ID|@kullanıcı>", aliases=("removepro", "proal"),
             description="Kullanıcının Pro'sunu kaldırır (sadece bot sahibi).", owner_only=True, guild_only=False)
        async def remove_pro(ctx: Ctx) -> None:
            user_id = parse_id(ctx.arg(0))
            if not user_id:
                raise CommandError(f"Kullanım: {ctx.usage()}")
            cur = self.db.execute("DELETE FROM pro WHERE user_id = ?", (user_id,))
            if not cur.rowcount:
                raise CommandError("Bu kullanıcının Pro'su yok.")
            await ctx.send(embed=ok(f"<@{user_id}> kullanıcısının Pro üyeliği kaldırıldı."))

        @cmd("proliste", category="pro", aliases=("prolist", "prolar"),
             description="Pro üyeleri listeler (sadece bot sahibi).", owner_only=True, guild_only=False)
        async def list_pro(ctx: Ctx) -> None:
            rows = self.db.all("SELECT * FROM pro WHERE until IS NULL OR until > ? ORDER BY until IS NULL DESC, until",
                               (time.time(),))
            lines = [f"<@{r['user_id']}> (`{r['user_id']}`) — " + ("kalıcı" if r["until"] is None else f"<t:{int(r['until'])}:R>")
                     for r in rows[:40]]
            await ctx.send(embed=embed(f"💎 Pro Üyeler ({len(rows)})", "\n".join(lines) or "Henüz Pro üye yok."))


def setup(bot: Bot) -> Pro:
    return Pro(bot)
