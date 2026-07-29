"""Projection 검증 (P3 F5) — 프로젝션이 JSONL과 일치·결정적 재생성인지 확인.

- 결정적 재생성: 임시 DB에 재구축한 checksum == 현재 저장 checksum.
- 누락 없음: 현재 DB 테이블 카운트 == 소스에서 재계산한 기대 카운트.
소스 JSONL 무변경(읽기만).
"""
from __future__ import annotations

import os
import tempfile

from jarvis.db.projector import _SOURCES, _read_jsonl, compute_checksum, rebuild
from jarvis.db.sqlite import Database, db_path, exists


def _expected_counts() -> dict:
    """소스에서 직접 기대 written 수 계산(테이블별)."""
    exp = {"strategy_events": 0, "strategies": 0, "signals": 0, "allocations": 0,
           "portfolio_decisions": 0, "experiments": 0, "audit_events": 0}
    for name, resolver, _ in _SOURCES:
        rows, _f = _read_jsonl(resolver())
        if name == "registry":
            sids = {r.get("strategy_id") for r in rows if r.get("strategy_id")}
            exp["strategy_events"] = sum(1 for r in rows if r.get("strategy_id"))
            exp["strategies"] = len(sids)
        elif name == "fusion_signals":
            exp["signals"] = sum(len(r.get("contributions", [])) for r in rows)
        elif name == "allocation_proposals":
            exp["allocations"] = sum(len(r.get("proposals", [])) for r in rows)
        elif name == "portfolio_decisions":
            exp["portfolio_decisions"] = len(rows)
        elif name == "experiments":
            exp["experiments"] = len(rows)
        elif name == "audit":
            exp["audit_events"] = len(rows)
    return exp


def verify(path: str | None = None) -> dict:
    """프로젝션 무결성 검증. 반환: {ok, deterministic, counts_match, ...}."""
    path = path or db_path()
    if not exists(path):
        return {"ok": False, "reason": "database_missing", "database_exists": False}

    db = Database(path, read_only=True)
    stored_checksum = db.get_meta("checksum")
    counts = {}
    from jarvis.db.sqlite import TABLES
    for t in TABLES:
        if t == "projection_meta":
            continue
        counts[t] = db.count(t)
    db.close()

    # 결정적 재생성: 임시 DB에 재구축
    tmp = os.path.join(tempfile.mkdtemp(), "verify.db")
    rep = rebuild(tmp, ts="verify")
    dv = Database(tmp, read_only=True)
    rebuilt_checksum = compute_checksum(dv)
    dv.close()
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(tmp + suffix)
        except OSError:
            pass

    deterministic = (rebuilt_checksum == stored_checksum) if stored_checksum else \
        (rebuilt_checksum == rep.checksum)
    expected = _expected_counts()
    counts_match = all(counts.get(k, 0) == expected.get(k, 0) for k in expected)

    return {
        "ok": bool(deterministic and counts_match),
        "database_exists": True,
        "deterministic": deterministic,
        "counts_match": counts_match,
        "stored_checksum": stored_checksum,
        "rebuilt_checksum": rebuilt_checksum,
        "table_counts": counts,
        "expected_counts": expected,
    }
