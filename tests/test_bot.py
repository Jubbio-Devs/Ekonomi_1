from __future__ import annotations

import asyncio
import itertools
import time

import pytest

from ekonomi import config, create_bot

from .conftest import APP_ID, until

OWNER = {"user": {"id": "100", "username": "sahip"}, "roles": [], "joined_at": "2025-01-01T00:00:00Z"}
USER = {"user": {"id": "7", "username": "ali"}, "roles": [], "joined_at": "2025-01-01T00:00:00Z"}
USER2 = {"user": {"id": "8", "username": "veli"}, "roles": ["900"], "joined_at": "2025-01-01T00:00:00Z"}

ids = itertools.count(1000)


@pytest.fixture
async def bot(server, tmp_path, monkeypatch):
    monkeypatch.setattr(config, "OWNER_ID", "100")
    instance = create_bot(str(tmp_path / "ekonomi.db"), gateway_url=server.gateway_url, api_url=server.api_url,
                          ready_timeout=5)
    await instance.client.login("t")
    yield instance
    await instance.client.destroy()
    instance.db.close()


def make_say(server):
    async def say(member, content, channel="300"):
        message_id = str(next(ids))
        await server.dispatch("MESSAGE_CREATE", {
            "id": message_id, "channel_id": channel, "guild_id": "200", "content": content,
            "author": member["user"], "member": {k: v for k, v in member.items() if k != "user"},
            "timestamp": "2026-01-01T00:00:00Z"})

        def reply():
            return [r["json"] for r in server.find("POST", f"/channels/{channel}/messages")
                    if (r.get("json") or {}).get("message_reference", {}).get("message_id") == message_id]
        await until(lambda: reply(), timeout=5)
        return reply()[-1]
    return say


def text(body) -> str:
    e = (body.get("embeds") or [{}])[0]
    parts = [e.get("title") or "", e.get("description") or ""]
    parts += [f"{f.get('name')}: {f.get('value')}" for f in e.get("fields") or []]
    return "\n".join(parts)


def interaction(i, member, channel="300", **data):
    return {"id": str(i), "application_id": APP_ID, "guild_id": "200", "channel_id": channel,
            "token": f"tok{i}", "member": member, **data}


async def send_interaction(server, payload):
    path = f"/interactions/{payload['id']}/"
    await server.dispatch("INTERACTION_CREATE", payload)
    await until(lambda: server.find("POST", path), timeout=5)
    return server.find("POST", path)[-1]["json"]


async def test_help_and_pro(server, bot):
    say = make_say(server)
    body = await say(USER, ".yardım")
    assert "Yardım" in text(body) and body["components"][0]["components"][0]["custom_id"] == "help:cat"
    assert "çalış" in text(await say(USER, ".help çalış")).lower()
    assert "Pro değil" in text(await say(USER, ".pro"))
    resp = await send_interaction(server, interaction(1, USER, type=3, data={"custom_id": "help:cat", "component_type": 3,
                                                                            "values": ["ekonomi"]},
                                                     message={"id": "m1", "channel_id": "300"}))
    assert "Ekonomi" in resp["data"]["embeds"][0]["title"]
    assert "bulunamadı" not in str(server.requests[-1])


async def test_pro_management(server, bot):
    say = make_say(server)
    assert "sadece bot sahibi" in text(await say(USER, ".proekle 7 30g"))
    assert "artık 💎 **Pro**" in text(await say(OWNER, ".proekle <@7> 30g"))
    active, until_ts = bot.db.pro_until("7")
    assert active and 29 * 86400 < until_ts - time.time() <= 30 * 86400
    await say(OWNER, ".proekle 7 1g")
    assert bot.db.pro_until("7")[1] - until_ts == pytest.approx(86400, abs=5)
    assert "Pro aktif" in text(await say(USER, ".pro"))
    assert "kalıcı" in text(await say(OWNER, ".proekle 9 kalıcı"))
    assert bot.db.pro_until("9") == (True, None)
    assert "Pro Üyeler (2)" in text(await say(OWNER, ".proliste"))
    assert "kaldırıldı" in text(await say(OWNER, ".prosil 9"))
    assert not bot.is_pro("9") and bot.is_pro("100")


async def test_work_transfer_and_tkm(server, bot):
    say = make_say(server)
    body = await say(USER, ".çalış")
    balance = bot.db.balance("7")
    assert config.WORK_MIN <= balance <= config.WORK_MAX and "Mesai" in text(body)
    assert "Yorgunsun" in text(await say(USER, ".calis"))
    bot.db.execute("INSERT INTO pro (user_id, until, added) VALUES ('8', NULL, ?)", (time.time(),))
    await say(USER2, ".çalış")
    assert config.WORK_MIN * 1.5 - 1 <= bot.db.balance("8") <= config.WORK_MAX * 1.5
    bot.db.execute("UPDATE users SET last_work = ? WHERE user_id = '8'", (time.time() - 13 * 3600,))
    assert "Mesai" in text(await say(USER2, ".çalış"))

    bot.db.execute("UPDATE users SET balance = 1000 WHERE user_id = '7'")
    body = await say(USER, ".gönder <@8> 100")
    assert "95 coin" in text(body) and bot.db.balance("7") == 900
    assert "Yeterli paran yok" in text(await say(USER, ".gönder <@8> 5000"))
    assert "Kendine" in text(await say(USER, ".gönder <@7> 5"))

    before = bot.db.balance("7")
    body = await say(USER, ".tkm makas 50")
    after = bot.db.balance("7")
    assert after - before in (-50, 0, 50) and "Taş Kağıt Makas" in text(body)
    assert "yavaş" in text(await say(USER, ".tkm taş"))
    assert "Seçimini yaz" in text(await say(USER2, ".tkm kalem"))
    assert "En Zenginler" in text(await say(USER, ".zenginler"))
    assert "Toplam servet" in text(await say(USER, ".profil"))


async def test_company_market_and_stocks(server, bot):
    say = make_say(server)
    bot.db.execute("INSERT INTO users (user_id, balance) VALUES ('7', 5000), ('8', 5000)")
    assert "Pro" in text(await say(USER, '.şirket kur "Elmas Madeni" elmas'))
    body = await say(USER, '.şirket kur "Demir Çelik" demir')
    assert "Şirket Kuruldu" in text(body)
    company = bot.db.one("SELECT * FROM companies WHERE owner_id = '7'")
    assert company["ticker"] == "DEMI" and bot.db.balance("7") == 4000
    assert bot.db.one("SELECT kind FROM stocks WHERE symbol = 'DEMI'")["kind"] == "sirket"

    assert "üretildi" in text(await say(USER, ".şirket üret"))
    assert "Fabrika çalışıyor" in text(await say(USER, ".şirket üret"))
    stock = bot.db.one("SELECT stock, vault FROM companies WHERE owner_id = '7'")
    assert stock["stock"] > 0 and stock["vault"] < 200
    assert "arasında olmalı" in text(await say(USER, ".şirket fiyat 5"))
    await say(USER, ".şirket fiyat 60")
    assert "DEMI" in text(await say(USER2, ".market"))
    body = await say(USER2, ".satınal DEMI 3")
    assert "aldın" in text(body) and bot.db.inventory("8") == {"demir": 3} and bot.db.balance("8") == 5000 - 180
    vault = bot.db.one("SELECT vault FROM companies WHERE owner_id = '7'")["vault"]
    assert vault == stock["vault"] + 180 - int(180 * config.MARKET_FEE)
    assert "Kendi şirketinden" in text(await say(USER, ".satınal DEMI 1"))
    assert "eksikler" in text(await say(USER, ".şirket yükselt"))

    assert "Pazar Fiyatları" in text(await say(USER2, ".pazar"))
    assert "pazara satıldı" in text(await say(USER2, ".sat demir 2"))
    assert bot.db.inventory("8") == {"demir": 1}

    assert "HLDG" in text(await say(USER2, ".borsa"))
    body = await say(USER2, ".borsa al HLDG 2")
    assert "aldın" in text(body) and "Komisyon" in text(body)
    assert bot.db.one("SELECT qty FROM holdings WHERE user_id = '8' AND symbol = 'HLDG'")["qty"] == 2
    assert "HLDG" in text(await say(USER2, ".portföy"))
    assert "sattın" in text(await say(USER2, ".borsa sat HLDG hepsi"))
    assert bot.db.one("SELECT qty FROM holdings WHERE user_id = '8' AND symbol = 'HLDG'")["qty"] == 0
    assert "Böyle bir hisse yok" in text(await say(USER2, ".borsa al YOK 1"))

    bot.db.execute("UPDATE stocks SET updated = updated - ?", (config.STOCK_TICK * 3,))
    await bot.modules["market"].tick()
    row = bot.db.one("SELECT history FROM stocks WHERE symbol = 'HLDG'")
    assert row["history"].count(",") >= 2

    body = await say(USER, ".şirket kapat")
    assert body["components"][0]["components"][0]["custom_id"] == "co:close:7:yes"
    resp = await send_interaction(server, interaction(2, USER2, type=3, data={"custom_id": "co:close:7:yes",
                                                                             "component_type": 2}))
    assert "senin için değil" in resp["data"]["embeds"][0]["description"]
    await send_interaction(server, interaction(3, USER, type=3, data={"custom_id": "co:close:7:yes", "component_type": 2}))
    assert bot.db.one("SELECT 1 FROM companies WHERE owner_id = '7'") is None


async def test_slash_and_prefix(server, bot):
    say = make_say(server)
    assert "Yardım" in text(await say(USER, "/yardım"))
    assert "Pong" in text(await say(USER, "/ping"))

    await until(lambda: server.find("PUT", "/applications/5000/commands"), timeout=5)
    registered = {c["name"]: c for c in server.find("PUT", "/applications/5000/commands")[-1]["json"]}
    assert {"calis", "sirket", "tkm", "borsa", "gonder"} <= set(registered)
    assert [o["name"] for o in registered["gonder"]["options"]] == ["kullanici", "argumanlar"]

    def slash(i, member, name, options=()):
        return interaction(i, member, type=2, data={"name": name, "options": list(options)})

    async def run(payload):
        await server.dispatch("INTERACTION_CREATE", payload)
        def answers():
            return [r["json"] for r in server.find("POST", "/channels/300/messages")
                    if (r.get("json") or {}).get("interaction_id") == payload["id"]]
        await until(lambda: answers(), timeout=5)
        return answers()[0]

    resp = await run(slash(20, USER, "ping"))
    assert server.find("POST", "/interactions/20/")[0]["json"]["type"] == 5
    assert "Pong" in text(resp)
    resp = await run(slash(21, USER, "calis"))
    assert "Mesai" in text(resp) and bot.db.balance("7") > 0
    resp = await run(slash(22, USER, "gonder", [{"name": "kullanici", "type": 6, "value": "8"},
                                                {"name": "argumanlar", "type": 3, "value": "20"}]))
    assert "gönderildi" in text(resp) and bot.db.balance("8") == 19
    resp = await run(slash(23, USER, "proekle", [{"name": "argumanlar", "type": 3, "value": "8 1g"}]))
    assert "sadece bot sahibi" in text(resp)
    resp = await run(slash(24, USER, "tkm", [{"name": "argumanlar", "type": 3, "value": "makas"}]))
    assert "Taş Kağıt Makas" in text(resp)


async def test_no_double_replies(server, bot):
    say = make_say(server)

    def replies_to(message_id):
        return [r for r in server.find("POST", "/channels/300/messages")
                if (r.get("json") or {}).get("message_reference", {}).get("message_id") == message_id]

    event = {"id": "77001", "channel_id": "300", "guild_id": "200", "content": ".ping",
             "author": USER["user"], "member": {"roles": []}}
    await server.dispatch("MESSAGE_CREATE", event)
    await server.dispatch("MESSAGE_CREATE", event)
    await until(lambda: replies_to("77001"), timeout=5)
    await say(USER2, ".ping")
    assert len(replies_to("77001")) == 1

    await server.dispatch("INTERACTION_CREATE", interaction(90, USER, type=2, data={"name": "pro", "options": []}))
    await server.dispatch("MESSAGE_CREATE", {"id": "77002", "channel_id": "300", "guild_id": "200", "content": "/pro",
                                             "author": USER["user"], "member": {"roles": []}})
    await until(lambda: any((r["json"] or {}).get("interaction_id") == "90"
                            for r in server.find("POST", "/channels/300/messages")), timeout=5)
    await say(USER2, ".ping")
    assert not replies_to("77002")

    await server.dispatch("MESSAGE_CREATE", {"id": "77010", "channel_id": "300", "guild_id": "200", "content": "/borsa HLDG",
                                             "author": USER2["user"], "member": {"roles": []}})
    await server.dispatch("INTERACTION_CREATE", interaction(91, USER2, type=2, data={
        "name": "borsa", "options": [{"name": "argumanlar", "type": 3, "value": "HLDG"}]}))
    await until(lambda: any((r["json"] or {}).get("interaction_id") == "91"
                            for r in server.find("POST", "/channels/300/messages")), timeout=5)
    await asyncio.sleep(bot.SLASH_ECHO_WAIT + 0.3)
    assert not replies_to("77010")

    await server.dispatch("MESSAGE_CREATE", {"id": "77011", "channel_id": "300", "guild_id": "200", "content": "/ping",
                                             "author": USER2["user"], "member": {"roles": []}})
    await until(lambda: replies_to("77011"), timeout=5)

    await server.dispatch("MESSAGE_CREATE", {"id": "77003", "channel_id": "300", "guild_id": "200", "content": "/yardım",
                                             "application_id": "5000", "author": USER["user"], "member": {"roles": []}})
    await say(USER2, ".ping")
    assert not replies_to("77003")

    assert "Mesai" in text(await say(USER, ".çalış"))
    assert "Yorgunsun" in text(await say(USER, ".çalış"))
