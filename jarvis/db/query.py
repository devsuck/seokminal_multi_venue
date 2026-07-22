"""Projection Query API (P3 F4) — 읽기 전용 헬퍼. 비즈니스 로직 없음, 쿼리만.

DB 없으면 빈 결과(정직). index.db는 disposable이므로 호출부는 없어도 안전.
"""
from __future__ import annotations

from jarvis.db.projector import _ACTIVE
from jarvis.db.sqlite import Database, db_path, exists


def _ro() -> Database | None:
    if not exists(db_path()):
        return None
    return Database(read_only=True)


def get_active_strategies() -> list[dict]:
    db = _ro()
    if db is None:
        return []
    q = ("SELECT * FROM strategies WHERE status IN (%s) ORDER BY id"
         % ",".join("?" * len(_ACTIVE)))
    out = db.query(q, tuple(sorted(_ACTIVE)))
    db.close()
    return out


def get_strategy_history(strategy_id: str) -> list[dict]:
    db = _ro()
    if db is None:
        return []
    out = db.query("SELECT * FROM strategy_events WHERE strategy_id=? ORDER BY event_id",
                   (strategy_id,))
    db.close()
    return out


def get_strategy_lineage(strategy_id: str) -> list[dict]:
    """전략 상태전이 계보(이벤트 체인). 지식그래프 계보는 후속 단계."""
    events = get_strategy_history(strategy_id)
    return [{"previous_state": e["previous_state"], "new_state": e["new_state"],
             "timestamp": e["timestamp"], "reason": e["reason"]} for e in events]


def get_latest_portfolio_decision() -> dict | None:
    db = _ro()
    if db is None:
        return None
    rows = db.query("SELECT * FROM portfolio_decisions ORDER BY id DESC LIMIT 1")
    db.close()
    return rows[0] if rows else None


def get_failed_experiments(limit: int = 100) -> list[dict]:
    db = _ro()
    if db is None:
        return []
    out = db.query("SELECT * FROM experiments WHERE status IN ('rejected','failed','blocked')"
                   " ORDER BY created_at DESC LIMIT ?", (limit,))
    db.close()
    return out


def get_recent_signals(limit: int = 50) -> list[dict]:
    db = _ro()
    if db is None:
        return []
    out = db.query("SELECT * FROM signals ORDER BY timestamp DESC, id DESC LIMIT ?", (limit,))
    db.close()
    return out


def table_counts() -> dict:
    db = _ro()
    if db is None:
        return {}
    from jarvis.db.sqlite import TABLES
    out = {t: db.count(t) for t in TABLES}
    db.close()
    return out
