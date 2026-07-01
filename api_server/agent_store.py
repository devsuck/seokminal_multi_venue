"""SQLite-backed store for AI trading agents and their structured cycle logs.

The shell agent loop talks to the backend over HTTP (as it already does for
Alpaca), so the backend is the single source of truth for agent definitions
and per-cycle records. Cycles are structured rows — not raw stdout — so the
frontend can render compact cards instead of dumping a terminal pane.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import sqlite3
import uuid
from pathlib import Path

# Known agent types and their default cadence/universe/gate profile. Profiles
# are data, not code, so a new strategy is a new row rather than a new branch.
AGENT_PROFILES: dict[str, dict] = {
    "swing": {
        "label": "스윙",
        "cadence_seconds": 8 * 3600,
        "universe_size": 10,
        "buy_score_threshold": 18,  # of 40
        "force_eod_close": False,
    },
    "longterm": {
        # 장기투자 — 스윙과 동일 실행 경로, 주기만 길게(주 단위 점검).
        "label": "장투",
        "cadence_seconds": 7 * 24 * 3600,
        "universe_size": 15,
        "buy_score_threshold": 16,  # of 40
        "force_eod_close": False,
    },
    "daytrade": {
        "label": "데이트레이딩",
        "cadence_seconds": 5 * 60,
        "universe_size": 15,
        "buy_score_threshold": 22,
        "force_eod_close": True,
        "tp_pct": 0.04,   # +4% take-profit
        "sl_pct": 0.02,   # -2% stop-loss (tight for intraday)
    },
    "kr_daytrade": {
        "label": "데이트레이딩 (한국주식)",
        "venue": "KR",
        "cadence_seconds": 5 * 60,
        "buy_score_threshold": 55,   # intraday conviction 0~100
        "position_pct": 0.10,
        "force_eod_close": True,      # 장 마감 전 청산
        "paper": True,               # KIS 모의
        "tp_pct": 0.03,
        "sl_pct": 0.02,
    },
    "hl_daytrade": {
        "label": "데이트레이딩 (Hyperliquid 무기한)",
        "venue": "HL",
        "cadence_seconds": 5 * 60,
        "buy_score_threshold": 55,   # intraday conviction 0~100
        "leverage": 3,               # default leverage multiplier
        "position_pct": 0.10,        # equity fraction per position (pre-leverage)
        "force_eod_close": False,    # crypto trades 24/7 — no enforced EOD flat
        "paper": True,               # testnet paper trading
        "tp_pct": 0.05,   # leverage-adjusted move (5% of price)
        "sl_pct": 0.03,
    },
}

_VALID_DECISIONS = {"WATCH", "BUY", "SELL", "SKIP", "HOLD"}


def _db_path() -> Path:
    return Path(os.environ.get("AGENT_DB_PATH", "data/agents.db"))


def _conn() -> sqlite3.Connection:
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS agents (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        type TEXT NOT NULL,
        account_alloc REAL NOT NULL,
        status TEXT NOT NULL,
        created_at TEXT NOT NULL
    )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS cycles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        cycle INTEGER NOT NULL,
        ts TEXT NOT NULL,
        payload TEXT NOT NULL
    )""")
    # Migrations for older DBs.
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(agents)")}
    if "paper" not in cols:
        conn.execute("ALTER TABLE agents ADD COLUMN paper INTEGER NOT NULL DEFAULT 1")
    if "autonomy" not in cols:
        # 1=fixed rules, 2=AI strategist (backtest-validated), 3=full autonomy
        conn.execute("ALTER TABLE agents ADD COLUMN autonomy INTEGER NOT NULL DEFAULT 2")
    if "market" not in cols:
        # US | KR | MIXED — market scope for swing agents (others ignore it)
        conn.execute("ALTER TABLE agents ADD COLUMN market TEXT NOT NULL DEFAULT 'US'")
    if "protected" not in cols:
        # 잠금: 삭제 시 이름 타이핑 확인 요구 (실수 삭제 방지)
        conn.execute("ALTER TABLE agents ADD COLUMN protected INTEGER NOT NULL DEFAULT 0")
    conn.commit()
    return conn


# ── Agents ────────────────────────────────────────────────────────────────────

def create_agent(name: str, agent_type: str, account_alloc: float,
                 paper: bool = True, autonomy: int = 2, market: str = "US") -> dict:
    if agent_type not in AGENT_PROFILES:
        raise ValueError(f"unknown agent type: {agent_type!r}")
    if autonomy not in (1, 2, 3):
        raise ValueError(f"autonomy must be 1, 2, or 3, got {autonomy}")
    if market not in ("US", "KR", "MIXED"):
        raise ValueError(f"market must be US, KR, or MIXED, got {market!r}")
    agent = {
        "id": uuid.uuid4().hex[:8],
        "name": name,
        "type": agent_type,
        "account_alloc": float(account_alloc),
        "status": "stopped",
        "paper": bool(paper),
        "autonomy": int(autonomy),
        "market": market,
        "created_at": _dt.datetime.now(_dt.UTC).isoformat(),
    }
    conn = _conn()
    conn.execute(
        "INSERT INTO agents (id,name,type,account_alloc,status,paper,autonomy,market,created_at) "
        "VALUES (?,?,?,?,?,?,?,?,?)",
        (agent["id"], agent["name"], agent["type"], agent["account_alloc"],
         agent["status"], 1 if paper else 0, int(autonomy), market, agent["created_at"]),
    )
    conn.commit()
    conn.close()
    return _with_profile(agent)


def list_agents() -> list[dict]:
    conn = _conn()
    rows = conn.execute("SELECT * FROM agents ORDER BY created_at").fetchall()
    conn.close()
    return [_with_profile(dict(r)) for r in rows]


def get_agent(agent_id: str) -> dict | None:
    conn = _conn()
    row = conn.execute("SELECT * FROM agents WHERE id=?", (agent_id,)).fetchone()
    conn.close()
    return _with_profile(dict(row)) if row else None


def set_status(agent_id: str, status: str) -> dict | None:
    if status not in ("running", "stopped"):
        raise ValueError(f"invalid status: {status!r}")
    conn = _conn()
    cur = conn.execute("UPDATE agents SET status=? WHERE id=?", (status, agent_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return get_agent(agent_id) if changed else None


def delete_agent(agent_id: str) -> bool:
    conn = _conn()
    cur = conn.execute("DELETE FROM agents WHERE id=?", (agent_id,))
    conn.execute("DELETE FROM cycles WHERE agent_id=?", (agent_id,))
    conn.commit()
    deleted = cur.rowcount
    conn.close()
    return bool(deleted)


def set_protected(agent_id: str, protected: bool) -> dict | None:
    conn = _conn()
    cur = conn.execute("UPDATE agents SET protected=? WHERE id=?", (1 if protected else 0, agent_id))
    conn.commit()
    changed = cur.rowcount
    conn.close()
    return get_agent(agent_id) if changed else None


def _with_profile(agent: dict) -> dict:
    agent["profile"] = AGENT_PROFILES.get(agent["type"], {})
    if "paper" in agent:  # SQLite stores 0/1 → expose as bool
        agent["paper"] = bool(agent["paper"])
    if "protected" in agent:
        agent["protected"] = bool(agent["protected"])
    return agent


# ── Cycles ──────────────────────────────────────────────────────────────────

def record_cycle(agent_id: str, payload: dict) -> dict:
    """Persist one structured cycle. Validates the decision enum; stores the
    rest as a JSON payload so the schema can evolve without migrations."""
    decision = payload.get("decision")
    if decision not in _VALID_DECISIONS:
        raise ValueError(f"invalid decision: {decision!r} (expected {_VALID_DECISIONS})")
    entry = {
        "agent_id": agent_id,
        "cycle": int(payload.get("cycle", 0)),
        "ts": payload.get("ts") or _dt.datetime.now(_dt.UTC).isoformat(),
        **payload,
    }
    conn = _conn()
    conn.execute(
        "INSERT INTO cycles (agent_id,cycle,ts,payload) VALUES (?,?,?,?)",
        (agent_id, entry["cycle"], entry["ts"], json.dumps(entry, ensure_ascii=False)),
    )
    conn.commit()
    conn.close()
    return entry


def read_cycles(agent_id: str, limit: int = 50) -> list[dict]:
    """Return recent cycles for an agent, newest last."""
    conn = _conn()
    rows = conn.execute(
        "SELECT payload FROM cycles WHERE agent_id=? ORDER BY id DESC LIMIT ?",
        (agent_id, limit),
    ).fetchall()
    conn.close()
    return [json.loads(r["payload"]) for r in reversed(rows)]
