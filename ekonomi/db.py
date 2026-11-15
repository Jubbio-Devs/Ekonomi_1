from __future__ import annotations

import os
import sqlite3
import time
from typing import Dict, Iterable, List, Optional, Tuple

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    user_id   TEXT PRIMARY KEY,
    balance   INTEGER NOT NULL DEFAULT 0,
    last_work REAL NOT NULL DEFAULT 0,
    earned    INTEGER NOT NULL DEFAULT 0,
    tkm_win   INTEGER NOT NULL DEFAULT 0,
    tkm_loss  INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS inventory (
    user_id TEXT NOT NULL,
    item    TEXT NOT NULL,
    qty     INTEGER NOT NULL,
    PRIMARY KEY (user_id, item)
);
CREATE TABLE IF NOT EXISTS companies (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    owner_id     TEXT NOT NULL UNIQUE,
    name         TEXT NOT NULL UNIQUE COLLATE NOCASE,
    ticker       TEXT NOT NULL UNIQUE,
    material     TEXT NOT NULL,
    level        INTEGER NOT NULL DEFAULT 1,
    price        INTEGER NOT NULL,
    stock        INTEGER NOT NULL DEFAULT 0,
    vault        INTEGER NOT NULL DEFAULT 0,
    sold         INTEGER NOT NULL DEFAULT 0,
    revenue      INTEGER NOT NULL DEFAULT 0,
    last_produce REAL NOT NULL DEFAULT 0,
    created      REAL NOT NULL
);
CREATE TABLE IF NOT EXISTS stocks (
    symbol     TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    kind       TEXT NOT NULL,
    price      REAL NOT NULL,
    base       REAL NOT NULL,
    volatility REAL NOT NULL,
    updated    REAL NOT NULL,
    history    TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS holdings (
    user_id TEXT NOT NULL,
    symbol  TEXT NOT NULL,
    qty     INTEGER NOT NULL,
    cost    INTEGER NOT NULL,
    PRIMARY KEY (user_id, symbol)
);
CREATE TABLE IF NOT EXISTS pro (
    user_id  TEXT PRIMARY KEY,
    until    REAL,
    added_by TEXT,
    added    REAL NOT NULL
);
"""


class Database:
    def __init__(self, path: str) -> None:
        if path != ":memory:":
            os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        self.path = path
        self.conn = sqlite3.connect(path, isolation_level=None, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def execute(self, sql: str, params: Iterable = ()) -> sqlite3.Cursor:
        return self.conn.execute(sql, tuple(params))

    def one(self, sql: str, params: Iterable = ()) -> Optional[sqlite3.Row]:
        return self.conn.execute(sql, tuple(params)).fetchone()

    def all(self, sql: str, params: Iterable = ()) -> List[sqlite3.Row]:
        return self.conn.execute(sql, tuple(params)).fetchall()

    def transaction(self) -> "Transaction":
        return Transaction(self.conn)

    def close(self) -> None:
        self.conn.close()

    def user(self, user_id: str) -> sqlite3.Row:
        self.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        return self.one("SELECT * FROM users WHERE user_id = ?", (user_id,))

    def balance(self, user_id: str) -> int:
        return int(self.user(user_id)["balance"])

    def add_balance(self, user_id: str, amount: int) -> int:
        self.user(user_id)
        self.execute("UPDATE users SET balance = balance + ? WHERE user_id = ?", (int(amount), user_id))
        return self.balance(user_id)

    def take_balance(self, user_id: str, amount: int) -> bool:
        self.user(user_id)
        cur = self.execute("UPDATE users SET balance = balance - ? WHERE user_id = ? AND balance >= ?",
                           (int(amount), user_id, int(amount)))
        return cur.rowcount == 1

    def inventory(self, user_id: str) -> Dict[str, int]:
        return {r["item"]: r["qty"] for r in self.all("SELECT item, qty FROM inventory WHERE user_id = ? AND qty > 0 "
                                                       "ORDER BY item", (user_id,))}

    def add_item(self, user_id: str, item: str, qty: int) -> None:
        self.execute("INSERT INTO inventory (user_id, item, qty) VALUES (?, ?, ?) "
                     "ON CONFLICT(user_id, item) DO UPDATE SET qty = qty + excluded.qty", (user_id, item, int(qty)))

    def take_item(self, user_id: str, item: str, qty: int) -> bool:
        cur = self.execute("UPDATE inventory SET qty = qty - ? WHERE user_id = ? AND item = ? AND qty >= ?",
                           (int(qty), user_id, item, int(qty)))
        return cur.rowcount == 1

    def pro_until(self, user_id: str) -> Tuple[bool, Optional[float]]:
        row = self.one("SELECT until FROM pro WHERE user_id = ?", (user_id,))
        if row is None:
            return False, None
        if row["until"] is not None and row["until"] <= time.time():
            return False, row["until"]
        return True, row["until"]


class Transaction:
    def __init__(self, conn: sqlite3.Connection) -> None:
        self.conn = conn

    def __enter__(self) -> "Transaction":
        self.conn.execute("BEGIN IMMEDIATE")
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.conn.execute("ROLLBACK" if exc_type else "COMMIT")
