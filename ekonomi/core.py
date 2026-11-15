from __future__ import annotations

import asyncio
import logging
import re
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any, Awaitable, Callable, Dict, List, Optional, Tuple

from jubbiopy import Client, EmbedBuilder, GatewayIntentBits, HTTPException, SlashCommandBuilder, User

from . import config
from .db import Database
from .utils import err, fold, ok, parse_id, split_args

log = logging.getLogger("ekonomi")

CATEGORIES = {
    "genel": ("📌", "Genel"),
    "ekonomi": ("🪙", "Ekonomi"),
    "sirket": ("🏢", "Şirket ve Pazar"),
    "borsa": ("📈", "Borsa"),
    "oyun": ("🎮", "Oyunlar"),
    "pro": ("💎", "Pro"),
}


def slash_name(name: str) -> str:
    return re.sub(r"[^a-z0-9_-]", "", fold(name))[:32]


class CommandError(Exception):
    pass


@dataclass
class Command:
    name: str
    func: Callable[..., Awaitable[Any]]
    category: str
    usage: str = ""
    description: str = ""
    aliases: Tuple[str, ...] = ()
    owner_only: bool = False
    guild_only: bool = True
    cooldown: float = 0.0
    examples: Tuple[str, ...] = ()
    _last_used: Dict[str, float] = field(default_factory=dict, repr=False)


class Ctx:
    def __init__(self, bot: "Bot", message: Any, command: Command, invoked: str, args: List[str], raw: str,
                 interaction: Any = None) -> None:
        self.bot = bot
        self.message = message
        self.interaction = interaction
        self.responded = False
        self.command = command
        self.invoked = invoked
        self.args = args
        self.raw = raw
        self.guild_id: Optional[str] = message.guild_id
        self.channel_id: str = message.channel_id
        self.author = message.author
        self.member = message.member

    @property
    def db(self) -> Database:
        return self.bot.db

    @property
    def prefix(self) -> str:
        return config.PREFIX

    def arg(self, index: int, default: Optional[str] = None) -> Optional[str]:
        return self.args[index] if len(self.args) > index else default

    def rest_text(self, start: int) -> str:
        return " ".join(self.args[start:])

    async def send(self, content: Optional[str] = None, *, embed: Optional[EmbedBuilder] = None,
                   embeds: Optional[List[Any]] = None, components: Optional[List[Any]] = None) -> Dict[str, Any]:
        payload: Dict[str, Any] = {}
        if content:
            payload["content"] = content
        if embed is not None:
            embeds = [embed]
        if embeds:
            payload["embeds"] = embeds
        if components:
            payload["components"] = components
        if self.interaction is not None:
            if not self.responded:
                self.responded = True
                await self.interaction.edit_reply(**payload)
                return {}
            return await self.bot.send(self.guild_id, self.channel_id, payload) or {}
        payload["message_reference"] = {"message_id": self.message.id}
        return await self.bot.send(self.guild_id, self.channel_id, payload) or {}

    async def error(self, text: str) -> Dict[str, Any]:
        return await self.send(embed=err(text))

    def usage(self) -> str:
        return f"`{self.prefix}{self.command.name} {self.command.usage}`".replace(" `", "`")


Handler = Callable[[Any], Awaitable[Any]]


class Bot:
    SLASH_ECHO_WINDOW = 3.0
    SLASH_ECHO_WAIT = 1.5

    def __init__(self, db: Database, **client_options: Any) -> None:
        self.db = db
        self.client = Client(intents=[
            GatewayIntentBits.Guilds, GatewayIntentBits.GuildMessages, GatewayIntentBits.MessageContent,
        ], **client_options)
        self.commands: Dict[str, Command] = {}
        self.command_list: List[Command] = []
        self.components: List[Tuple[str, Handler]] = []
        self.ready_hooks: List[Callable[[], Any]] = []
        self.modules: Dict[str, Any] = {}
        self.started_at = time.time()
        self._tasks: set = set()
        self._ready_once = False
        self._seen_ids: "OrderedDict[str, None]" = OrderedDict()
        self._slash_calls: Dict[Tuple[str, str, str], float] = {}

        self.ready_hooks.append(self.register_slash)
        self.client.on("ready", self._on_ready)
        self.client.on("messageCreate", self._on_message)
        self.client.on("interactionCreate", self._on_interaction)

    def command(self, name: str, *, category: str, usage: str = "", description: str = "",
                aliases: Tuple[str, ...] = (), owner_only: bool = False, guild_only: bool = True,
                cooldown: float = 0.0, examples: Tuple[str, ...] = ()):
        def decorator(func):
            cmd = Command(name, func, category, usage, description, tuple(aliases), owner_only, guild_only,
                          cooldown, tuple(examples))
            self.command_list.append(cmd)
            for key in (name, *aliases):
                folded = fold(key)
                if folded in self.commands and self.commands[folded] is not cmd:
                    raise ValueError(f"Komut adı çakışıyor: {key}")
                self.commands[folded] = cmd
            return func
        return decorator

    def component(self, prefix: str):
        def decorator(func):
            self.components.append((prefix, func))
            return func
        return decorator

    def spawn(self, coro) -> asyncio.Task:
        task = asyncio.get_running_loop().create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def every(self, seconds: float, func: Callable[[], Awaitable[Any]]) -> None:
        async def loop() -> None:
            while True:
                try:
                    await func()
                except Exception:
                    log.exception("Zamanlanmış görev hatası")
                await asyncio.sleep(seconds)

        self.ready_hooks.append(lambda: self.spawn(loop()))

    @property
    def rest(self):
        return self.client.rest

    def is_owner(self, user_id: str) -> bool:
        return bool(config.OWNER_ID) and str(user_id) == str(config.OWNER_ID)

    def is_pro(self, user_id: str) -> bool:
        return self.is_owner(user_id) or self.db.pro_until(str(user_id))[0]

    async def send(self, guild_id: Optional[str], channel_id: str, payload: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        try:
            return await self.rest.create_message(guild_id or "", channel_id, payload)
        except HTTPException as exc:
            log.warning("Mesaj gönderilemedi (%s): %s", channel_id, exc)
            return None

    async def _on_ready(self, _client: Any) -> None:
        if not self._ready_once:
            self._ready_once = True
            for hook in self.ready_hooks:
                result = hook()
                if asyncio.iscoroutine(result):
                    await result
        user = self.client.user
        log.info("%s hazır! %d sunucu, %d komut", user.username if user else config.BOT_NAME,
                 len(self.client.guilds), len(self.command_list))

    def first_time(self, event_id: str) -> bool:
        if event_id in self._seen_ids:
            return False
        self._seen_ids[event_id] = None
        while len(self._seen_ids) > 2000:
            self._seen_ids.popitem(last=False)
        return True

    def mark_slash(self, user_id: str, channel_id: str, command: str) -> None:
        now = time.monotonic()
        if len(self._slash_calls) > 500:
            self._slash_calls = {k: t for k, t in self._slash_calls.items() if now - t < self.SLASH_ECHO_WINDOW}
        self._slash_calls[(str(user_id), str(channel_id), command)] = now

    def slash_seen(self, user_id: str, channel_id: str, command: str) -> bool:
        last = self._slash_calls.get((str(user_id), str(channel_id), command))
        return last is not None and time.monotonic() - last < self.SLASH_ECHO_WINDOW

    async def _on_message(self, message: Any) -> None:
        if message.author.bot or not self.first_time(f"m{message.id}") or getattr(message, "application_id", None):
            return
        content = message.content.strip()
        prefix = next((p for p in config.PREFIXES if content.startswith(p) and len(content) > len(p)), None)
        if prefix is None:
            return
        invoked, _, raw = content[len(prefix):].partition(" ")
        command = self.commands.get(fold(invoked.strip()))
        if command is None:
            return
        if prefix == "/":
            if not self.slash_seen(message.author.id, message.channel_id, command.name):
                await asyncio.sleep(self.SLASH_ECHO_WAIT)
            if self.slash_seen(message.author.id, message.channel_id, command.name):
                return
        await self.invoke(command, message, invoked.strip(), raw.strip())

    async def invoke(self, command: Command, message: Any, invoked: str, raw: str, interaction: Any = None) -> None:
        ctx = Ctx(self, message, command, invoked, split_args(raw), raw, interaction)
        try:
            if command.guild_only and not ctx.guild_id:
                raise CommandError("Bu komut sadece sunucularda kullanılabilir.")
            if command.owner_only and not self.is_owner(ctx.author.id):
                raise CommandError("Bu komutu sadece bot sahibi kullanabilir.")
            if command.cooldown:
                wait = command.cooldown - (time.monotonic() - command._last_used.get(ctx.author.id, 0))
                if wait > 0:
                    raise CommandError(f"Biraz yavaş! **{wait:.0f} sn** sonra tekrar dene.")
                command._last_used[ctx.author.id] = time.monotonic()
            await command.func(ctx)
        except CommandError as exc:
            await ctx.error(str(exc))
        except HTTPException as exc:
            log.warning("Komut API hatası (%s): %s", command.name, exc)
            await ctx.error("Bunun için yetkim yok." if exc.status == 403 else f"API hatası ({exc.status}).")
        except Exception as exc:
            log.exception("Komut hatası: %s", command.name)
            await ctx.error(f"Beklenmeyen bir hata oluştu: `{type(exc).__name__}`")
        finally:
            if interaction is not None and not ctx.responded:
                try:
                    await interaction.edit_reply(embeds=[ok("Tamamlandı.")])
                except HTTPException:
                    pass

    async def _on_interaction(self, interaction: Any) -> None:
        if interaction.is_command():
            return await self._on_slash(interaction)
        custom_id = getattr(interaction, "custom_id", "") or ""
        if not custom_id or not self.first_time(f"i{interaction.id}"):
            return
        for prefix, handler in self.components:
            if custom_id.startswith(prefix):
                try:
                    await handler(interaction)
                except CommandError as exc:
                    await self.respond(interaction, embeds=[err(str(exc))], ephemeral=True)
                except HTTPException as exc:
                    log.warning("Etkileşim API hatası: %s", exc)
                    await self.respond(interaction, embeds=[err(f"İşlem yapılamadı (API {exc.status}).")], ephemeral=True)
                except Exception:
                    log.exception("Etkileşim hatası: %s", custom_id)
                    await self.respond(interaction, embeds=[err("Bir hata oluştu.")], ephemeral=True)
                return

    def slash_commands(self) -> List[SlashCommandBuilder]:
        builders = []
        for cmd in self.command_list:
            builder = SlashCommandBuilder().set_name(slash_name(cmd.name)).set_description((cmd.description or cmd.name)[:100])
            usage = cmd.usage
            if usage and "@kullanıcı" in usage.split(" ")[0]:
                builder.add_user_option(lambda o: o.set_name("kullanici").set_description("Kullanıcı"))
                usage = usage.split(" ", 1)[1] if " " in usage else ""
            if usage:
                builder.add_string_option(lambda o, u=usage: o.set_name("argumanlar")
                                          .set_description(f"Örn: {u}"[:100]).set_max_length(1000))
            builders.append(builder)
        return builders

    async def register_slash(self) -> None:
        try:
            commands = self.slash_commands()
            await self.client.application.commands.set(commands)
            log.info("%d slash komut kaydedildi", len(commands))
        except HTTPException as exc:
            log.warning("Slash komutlar kaydedilemedi: %s", exc)

    async def _on_slash(self, interaction: Any) -> None:
        command = self.commands.get(fold(interaction.command_name or ""))
        if command is None or not self.first_time(f"i{interaction.id}"):
            return
        user = interaction.options.get_user_id("kullanici")
        text = interaction.options.get_string("argumanlar") or ""
        raw = " ".join(p for p in (f"<@{user}>" if user else "", text) if p)
        self.mark_slash(interaction.user.id, interaction.channel_id, command.name)
        try:
            await interaction.defer_reply()
        except HTTPException as exc:
            log.warning("Slash komut ertelenemedi: %s", exc)
            return
        message = SimpleNamespace(id=interaction.id, guild_id=interaction.guild_id, channel_id=interaction.channel_id,
                                  author=interaction.user, member=interaction.member, content=f"/{command.name} {raw}")
        await self.invoke(command, message, interaction.command_name, raw, interaction)

    @staticmethod
    async def respond(interaction: Any, content: Optional[str] = None, **kwargs: Any) -> None:
        try:
            if interaction.deferred:
                kwargs.pop("ephemeral", None)
                await interaction.edit_reply(content, **kwargs)
            elif interaction.replied:
                await interaction.follow_up(content, **kwargs)
            else:
                await interaction.reply(content, **kwargs)
        except HTTPException as exc:
            log.warning("Etkileşime yanıt verilemedi: %s", exc)

    async def resolve_user(self, ctx: Ctx, value: Optional[str], default_self: bool = False) -> Optional[Any]:
        user_id = parse_id(value) if value else (ctx.author.id if default_self else None)
        if not user_id:
            return None
        if user_id == ctx.author.id:
            return ctx.author
        cached = self.client.users.get(user_id)
        if cached is not None:
            return cached
        try:
            return await self.client.fetch_user(user_id)
        except Exception:
            return User({"id": user_id, "username": f"Kullanıcı {user_id}"}, self.client)
