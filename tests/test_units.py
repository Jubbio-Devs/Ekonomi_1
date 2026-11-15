from __future__ import annotations

import time


from ekonomi.db import Database
from ekonomi.economy_data import find_material
from ekonomi.modules.games import BEATS, parse_choice
from ekonomi.modules.market import step_price
from ekonomi.utils import fmt_duration, fold, money, parse_amount, parse_duration, parse_id, sparkline, split_args


def test_parsers():
    assert fold("ÇALIŞ") == "calis" and fold("Şirket") == "sirket" and fold("İstanbul") == "istanbul"
    assert parse_duration("10dk") == 600 and parse_duration("1sa30dk") == 5400 and parse_duration("2g") == 172800
    assert parse_duration("1ay") == 30 * 86400 and parse_duration("1y") == 365 * 86400 and parse_duration("15") == 900
    assert parse_duration("abc") is None and parse_duration("10x") is None
    assert fmt_duration(5400) == "1 saat 30 dakika"
    assert parse_amount("500") == 500 and parse_amount("1.500") == 1500 and parse_amount("2k") == 2000
    assert parse_amount("1,5m") == 1_500_000 and parse_amount("hepsi", 42) == 42 and parse_amount("-5") is None
    assert parse_amount("abc") is None and parse_amount("0") is None
    assert money(1234567) == "1.234.567 coin"
    assert parse_id("<@123>") == "123" and parse_id("<@&45>") == "45" and parse_id("<#9>") == "9"
    assert parse_id("77") == "77" and parse_id("ali") is None
    assert split_args('buton "Oyun Rolleri" <@&1>') == ["buton", "Oyun Rolleri", "<@&1>"]
    assert split_args('tırnak "kapanmamış') == ["tırnak", '"kapanmamış']
    assert sparkline([1, 2, 3]) == "▁▄█" and sparkline([5]) == ""


def test_materials_and_choices():
    assert find_material("Taş") == "tas" and find_material("taşlar") == "tas" and find_material("demirler") == "demir"
    assert find_material("💎") == "elmas" and find_material("ALTIN") == "altin" and find_material("su") is None
    assert parse_choice("Taş") == "tas" and parse_choice("kağıt") == "kagit" and parse_choice("m") == "makas"
    assert parse_choice("✂️") == "makas" and parse_choice("kalem") == ""
    assert BEATS["tas"] == "makas"


def test_step_price_bounds():
    price = 100.0
    for _ in range(5000):
        price = step_price(price, 100, 0.5)
        assert 20 <= price <= 500


def test_database(tmp_path):
    db = Database(str(tmp_path / "x.db"))
    assert db.balance("1") == 0
    db.add_balance("1", 100)
    assert not db.take_balance("1", 150) and db.take_balance("1", 60) and db.balance("1") == 40
    db.add_item("1", "demir", 5)
    assert not db.take_item("1", "demir", 6) and db.take_item("1", "demir", 2) and db.inventory("1") == {"demir": 3}
    db.execute("INSERT INTO pro (user_id, until, added) VALUES ('7', ?, ?)", (time.time() - 1, time.time()))
    assert db.pro_until("7")[0] is False
    db.close()
    again = Database(str(tmp_path / "x.db"))
    assert again.balance("1") == 40


def test_delisted_stock_paid_out(tmp_path):
    from ekonomi import create_bot

    bot = create_bot(str(tmp_path / "n.db"))
    db = bot.db
    db.execute("INSERT INTO stocks (symbol, name, kind, price, base, volatility, updated) "
               "VALUES ('SYN', 'Eski', 'hisse', 150, 140, 0.03, 0)")
    db.execute("INSERT INTO holdings (user_id, symbol, qty, cost) VALUES ('7', 'SYN', 4, 500)")
    bot.modules["market"].seed()
    assert db.balance("7") == 600
    assert db.one("SELECT 1 FROM stocks WHERE symbol = 'SYN'") is None
    assert db.one("SELECT 1 FROM holdings WHERE symbol = 'SYN'") is None
    assert db.one("SELECT 1 FROM stocks WHERE symbol = 'TKNO'")
    db.close()
