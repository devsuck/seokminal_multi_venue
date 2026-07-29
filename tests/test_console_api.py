"""Console API 스모크 테스트 — /console/* read-only 엔드포인트 회귀 보호.

각 엔드포인트가 방어적으로 dict를 반환하고(원장 부재에도 크래시 없음) 필수 키를 담는지 확인.
TestClient 대신 함수 직접 호출(전체 app 기동 불필요). fastapi만 있으면 실행.
"""
from __future__ import annotations

import api_server.console_api as c


def test_status_shape():
    s = c.status()
    assert isinstance(s, dict)
    for k in ("system", "autonomy", "boundaries", "strategies", "capital"):
        assert k in s
    assert s["autonomy"]["level"] >= 0
    assert s["strategies"]["total"] >= 0


def test_pipeline_shape():
    p = c.pipeline()
    assert isinstance(p, dict) and isinstance(p["stages"], list)
    assert len(p["stages"]) == 10   # P7.4~P8.7 + readiness
    for st in p["stages"]:
        assert {"key", "label", "count", "by_status"} <= set(st)


def test_regime_has_posture():
    r = c.regime()
    assert isinstance(r, dict) and "regime" in r
    # posture는 실 레지스트리에서 항상 도출(정직한 파생)
    if r.get("posture"):
        assert {"label", "confidence", "total_active", "breakdown"} <= set(r["posture"])


def test_strategies_shape():
    s = c.strategies()
    assert isinstance(s["strategies"], list) and s["total"] >= 0
    assert isinstance(s["by_factor"], dict)
    if s["strategies"]:
        assert {"strategy_id", "status", "factor"} <= set(s["strategies"][0])


def test_validation_shape():
    v = c.validation()
    assert "redteam" in v and "gates" in v
    assert isinstance(v["gates"], list) and "bh_fdr" in v["gates"]


def test_agents_council_tree():
    a = c.agents()
    assert "council" in a
    council = a["council"]
    assert council["role"] == "CIO"
    assert len(council["children"]) == 3   # Research / Risk / Execution
    assert isinstance(a["archetypes"], list)


def test_knowledge_derives_graph():
    k = c.knowledge()
    assert "nodes" in k and "edges" in k
    # 레지스트리 있으면 그래프 도출(전략+팩터 노드)
    if k["nodes"]:
        types = {n["type"] for n in k["nodes"]}
        assert "factor" in types or "strategy" in types


def test_read_only_endpoints_never_crash():
    """모든 엔드포인트가 방어적으로 dict 반환(원장 부재에도)."""
    for fn in (c.status, c.pipeline, c.regime, c.council, c.strategies, c.experiments,
               c.validation, c.agents, c.logs, c.knowledge, c.research, c.market,
               c.allocation, c.positions, c.risk, c.orders, c.broker, c.monitor):
        out = fn()
        assert isinstance(out, dict), f"{fn.__name__} did not return dict"


def test_no_mutation_verbs_in_source():
    """소스에 write/집행 동사 없음(read-only 보증)."""
    import inspect
    src = inspect.getsource(c)
    for banned in ("submit_order", "place_order", "execute(", ".buy(", ".sell(",
                   "append_", "write_", "record("):
        assert banned not in src, f"console_api contains mutation verb: {banned}"
