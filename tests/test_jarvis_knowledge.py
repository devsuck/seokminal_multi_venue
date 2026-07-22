"""P4 Knowledge Graph 테스트.

deterministic rebuild · no JSONL mutation · checksum · duplicate · missing refs ·
query correctness · relationship consistency.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    """tmp _state 소스 + tmp projection + tmp graph.db."""
    state = tmp_path / "_state"
    state.mkdir()

    def sp(name):
        return str(state / name)

    import jarvis.db.projector as pj
    import jarvis.db.sqlite as sq
    import jarvis.knowledge.schema as ks
    monkeypatch.setattr(pj, "state_path", sp)
    monkeypatch.setattr(sq, "state_path", sp)
    monkeypatch.setattr(ks, "state_path", sp)   # graph_db_path → tmp
    exp = str(tmp_path / "experiment_registry.jsonl")
    monkeypatch.setattr(pj, "EXPERIMENTS_PATH", exp)
    return {"sp": sp, "exp": exp, "proj": sp("index.db"), "graph": sp("knowledge.db")}


def _w(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed(env):
    _w(env["sp"]("registry.jsonl"), [
        {"strategy_id": "orb_rvol_vwap", "to": "draft", "timestamp": "2026-01-01T00:00:00Z"},
        {"strategy_id": "orb_rvol_vwap", "from": "draft", "to": "rejected",
         "timestamp": "2026-01-02T00:00:00Z", "config_hash": "h1"},
        {"strategy_id": "kr_buyback", "to": "draft", "timestamp": "2026-01-01T00:00:00Z"},
        {"strategy_id": "kr_buyback", "from": "draft", "to": "paper_active",
         "timestamp": "2026-01-03T00:00:00Z", "config_hash": "h2"},
    ])
    _w(env["exp"], [
        {"timestamp": "2026-01-02T00:00:00Z", "hypothesis_id": "orb_rvol_vwap",
         "name": "ORB", "status": "rejected", "diagnosis": "SIGNAL DEAD",
         "data_source": "yfinance", "universe": "us_large", "net": -5401, "sharpe": -0.3},
        {"timestamp": "2026-01-01T00:00:00Z", "hypothesis_id": "orb_rvol_vwap",
         "name": "ORB", "status": "rejected", "diagnosis": "COST/EXECUTION"},  # 재실행
        {"timestamp": "2026-01-03T00:00:00Z", "hypothesis_id": "kr_buyback",
         "name": "buyback", "status": "paper_candidate", "data_source": "krx",
         "net": 173, "sharpe": 0.5, "random_percentile": 97},
    ])
    _w(env["sp"]("audit.jsonl"), [])


def _build(env):
    from jarvis.db.projector import rebuild as p3
    from jarvis.knowledge.builder import build
    p3(env["proj"], ts="T")
    return build(env["graph"], projection_db=env["proj"], ts="T")


# ─────────────── Projection/build ───────────────
def test_build_creates_nodes_and_edges(env):
    _seed(env)
    rep = _build(env)
    assert rep.node_count > 0 and rep.edge_count > 0
    # 엔티티: Strategy 2, Experiment 2(id별), Hypothesis 2, FailureReason(SIGNAL_DEAD,COST_EXECUTION),
    # Dataset(yfinance,us_large,krx), Metric(net,sharpe,random_percentile)
    assert rep.nodes_by_type["Strategy"] == 2
    assert rep.nodes_by_type["Experiment"] == 2
    assert rep.nodes_by_type["Hypothesis"] == 2
    assert "FailureReason" in rep.nodes_by_type and "Dataset" in rep.nodes_by_type
    # derived_from: 두 전략 모두 동명 experiment 존재
    assert rep.edges_by_relation["derived_from"] == 2
    assert rep.edges_by_relation["tested"] == 2
    assert rep.edges_by_relation["failed_because"] >= 1
    assert rep.edges_by_relation["used"] >= 1


def test_deterministic_rebuild(env):
    _seed(env)
    c1 = _build(env).checksum
    c2 = _build(env).checksum
    assert c1 == c2


def test_delete_and_rebuild_identical(env):
    _seed(env)
    c1 = _build(env).checksum
    for sfx in ("", "-wal", "-shm"):
        try:
            os.remove(env["graph"] + sfx)
        except OSError:
            pass
    assert not os.path.exists(env["graph"])
    c2 = _build(env).checksum
    assert c1 == c2


def test_no_jsonl_mutation(env):
    _seed(env)
    srcs = [env["sp"]("registry.jsonl"), env["exp"], env["sp"]("audit.jsonl")]
    before = {s: hashlib.sha256(open(s, "rb").read()).hexdigest() for s in srcs}
    _build(env)
    for s in srcs:
        assert hashlib.sha256(open(s, "rb").read()).hexdigest() == before[s]


def test_duplicate_experiment_runs_aggregated(env):
    _seed(env)
    _build(env)
    from jarvis.db.sqlite import Database
    g = Database(env["graph"], read_only=True)
    # orb_rvol_vwap 2회 실행 → Experiment 노드 1개, n_runs=2
    exp = g.query("SELECT metadata FROM nodes WHERE id='Experiment:orb_rvol_vwap'")[0]
    assert json.loads(exp["metadata"])["n_runs"] == 2
    g.close()


def test_missing_references_tolerated(env):
    # experiment 없이 strategy만 → derived_from 엣지 skip(크래시 없음)
    _w(env["sp"]("registry.jsonl"),
       [{"strategy_id": "lonely", "to": "draft", "timestamp": "2026-01-01T00:00:00Z"}])
    _w(env["exp"], [])
    _w(env["sp"]("audit.jsonl"), [])
    rep = _build(env)
    assert rep.nodes_by_type.get("Strategy") == 1
    assert rep.edges_by_relation.get("derived_from", 0) == 0   # 대응 experiment 없음


def test_corrupted_metadata_safe(env):
    _w(env["sp"]("registry.jsonl"),
       [{"strategy_id": "s", "to": "rejected", "timestamp": "2026-01-01T00:00:00Z"}])
    _w(env["exp"], [{"timestamp": "2026-01-01T00:00:00Z", "hypothesis_id": "s",
                     "status": "rejected", "diagnosis": "SIGNAL DEAD"}])
    _w(env["sp"]("audit.jsonl"), [])
    # projection 후 experiments.metadata를 손상시켜도 그래프 빌드가 안전해야
    from jarvis.db.projector import rebuild as p3
    p3(env["proj"], ts="T")
    from jarvis.db.sqlite import Database
    d = Database(env["proj"])
    d.execute("UPDATE experiments SET metadata='{bad json' WHERE id='s'")
    d.close()
    from jarvis.knowledge.builder import build
    rep = build(env["graph"], projection_db=env["proj"], ts="T")   # 크래시 없이 빌드
    assert rep.node_count > 0


# ─────────────── Query correctness ───────────────
def test_query_failed_strategies(env, monkeypatch):
    _seed(env)
    _build(env)
    _point_query_at(env, monkeypatch)
    from jarvis.knowledge import query as q
    failed = q.find_failed_strategies()
    names = {f["strategy"] for f in failed}
    assert "orb_rvol_vwap" in names       # status rejected + failed_because
    assert "kr_buyback" not in names       # paper_active


def test_query_lineage_and_failure_patterns(env, monkeypatch):
    _seed(env)
    _build(env)
    _point_query_at(env, monkeypatch)
    from jarvis.knowledge import query as q
    lin = q.strategy_lineage("orb_rvol_vwap")
    assert lin["experiments"][0]["experiment"] == "orb_rvol_vwap"
    assert "SIGNAL_DEAD" in lin["experiments"][0]["failed_because"] or \
           "COST_EXECUTION" in lin["experiments"][0]["failed_because"]
    patt = q.failure_pattern_summary()
    assert sum(patt.values()) >= 1
    rel = q.find_related_experiments("kr_buyback")
    assert rel and rel[0]["experiment"] == "kr_buyback"


def test_relationship_consistency(env, monkeypatch):
    """모든 엣지의 끝점이 실제 노드여야(dangling 없음)."""
    _seed(env)
    _build(env)
    from jarvis.db.sqlite import Database
    g = Database(env["graph"], read_only=True)
    dangling = g.query("""SELECT COUNT(*) n FROM edges e
        WHERE e.source_id NOT IN (SELECT id FROM nodes)
           OR e.target_id NOT IN (SELECT id FROM nodes)""")[0]["n"]
    g.close()
    assert dangling == 0


# ─────────────── CLI ───────────────
def test_cli_rebuild_verify(env, monkeypatch, capsys):
    _seed(env)
    from jarvis.db.projector import rebuild as p3
    p3(env["proj"], ts="T")
    _point_query_at(env, monkeypatch)
    # graph_db_path는 이미 tmp; projection_db는 CLI 내부에서 재구축되므로 소스경로 patch로 충분
    from jarvis.knowledge.__main__ import main
    assert main(["rebuild"]) == 0
    rep = json.loads(capsys.readouterr().out)
    assert rep["node_count"] > 0
    assert main(["verify"]) == 0
    v = json.loads(capsys.readouterr().out)
    assert v["deterministic"] is True


def _point_query_at(env, monkeypatch):
    """query 모듈의 graph_db_path가 tmp graph를 보도록(schema.state_path 이미 patch됨)."""
    # jarvis.knowledge.query는 schema.graph_db_path 사용 → schema.state_path patch로 이미 tmp.
    pass
