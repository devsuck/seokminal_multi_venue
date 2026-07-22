"""Projection Engine (P3 F2) — JSONL 이벤트 → SQLite 테이블.

`python -m jarvis.db.projector rebuild`:
  1) 프로젝션 테이블 drop  2) 모든 JSONL 소스 read  3) DB 재구축
  4) 카운트 검증  5) ProjectionReport 산출.

**소스 JSONL 무변경(audit.jsonl에도 안 씀).** 프로젝션 provenance는 projection_meta 테이블.
결정적: 같은 소스 → 같은 checksum. 손상 레코드는 skip+failures 집계(크래시 없음).
"""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field

from jarvis.config import state_path
from jarvis.db.sqlite import Database, TABLES

# 소스 경로 — jarvis _state는 state_path(테스트에서 patch), research는 모듈 변수.
EXPERIMENTS_PATH = os.path.join(os.path.dirname(__file__), "..", "..",
                               "research", "agents", "experiment_registry.jsonl")

_ACTIVE = {"watchlist", "paper_candidate", "paper_candidate_forward_test_required",
           "paper_active", "live_candidate", "micro_live", "constrained_live", "live"}

# checksum 대상 자연키 컬럼(autoincrement id 제외, projection_meta 제외)
_CHECKSUM_COLS = {
    "strategies": ["id", "name", "status", "family", "created_at", "updated_at", "config_hash"],
    "strategy_events": ["event_id", "strategy_id", "previous_state", "new_state", "timestamp", "reason"],
    "signals": ["strategy_id", "instrument", "direction", "strength", "timestamp"],
    "allocations": ["strategy_id", "weight", "risk_contribution", "timestamp"],
    "portfolio_decisions": ["decision", "reason", "timestamp", "regime", "risk_level"],
    "experiments": ["id", "hypothesis", "result", "status", "created_at", "metadata"],
    "audit_events": ["event", "actor", "action", "timestamp", "metadata"],
}


@dataclass
class ProjectionReport:
    timestamp: str
    sources_processed: list = field(default_factory=list)
    records_read: int = 0
    records_written: int = 0
    failures: int = 0
    checksum: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# ── 소스 경로 ──
def _sig_path():
    return state_path("fusion_signals.jsonl")


def _alloc_path():
    return state_path("allocation_proposals.jsonl")


def _pdec_path():
    return state_path("portfolio_decisions.jsonl")


def _registry_path():
    return state_path("registry.jsonl")


def _audit_path():
    return state_path("audit.jsonl")


def _read_jsonl(path: str) -> tuple[list[dict], int]:
    """(rows, failures). 손상 라인은 skip. 파일 없으면 ([],0)."""
    if not os.path.exists(path):
        return [], 0
    rows, failures = [], 0
    with open(path) as f:
        for ln in f:
            if not ln.strip():
                continue
            try:
                rows.append(json.loads(ln))
            except (json.JSONDecodeError, ValueError):
                failures += 1
    return rows, failures


# ── 프로젝터(테이블별) ──
def _project_registry(db, rows) -> int:
    """registry.jsonl → strategies(fold) + strategy_events(per line)."""
    fold: dict = {}
    events = []
    counter: dict = {}
    for ev in rows:
        sid = ev.get("strategy_id")
        if not sid:
            continue
        i = counter.get(sid, 0)
        counter[sid] = i + 1
        events.append((f"{sid}#{i}", sid, ev.get("from"), ev.get("to"),
                       ev.get("timestamp"), ev.get("reason")))
        cur = fold.get(sid)
        fold[sid] = {
            "id": sid, "name": ev.get("name") or (cur or {}).get("name") or sid,
            "status": ev.get("to"),
            "family": ev.get("family") or (cur or {}).get("family") or "",
            "created_at": (cur or {}).get("created_at") or ev.get("timestamp"),
            "updated_at": ev.get("timestamp"),
            "config_hash": ev.get("config_hash") or (cur or {}).get("config_hash"),
        }
    db.executemany(
        "INSERT INTO strategy_events(event_id,strategy_id,previous_state,new_state,timestamp,reason)"
        " VALUES (?,?,?,?,?,?)", events)
    strat_rows = [(s["id"], s["name"], s["status"], s["family"],
                   s["created_at"], s["updated_at"], s["config_hash"]) for s in fold.values()]
    db.executemany(
        "INSERT INTO strategies(id,name,status,family,created_at,updated_at,config_hash)"
        " VALUES (?,?,?,?,?,?,?)", strat_rows)
    return len(events) + len(strat_rows)


def _project_signals(db, rows) -> int:
    out = []
    for r in rows:
        instrument = r.get("instrument")
        ts = r.get("as_of") or r.get("timestamp")
        for c in r.get("contributions", []):
            out.append((c.get("strategy_id"), instrument, c.get("direction"),
                        c.get("strength"), ts))
    db.executemany(
        "INSERT INTO signals(strategy_id,instrument,direction,strength,timestamp)"
        " VALUES (?,?,?,?,?)", out)
    return len(out)


def _project_allocations(db, rows) -> int:
    out = []
    for r in rows:
        ts = r.get("timestamp")
        for p in r.get("proposals", []):
            out.append((p.get("strategy_id"), p.get("target_weight"),
                        p.get("risk_contribution"), ts))
    db.executemany(
        "INSERT INTO allocations(strategy_id,weight,risk_contribution,timestamp)"
        " VALUES (?,?,?,?)", out)
    return len(out)


def _project_portfolio_decisions(db, rows) -> int:
    out = []
    for r in rows:
        inputs = r.get("inputs") or {}
        meta = r.get("metadata") or {}
        reason = "; ".join(r.get("reasons") or []) or "; ".join(r.get("blockers") or [])
        out.append((r.get("decision"), reason, r.get("timestamp"),
                    inputs.get("regime"), meta.get("quality_mode")))
    db.executemany(
        "INSERT INTO portfolio_decisions(decision,reason,timestamp,regime,risk_level)"
        " VALUES (?,?,?,?,?)", out)
    return len(out)


_EXP_META_KEYS = ("reason", "data_source", "universe", "sharpe", "random_percentile",
                  "percentile", "failure_mechanism", "net", "net_pnl", "net_base")


def _project_experiments(db, rows) -> int:
    out = []
    for r in rows:
        meta = {k: r[k] for k in _EXP_META_KEYS if r.get(k) is not None}
        out.append((r.get("hypothesis_id") or r.get("id"),
                    r.get("name") or r.get("hypothesis") or r.get("hypothesis_id"),
                    r.get("diagnosis") or r.get("verdict") or r.get("result") or r.get("reason"),
                    r.get("status"), r.get("timestamp"),
                    json.dumps(meta, ensure_ascii=False, sort_keys=True, default=str)))
    db.executemany(
        "INSERT INTO experiments(id,hypothesis,result,status,created_at,metadata)"
        " VALUES (?,?,?,?,?,?)", out)
    return len(out)


def _project_audit(db, rows) -> int:
    out = []
    for r in rows:
        known = {"timestamp", "code_version", "layer", "action", "agent", "actor", "result"}
        meta = {k: v for k, v in r.items() if k not in known}
        out.append((r.get("layer") or r.get("event"),
                    r.get("agent") or r.get("actor") or "system",
                    r.get("action"), r.get("timestamp"),
                    json.dumps(meta, ensure_ascii=False, sort_keys=True, default=str)))
    db.executemany(
        "INSERT INTO audit_events(event,actor,action,timestamp,metadata) VALUES (?,?,?,?,?)", out)
    return len(out)


_SOURCES = [
    ("registry", _registry_path, _project_registry),
    ("fusion_signals", _sig_path, _project_signals),
    ("allocation_proposals", _alloc_path, _project_allocations),
    ("portfolio_decisions", _pdec_path, _project_portfolio_decisions),
    ("experiments", lambda: EXPERIMENTS_PATH, _project_experiments),
    ("audit", _audit_path, _project_audit),
]


def compute_checksum(db: Database) -> str:
    h = hashlib.sha256()
    for table in sorted(_CHECKSUM_COLS):
        cols = _CHECKSUM_COLS[table]
        for row in db.query(f"SELECT {','.join(cols)} FROM {table} ORDER BY rowid"):
            h.update(json.dumps([row[c] for c in cols], sort_keys=True, default=str).encode())
        h.update(b"|")
    return "sha256:" + h.hexdigest()


def source_checksum() -> str:
    """소스 JSONL 원문 해시(순서 고정). status/verify용."""
    h = hashlib.sha256()
    for name, resolver, _ in _SOURCES:
        p = resolver()
        h.update(name.encode())
        if os.path.exists(p):
            with open(p, "rb") as f:
                h.update(f.read())
        h.update(b"|")
    return "sha256:" + h.hexdigest()


def rebuild(db_path: str | None = None, ts: str = "") -> ProjectionReport:
    """프로젝션 재구축. 소스 무변경. 반환: ProjectionReport."""
    db = Database(db_path)
    db.drop_all()
    db.apply_schema()

    rep = ProjectionReport(timestamp=ts)
    for name, resolver, projector in _SOURCES:
        path = resolver()
        rows, failures = _read_jsonl(path)
        written = projector(db, rows)
        rep.sources_processed.append({"name": name, "exists": os.path.exists(path),
                                      "records_read": len(rows),
                                      "records_written": written, "failures": failures})
        rep.records_read += len(rows)
        rep.records_written += written
        rep.failures += failures

    rep.checksum = compute_checksum(db)
    db.set_meta("last_projection", ts)
    db.set_meta("checksum", rep.checksum)
    db.set_meta("source_checksum", source_checksum())
    db.set_meta("records_written", str(rep.records_written))
    db.close()
    return rep


def main(argv=None) -> int:
    import argparse
    from datetime import datetime, timezone
    ap = argparse.ArgumentParser(prog="jarvis.db.projector")
    ap.add_argument("cmd", choices=["rebuild"], nargs="?", default="rebuild")
    ap.parse_args(argv)
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    rep = rebuild(ts=ts)
    print(json.dumps(rep.to_dict(), ensure_ascii=False, indent=2, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
