"""P3 SQLite Projection Layer 테스트.

Projection · Integrity · Query · CLI. 소스 JSONL 무변경 확인 포함.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """jarvis _state 소스를 tmp로, experiments 경로도 tmp로, index.db도 tmp로."""
    state = tmp_path / "_state"
    state.mkdir()

    def sp(name):
        return str(state / name)

    import jarvis.db.projector as pj
    import jarvis.db.sqlite as sq
    monkeypatch.setattr(pj, "state_path", sp)
    monkeypatch.setattr(sq, "state_path", sp)
    exp_path = str(tmp_path / "experiment_registry.jsonl")
    monkeypatch.setattr(pj, "EXPERIMENTS_PATH", exp_path)
    return {"state": state, "sp": sp, "exp": exp_path, "db": sp("index.db")}


def _write(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed(env):
    _write(env["sp"]("registry.jsonl"), [
        {"strategy_id": "S1", "name": "S1", "from": None, "to": "draft", "reason": "reg",
         "config_hash": "h1", "family": "event", "timestamp": "2026-01-01T00:00:00Z"},
        {"strategy_id": "S1", "from": "draft", "to": "backtested", "reason": "bt",
         "config_hash": "h1", "family": "event", "timestamp": "2026-01-02T00:00:00Z"},
        {"strategy_id": "S1", "from": "backtested", "to": "paper_active", "reason": "go",
         "config_hash": "h1", "family": "event", "timestamp": "2026-01-03T00:00:00Z"},
        {"strategy_id": "S2", "from": None, "to": "draft", "reason": "reg",
         "config_hash": "h2", "family": "trend", "timestamp": "2026-01-01T00:00:00Z"},
        {"strategy_id": "S2", "from": "draft", "to": "rejected", "reason": "no",
         "config_hash": "h2", "family": "trend", "timestamp": "2026-01-02T00:00:00Z"},
    ])
    _write(env["sp"]("audit.jsonl"), [
        {"timestamp": "2026-01-01T00:00:00Z", "code_version": "v", "layer": "registry",
         "agent": "pipeline", "action": "transition", "result": "committed", "strategy_id": "S1"},
        {"timestamp": "2026-01-02T00:00:00Z", "code_version": "v", "layer": "permissions",
         "agent": "research_agent", "action": "check", "result": "allowed"},
    ])
    _write(env["exp"], [
        {"timestamp": "2026-01-01T00:00:00Z", "hypothesis_id": "H1", "name": "hyp one",
         "status": "rejected", "diagnosis": "SIGNAL DEAD"},
        {"timestamp": "2026-01-02T00:00:00Z", "hypothesis_id": "H2", "name": "hyp two",
         "status": "candidate", "verdict": "edge"},
    ])
    _write(env["sp"]("fusion_signals.jsonl"), [
        {"instrument": "AAA", "direction": 1, "as_of": "2026-02-01T00:00:00Z",
         "contributions": [{"strategy_id": "S1", "direction": 1, "strength": 1.0},
                           {"strategy_id": "S2", "direction": -1, "strength": 0.5}]},
    ])
    _write(env["sp"]("allocation_proposals.jsonl"), [
        {"method": "v1", "timestamp": "2026-02-01T00:00:00Z",
         "proposals": [{"strategy_id": "S1", "target_weight": 0.7, "risk_contribution": 0.6}]},
    ])
    _write(env["sp"]("portfolio_decisions.jsonl"), [
        {"timestamp": "2026-02-01T00:00:00Z", "decision": "REBALANCE", "reasons": ["drift"],
         "blockers": [], "inputs": {"regime": "bull_low_vol"}, "metadata": {"quality_mode": "normal"}},
    ])


# ─────────────────────── Projection ──────────────────────────
def test_empty_database_rebuild(env):
    from jarvis.db.projector import rebuild
    rep = rebuild(env["db"], ts="T")           # 소스 없음
    assert rep.records_written == 0 and rep.failures == 0
    assert os.path.exists(env["db"])
    assert rep.checksum.startswith("sha256:")


def test_jsonl_to_sqlite_conversion(env):
    from jarvis.db.projector import rebuild
    from jarvis.db.sqlite import Database
    _seed(env)
    rep = rebuild(env["db"], ts="T")
    db = Database(env["db"], read_only=True)
    assert db.count("strategies") == 2          # S1,S2 fold
    assert db.count("strategy_events") == 5
    assert db.count("signals") == 2             # contributions expanded
    assert db.count("allocations") == 1
    assert db.count("portfolio_decisions") == 1
    assert db.count("experiments") == 2
    assert db.count("audit_events") == 2
    # fold 정확성: S1 최종 status
    s1 = db.query("SELECT status,config_hash,created_at,updated_at FROM strategies WHERE id='S1'")[0]
    assert s1["status"] == "paper_active" and s1["config_hash"] == "h1"
    assert s1["created_at"] == "2026-01-01T00:00:00Z" and s1["updated_at"] == "2026-01-03T00:00:00Z"
    db.close()
    assert rep.records_read == 5 + 2 + 1 + 1 + 1 + 2


def test_rebuild_determinism(env):
    from jarvis.db.projector import rebuild
    _seed(env)
    c1 = rebuild(env["db"], ts="T1").checksum
    c2 = rebuild(env["db"], ts="T2").checksum   # 타임스탬프 달라도 데이터 checksum 동일
    assert c1 == c2


def test_duplicate_events_handled(env):
    from jarvis.db.projector import rebuild
    from jarvis.db.sqlite import Database
    # 같은 전략 같은 전이 반복 → strategy_events 별개 event_id로 보존, strategies는 1개
    _write(env["sp"]("registry.jsonl"), [
        {"strategy_id": "D", "from": None, "to": "draft", "timestamp": "2026-01-01T00:00:00Z"},
        {"strategy_id": "D", "from": "draft", "to": "rejected", "timestamp": "2026-01-02T00:00:00Z"},
        {"strategy_id": "D", "from": "draft", "to": "rejected", "timestamp": "2026-01-02T00:00:00Z"},
    ])
    rebuild(env["db"], ts="T")
    db = Database(env["db"], read_only=True)
    assert db.count("strategies") == 1
    assert db.count("strategy_events") == 3     # 중복도 별개 event_id
    db.close()


def test_corrupted_record_handled(env):
    from jarvis.db.projector import rebuild
    from jarvis.db.sqlite import Database
    with open(env["sp"]("registry.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "OK", "to": "draft",
                            "timestamp": "2026-01-01T00:00:00Z"}) + "\n")
        f.write("{ this is not valid json ]\n")   # 손상 라인
        f.write(json.dumps({"strategy_id": "OK", "from": "draft", "to": "backtested",
                            "timestamp": "2026-01-02T00:00:00Z"}) + "\n")
    rep = rebuild(env["db"], ts="T")
    assert rep.failures == 1                     # 손상 1건 집계
    db = Database(env["db"], read_only=True)
    assert db.count("strategy_events") == 2      # 정상 2건만
    db.close()


# ─────────────────────── Integrity ───────────────────────────
def test_delete_and_rebuild_identical(env):
    from jarvis.db.projector import rebuild
    _seed(env)
    c1 = rebuild(env["db"], ts="T1").checksum
    for suffix in ("", "-wal", "-shm"):
        try:
            os.remove(env["db"] + suffix)
        except OSError:
            pass
    assert not os.path.exists(env["db"])
    c2 = rebuild(env["db"], ts="T2").checksum
    assert c1 == c2                              # 삭제 후 재구축 = 동일


def test_jsonl_never_modified(env):
    from jarvis.db.projector import rebuild
    _seed(env)
    sources = ["registry.jsonl", "audit.jsonl", "fusion_signals.jsonl",
               "allocation_proposals.jsonl", "portfolio_decisions.jsonl"]
    before = {s: hashlib.sha256(open(env["sp"](s), "rb").read()).hexdigest() for s in sources}
    before[env["exp"]] = hashlib.sha256(open(env["exp"], "rb").read()).hexdigest()
    rebuild(env["db"], ts="T")
    for s in sources:
        assert hashlib.sha256(open(env["sp"](s), "rb").read()).hexdigest() == before[s]
    assert hashlib.sha256(open(env["exp"], "rb").read()).hexdigest() == before[env["exp"]]


def test_checksums_consistent_and_verify(env):
    from jarvis.db.projector import rebuild
    from jarvis.db.verify import verify
    _seed(env)
    rebuild(env["db"], ts="T")
    res = verify(env["db"])
    assert res["ok"] is True
    assert res["deterministic"] is True and res["counts_match"] is True


# ─────────────────────── Query ───────────────────────────────
def test_query_active_strategies(env):
    from jarvis.db.projector import rebuild
    from jarvis.db import query
    import jarvis.db.query as qmod
    import jarvis.db.sqlite as sq
    monkeypatch_db(env, qmod, sq)
    _seed(env)
    rebuild(env["db"], ts="T")
    active = query.get_active_strategies()
    ids = {a["id"] for a in active}
    assert "S1" in ids and "S2" not in ids       # S1 paper_active, S2 rejected


def test_query_history_and_latest_decision(env):
    from jarvis.db.projector import rebuild
    from jarvis.db import query
    import jarvis.db.query as qmod
    import jarvis.db.sqlite as sq
    monkeypatch_db(env, qmod, sq)
    _seed(env)
    rebuild(env["db"], ts="T")
    hist = query.get_strategy_history("S1")
    assert [h["new_state"] for h in hist] == ["draft", "backtested", "paper_active"]
    dec = query.get_latest_portfolio_decision()
    assert dec["decision"] == "REBALANCE" and dec["regime"] == "bull_low_vol"
    failed = query.get_failed_experiments()
    assert any(e["id"] == "H1" for e in failed)
    sigs = query.get_recent_signals()
    assert len(sigs) == 2


# ─────────────────────── CLI ─────────────────────────────────
def test_cli_rebuild_status_verify(env, capsys):
    import jarvis.db.query as qmod
    import jarvis.db.sqlite as sq
    monkeypatch_db(env, qmod, sq)
    _seed(env)
    from jarvis.db.__main__ import main
    assert main(["rebuild"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["records_written"] > 0
    assert main(["status"]) == 0
    st = json.loads(capsys.readouterr().out)
    assert st["database_exists"] is True and st["table_counts"]["strategies"] == 2
    assert main(["verify"]) == 0                 # ok → exit 0


def monkeypatch_db(env, qmod, sq):
    """query/sqlite의 db_path를 tmp index.db로."""
    import jarvis.db.projector as pj
    # sqlite.db_path()가 state_path("index.db")를 쓰므로 sqlite.state_path만 patch되면 됨.
    # (env fixture가 이미 pj.state_path/sq.state_path를 patch)
    pass
