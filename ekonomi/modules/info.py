from __future__ import annotations

import time
from typing import Any, List, Optional

from jubbiopy import ActionRowBuilder, ButtonBuilder, ButtonStyle, StringSelectMenuBuilder

from .. import config
from ..core import CATEGORIES, Bot, Command, CommandError, Ctx
from ..utils import embed, fmt_duration, fold, money


class Info:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        bot.component("help:")(self.on_component)
        self.register()

    def visible(self, category: Optional[str] = None) -> List[Command]:
        return [c for c in self.bot.command_list if category is None or c.category == category]

    def menu(self, selected: Optional[str] = None) -> ActionRowBuilder:
        options = [{"label": "Ana Sayfa", "value": "home", "emoji": {"name": "🏠"}, "default": selected is None}]
        for key, (emoji, label) in CATEGORIES.items():
            count = len(self.visible(key))
            if count:
                options.append({"label": label, "value": key, "description": f"{count} komut",
                                "emoji": {"name": emoji}, "default": key == selected})
        return ActionRowBuilder().add_components(
            StringSelectMenuBuilder().set_custom_id("help:cat").set_placeholder("📂 Kategori seç...").add_options(*options))

    def components(self, selected: Optional[str] = None) -> List[ActionRowBuilder]:
        rows = [self.menu(selected)]
        if config.SUPPORT_INVITE:
            rows.append(ActionRowBuilder().add_components(
                ButtonBuilder().set_label("Destek Sunucusu").set_emoji("💬").set_style(ButtonStyle.Link)
                .set_url(config.SUPPORT_INVITE)))
        return rows

    def home_embed(self):
        p = config.PREFIX
        lines = [f"{emoji} **{label}** — `{p}yardım {key}`" for key, (emoji, label) in CATEGORIES.items() if self.visible(key)]
        e = (embed(f"📖 {config.BOT_NAME} Yardım Menüsü",
                   f"Çalış, **{config.CURRENCY}** kazan, şirket kur, malzeme üret ve sat, borsada yatırım yap!\n\n"
                   f"Ön ek: `{p}` veya `/` • Kategori seçmek için aşağıdaki menüyü kullan.\n"
                   f"Bir komutun ayrıntısı: `{p}yardım <komut>`\n\n" + "\n".join(lines))
             .set_footer(text=f"{config.BOT_NAME} v{config.VERSION}"))
        if config.LOGO_URL:
            e.set_thumbnail(config.LOGO_URL)
        return e

    def category_embed(self, key: str):
        emoji, label = CATEGORIES[key]
        p = config.PREFIX
        lines = [f"`{p}{c.name}{' ' + c.usage if c.usage else ''}`\n└ {c.description}" for c in self.visible(key)]
        return embed(f"{emoji} {label}", "\n".join(lines)[:4000]).set_footer(text=f"Ayrıntı için: {p}yardım <komut>")

    def command_embed(self, c: Command):
        p = config.PREFIX
        e = embed(f"📘 {p}{c.name}", c.description).add_fields(
            {"name": "Kullanım", "value": f"`{p}{c.name}{' ' + c.usage if c.usage else ''}`"})
        if c.aliases:
            e.add_fields({"name": "Diğer adlar", "value": ", ".join(f"`{p}{a}`" for a in c.aliases)})
        if c.examples:
            e.add_fields({"name": "Örnekler", "value": "\n".join(f"`{p}{x}`" for x in c.examples)})
        if c.owner_only:
            e.set_footer(text="Sadece bot sahibi kullanabilir.")
        return e

    async def on_component(self, interaction: Any) -> None:
        if interaction.custom_id != "help:cat":
            return
        value = interaction.values[0] if interaction.values else "home"
        if value in CATEGORIES:
            await interaction.update(embeds=[self.category_embed(value)], components=self.components(value))
        else:
            await interaction.update(embeds=[self.home_embed()], components=self.components())

    def register(self) -> None:
        cmd = self.bot.command

        @cmd("yardım", category="genel", usage="[kategori | komut]", aliases=("yardim", "help", "h", "komutlar"),
             description="Yardım menüsü.", guild_only=False)
        async def help_cmd(ctx: Ctx) -> None:
            query = fold(ctx.arg(0, ""))
            if query:
                if query in CATEGORIES:
                    return await ctx.send(embed=self.category_embed(query), components=self.components(query))
                for key, (_, label) in CATEGORIES.items():
                    if query == fold(label.split()[0]):
                        return await ctx.send(embed=self.category_embed(key), components=self.components(key))
                command = self.bot.commands.get(query.lstrip(config.PREFIX))
                if command is None:
                    raise CommandError(f"`{ctx.arg(0)}` diye bir komut veya kategori yok.")
                return await ctx.send(embed=self.command_embed(command))
            await ctx.send(embed=self.home_embed(), components=self.components())

        @cmd("ping", category="genel", aliases=("gecikme",), description="Botun gecikmesi.", guild_only=False)
        async def ping(ctx: Ctx) -> None:
            start = time.perf_counter()
            await self.bot.rest.get_current_user()
            rest_ms = (time.perf_counter() - start) * 1000
            await ctx.send(embed=embed(description=f"🏓 **Pong!**\nGateway: `{self.bot.client.ping:.0f} ms` • "
                                                   f"API: `{rest_ms:.0f} ms`"))

        @cmd("istatistik", category="genel", aliases=("botbilgi", "stats", "bilgi"),
             description="Bot istatistikleri.", guild_only=False)
        async def stats(ctx: Ctx) -> None:
            db = self.bot.db
            users = db.one("SELECT COUNT(*) AS n, COALESCE(SUM(balance), 0) AS total FROM users")
            companies = db.one("SELECT COUNT(*) AS n FROM companies")["n"]
            await ctx.send(embed=embed(f"📊 {config.BOT_NAME} İstatistikleri").add_fields(
                {"name": "Sunucu", "value": str(len(self.bot.client.guilds)), "inline": True},
                {"name": "Komut", "value": str(len(self.visible())), "inline": True},
                {"name": "Çalışma süresi", "value": fmt_duration(time.time() - self.bot.started_at), "inline": True},
                {"name": "Oyuncu", "value": str(users["n"]), "inline": True},
                {"name": "Dolaşımdaki para", "value": money(users["total"]), "inline": True},
                {"name": "Şirket", "value": str(companies), "inline": True}))

        if config.SUPPORT_INVITE:
            @cmd("destek", category="genel", aliases=("davet", "support", "invite"),
                 description="Destek sunucusunun davet bağlantısı.", guild_only=False)
            async def support(ctx: Ctx) -> None:
                await ctx.send(embed=embed("💬 Destek Sunucusu", config.SUPPORT_INVITE), components=self.components())


def setup(bot: Bot) -> Info:
    return Info(bot)
