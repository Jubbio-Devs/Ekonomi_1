from __future__ import annotations

import random

from jubbiopy import Colors

from .. import config
from ..core import CommandError, Ctx, Bot
from ..utils import embed, fold, money, parse_amount

CHOICES = {"tas": ("Taş", "🪨"), "kagit": ("Kağıt", "📄"), "makas": ("Makas", "✂️")}
ALIASES = {"t": "tas", "rock": "tas", "🪨": "tas", "✊": "tas", "k": "kagit", "paper": "kagit", "📄": "kagit",
           "✋": "kagit", "m": "makas", "scissors": "makas", "✂️": "makas", "✌️": "makas"}
BEATS = {"tas": "makas", "kagit": "tas", "makas": "kagit"}


def parse_choice(text: str) -> str:
    key = fold(text or "")
    return key if key in CHOICES else ALIASES.get(key, ALIASES.get(text or "", ""))


class Games:
    def __init__(self, bot: Bot) -> None:
        self.bot = bot
        self.db = bot.db
        self.register()

    def register(self) -> None:
        @self.bot.command("tkm", category="oyun", usage="<taş|kağıt|makas> [bahis]", aliases=("taskagitmakas", "rps"),
                          description="Bota karşı taş-kağıt-makas. Bahis koyarsan kazanınca bahsin kadar kazanırsın.",
                          cooldown=config.TKM_COOLDOWN, examples=("tkm makas", "tkm taş 100", "tkm kağıt hepsi"))
        async def tkm(ctx: Ctx) -> None:
            choice = parse_choice(ctx.arg(0, ""))
            if not choice:
                raise CommandError("Seçimini yaz: `.tkm taş`, `.tkm kağıt` veya `.tkm makas` (bahis için sonuna miktar ekle)")
            pro = self.bot.is_pro(ctx.author.id)
            limit = config.PRO_TKM_MAX_BET if pro else config.TKM_MAX_BET
            bet = 0
            if ctx.arg(1):
                bet = parse_amount(ctx.arg(1), min(self.db.balance(ctx.author.id), limit)) or 0
                if bet <= 0:
                    raise CommandError("Geçerli bir bahis yaz. Örnek: `.tkm taş 100`")
                if bet > limit:
                    raise CommandError(f"En fazla **{money(limit)}** bahis yapabilirsin"
                                       + ("" if pro else f" (Pro: {money(config.PRO_TKM_MAX_BET)})") + ".")
                if self.db.balance(ctx.author.id) < bet:
                    raise CommandError(f"Yeterli paran yok. Bakiye: **{money(self.db.balance(ctx.author.id))}**")
            bot_choice = random.choice(list(CHOICES))
            if choice == bot_choice:
                result, color, delta = "🤝 **Berabere!**", Colors.Grey, 0
            elif BEATS[choice] == bot_choice:
                result, color, delta = "🎉 **Kazandın!**", Colors.Green, bet
                self.db.execute("UPDATE users SET tkm_win = tkm_win + 1 WHERE user_id = ?", (self.db.user(ctx.author.id)["user_id"],))
            else:
                result, color, delta = "😢 **Kaybettin!**", Colors.Red, -bet
                self.db.execute("UPDATE users SET tkm_loss = tkm_loss + 1 WHERE user_id = ?", (self.db.user(ctx.author.id)["user_id"],))
            if delta > 0:
                self.db.add_balance(ctx.author.id, delta)
            elif delta < 0 and not self.db.take_balance(ctx.author.id, -delta):
                raise CommandError("Bakiyen bu arada değişti, bahis iptal edildi.")
            you, me = CHOICES[choice], CHOICES[bot_choice]
            text = f"Sen: {you[1]} **{you[0]}**\n{config.BOT_NAME}: {me[1]} **{me[0]}**\n\n{result}"
            if bet:
                text += f"\n{'+' if delta > 0 else '-' if delta < 0 else '±'}{money(abs(delta) if delta else bet)}" \
                        + (" (bahsin iade edildi)" if not delta else "")
                text += f"\nBakiye: **{money(self.db.balance(ctx.author.id))}**"
            await ctx.send(embed=embed("✊ Taş Kağıt Makas", text, color))


def setup(bot: Bot) -> Games:
    return Games(bot)
