"""P5 Research Planner 테스트 — 커버리지 최적화기(제안 전용).

deterministic · no JSONL mutation · graph 의존 · 결측 · 랭킹 일관 ·
중복 가설 탐지 · 실패패턴 매핑 · 빈 그래프.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest


@pytest.fixture()
def env(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()

    def sp(name):
        return str(state / name)

    import jarvis.db.projector as pj
    import jarvis.db.sqlite as sq
    import jarvis.knowledge.schema as ks
    monkeypatch.setattr(pj, "state_path", sp)
    monkeypatch.setattr(sq, "state_path", sp)
    monkeypatch.setattr(ks, "state_path", sp)
    exp = str(tmp_path / "experiment_registry.jsonl")
    monkeypatch.setattr(pj, "EXPERIMENTS_PATH", exp)
    return {"sp": sp, "exp": exp, "proj": sp("index.db"), "graph": sp("knowledge.db")}


def _w(path, rows):
    with open(path, "w") as f:
        for r in rows:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def _seed(env):
    # 여러 momentum/trend 계열 전략 전멸 + 실패사유 SIGNAL_DEAD/COST 다수
    reg = []
    for sid in ["orb_rvol_vwap", "vwap_mean_reversion", "gap_continuation", "atr_compression",
                "tsmom_breakout_v1", "mom_reversal_v1"]:
        reg.append({"strategy_id": sid, "to": "draft", "timestamp": "2026-01-01T00:00:00Z"})
        reg.append({"strategy_id": sid, "from": "draft", "to": "rejected",
                    "timestamp": "2026-01-02T00:00:00Z"})
    reg.append({"strategy_id": "kr_buyback", "to": "draft", "timestamp": "2026-01-01T00:00:00Z"})
    reg.append({"strategy_id": "kr_buyback", "from": "draft", "to": "paper_active",
                "timestamp": "2026-01-03T00:00:00Z"})
    reg.append({"strategy_id": "cb_bw_blocked", "to": "blocked_by_data",
                "timestamp": "2026-01-01T00:00:00Z"})
    _w(env["sp"]("registry.jsonl"), reg)

    exp = []
    for sid, diag in [("orb_rvol_vwap", "SIGNAL DEAD"), ("vwap_mean_reversion", "COST/EXECUTION"),
                      ("gap_continuation", "COST/EXECUTION"), ("tsmom_breakout_v1", "SIGNAL DEAD"),
                      ("mom_reversal_v1", "indistinguishable_from_random")]:
        # 각 가설 3회 재검 후 실패(반복 실패 방향)
        for i in range(3):
            exp.append({"timestamp": f"2026-01-0{i+1}T00:00:00Z", "hypothesis_id": sid,
                        "name": sid, "status": "rejected", "diagnosis": diag,
                        "data_source": "yfinance", "universe": "us"})
    _w(env["exp"], exp)
    _w(env["sp"]("audit.jsonl"), [])


def _build_sources(env):
    from jarvis.db.projector import rebuild as p3
    from jarvis.knowledge.builder import build as kg
    p3(env["proj"], ts="T")
    kg(env["graph"], projection_db=env["proj"], ts="T")


def _run(env, ts="T"):
    from jarvis.planner.planner import run_planner
    return run_planner(projection_db=env["proj"], graph_db=env["graph"], ts=ts)


# ─────────────── 기본 ───────────────
def test_produces_ranked_proposals(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    assert rep.n_proposals > 0
    # 랭킹: priority 내림차순
    scores = [p["priority_score"] for p in rep.proposals]
    assert scores == sorted(scores, reverse=True)
    cats = {p["category"] for p in rep.proposals}
    assert cats <= {"MISSING_REGIME", "MISSING_STRATEGY_FAMILY", "REPLACE_FAILED_STRATEGY",
                    "REDUCE_REDUNDANCY", "DATA_GAP", "KNOWLEDGE_GAP"}


def test_failure_pattern_mapping(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    # SIGNAL_DEAD 실패 → 대체 신호군 제안(MISSING_STRATEGY_FAMILY / signal_generation)
    sig = [p for p in rep.proposals if p["target_area"] == "signal_generation"]
    assert sig, "SIGNAL_DEAD → alternative signal family 제안이 있어야"
    assert any("signal" in r.lower() for r in sig[0]["rationale"])
    # COST_EXECUTION → turnover reduction
    assert any(p["target_area"] == "turnover_reduction" for p in rep.proposals)


def test_replace_failed_family(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    # 전멸한 패밀리 → REPLACE_FAILED_STRATEGY
    assert any(p["category"] == "REPLACE_FAILED_STRATEGY" for p in rep.proposals)


def test_data_gap_detected(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    dg = [p for p in rep.proposals if p["category"] == "DATA_GAP"]
    assert dg and any("blocked" in r.lower() for p in dg for r in p["rationale"])


def test_duplicate_hypothesis_detection(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    # 3회 재검+실패 가설 → REDUCE_REDUNDANCY
    red = [p for p in rep.proposals if p["category"] == "REDUCE_REDUNDANCY"]
    assert red


def test_missing_family_detected(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    # carry/microstructure 등 정규 패밀리 미존재 → MISSING_STRATEGY_FAMILY
    mf = [p for p in rep.proposals if p["category"] == "MISSING_STRATEGY_FAMILY"]
    areas = {p["target_area"] for p in mf}
    assert "carry" in areas or "microstructure" in areas


# ─────────────── 결정성/무결성 ───────────────
def test_deterministic_output(env):
    _seed(env)
    _build_sources(env)
    assert _run(env, "T1").checksum == _run(env, "T2").checksum   # ts 달라도 동일


def test_verify_deterministic(env):
    _seed(env)
    _build_sources(env)
    from jarvis.planner.verify import verify
    res = verify(projection_db=env["proj"], graph_db=env["graph"])
    assert res["ok"] is True and res["deterministic"] is True


def test_no_jsonl_mutation(env):
    _seed(env)
    _build_sources(env)
    srcs = [env["sp"]("registry.jsonl"), env["exp"], env["sp"]("audit.jsonl")]
    before = {s: hashlib.sha256(open(s, "rb").read()).hexdigest() for s in srcs}
    _run(env)
    for s in srcs:
        assert hashlib.sha256(open(s, "rb").read()).hexdigest() == before[s]


def test_ranking_consistency(env):
    _seed(env)
    _build_sources(env)
    rep = _run(env)
    # 동일 proposal_id 중복 없음
    ids = [p["proposal_id"] for p in rep.proposals]
    assert len(ids) == len(set(ids))


# ─────────────── 엣지 케이스 ───────────────
def test_empty_graph_behavior(env):
    # 빈 소스 → 빈 그래프 → 제안 0(크래시 없음)
    _w(env["sp"]("registry.jsonl"), [])
    _w(env["exp"], [])
    _w(env["sp"]("audit.jsonl"), [])
    _build_sources(env)
    rep = _run(env)
    assert rep.n_proposals == 0 and rep.proposals == []


def test_missing_graph_rebuilds(env):
    # graph_db=None → 내부에서 projection+graph 재구축(자체 완결)
    _seed(env)
    from jarvis.db.projector import rebuild as p3
    p3(env["proj"], ts="T")
    from jarvis.planner.planner import run_planner
    rep = run_planner(projection_db=env["proj"], graph_db=None, ts="T")  # graph 자동 빌드
    assert rep.n_proposals > 0


# ─────────────── 원장 권한/감사 ───────────────
def test_ledger_write_requires_permission_and_audits(env, monkeypatch):
    _seed(env)
    _build_sources(env)
    import jarvis.audit.log as al
    import jarvis.planner.planner as pp
    monkeypatch.setattr(al, "state_path", env["sp"])
    monkeypatch.setattr("jarvis.config.state_path", env["sp"])
    rep = _run(env)
    out = pp.write_proposals(rep)
    assert out["written"] is True
    rows = pp.read_all()
    assert len(rows) == 1 and rows[0]["executed"] is False and rows[0]["kind"] == "proposal_only"
    audit = al.read_all()
    assert any(a.get("action") == "write_planner_proposal" and a.get("result") == "allowed"
               for a in audit)
