"""SQLite 연결 관리자 (P3 F1) — WAL, thread-safe, 읽기 최적화.

index.db는 disposable 프로젝션. 진실의 소유권 없음(소스 = JSONL).
"""
from __future__ import annotations

import os
import sqlite3
import threading

from jarvis.config import state_path

DB_NAME = "index.db"
_SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "schema.sql")

# 프로젝션 테이블(rebuild 시 drop 대상). projection_meta도 포함.
TABLES = ["strategies", "strategy_events", "signals", "allocations",
          "portfolio_decisions", "experiments", "audit_events", "projection_meta"]


def db_path() -> str:
    return state_path(DB_NAME)


def schema_sql() -> str:
    with open(_SCHEMA_FILE) as f:
        return f.read()


class Database:
    """thread-safe 연결. 쓰기는 lock 직렬화, 읽기는 WAL 동시성."""

    def __init__(self, path: str | None = None, read_only: bool = False) -> None:
        self.path = path or db_path()
        self._lock = threading.Lock()
        if read_only:
            self.conn = sqlite3.connect(f"file:{self.path}?mode=ro", uri=True,
                                        check_same_thread=False)
        else:
            os.makedirs(os.path.dirname(self.path), exist_ok=True)
            self.conn = sqlite3.connect(self.path, check_same_thread=False)
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=NORMAL")
            self.conn.execute("PRAGMA foreign_keys=ON")
        self.conn.row_factory = sqlite3.Row

    # ── 쓰기 ──
    def executescript(self, sql: str) -> None:
        with self._lock:
            self.conn.executescript(sql)
            self.conn.commit()

    def execute(self, sql: str, params=()):
        with self._lock:
            cur = self.conn.execute(sql, params)
            self.conn.commit()
            return cur

    def executemany(self, sql: str, rows) -> None:
        with self._lock:
            self.conn.executemany(sql, rows)
            self.conn.commit()

    def apply_schema(self) -> None:
        self.executescript(schema_sql())

    def drop_all(self) -> None:
        with self._lock:
            for t in TABLES:
                self.conn.execute(f"DROP TABLE IF EXISTS {t}")
            self.conn.commit()

    def set_meta(self, key: str, value: str) -> None:
        self.execute("INSERT OR REPLACE INTO projection_meta(key, value) VALUES (?, ?)",
                     (key, value))

    def get_meta(self, key: str) -> str | None:
        rows = self.query("SELECT value FROM projection_meta WHERE key=?", (key,))
        return rows[0]["value"] if rows else None

    # ── 읽기 ──
    def query(self, sql: str, params=()) -> list[dict]:
        cur = self.conn.execute(sql, params)
        return [dict(r) for r in cur.fetchall()]

    def count(self, table: str) -> int:
        return self.query(f"SELECT COUNT(*) AS n FROM {table}")[0]["n"]

    def close(self) -> None:
        self.conn.close()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


def exists(path: str | None = None) -> bool:
    return os.path.exists(path or db_path())
