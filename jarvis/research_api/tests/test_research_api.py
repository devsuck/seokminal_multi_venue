"""P10.29 Research Intelligence API Backend 테스트. **대시보드·AI 에이전트용 조회 백엔드 — 읽기 전용.**

레지스트리 등록(스키마/쿼리/뷰/엔드포인트·불변)·부트스트랩·7 조회 함수(system_status/timeline/lineage/alpha/
risk/agent/governance·결정적·스키마 일관)·접근 감사 로그(append-only·불변)·권한 경계(GET·read_only·금지 동사
거부)·verify(체인/변조/중복/스키마/권한)·replay·상위 READ ONLY 보호·CLI·보안(금지import·POST/trade/order/deploy
엔드포인트 없음·상위 원장 무변경·삭제 API 없음·불변·READ≠WRITE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_api import ledger
from jarvis.research_api import models as M
from jarvis.research_api.engine import ResearchAPIEngine
from jarvis.research_api.models import (
    ENDPOINT_SCHEMAS,
    ForbiddenEndpoint,
    ImmutableEndpointError,
    ImmutableSchemaError,
    ImmutableViewError,
    InvalidEndpointMethod,
    UnknownEndpointError,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_api.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchAPIEngine()


def _seed(sp, filename, rows):
    """상위 소스 원장 시드(엔진은 절대 쓰지 않는다)."""
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


# ══════════════ register_schema ══════════════
def test_schema_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_schema("get_alpha_summary", "/api/v1/alpha", ["insight_count"], "v1", T0,
                               commit=True)
    assert s.schema_id.startswith("RAS:")
    assert s.fields == ["insight_count"]


def test_schema_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_schema("x", "/p", ["a"], now=T0, commit=False)
    b = _eng().register_schema("x", "/p", ["a"], now=T1, commit=False)
    assert a.schema_id == b.schema_id


def test_schema_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_schema("x", "/p", ["a"], now=T0, commit=True)
    e.register_schema("x", "/p", ["a"], now=T1, commit=True)
    assert len(ledger.read_schemas()) == 1


def test_schema_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_schema("x", "/p", ["a"], now=T0, commit=True)
    with pytest.raises(ImmutableSchemaError):
        e.register_schema("x", "/p", ["a", "b"], now=T1, commit=True)


def test_schema_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_schema("x", "/p", ["a"], now=T0, commit=False)
    assert ledger.read_schemas() == []


# ══════════════ register_query ══════════════
def test_query_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    q = _eng().register_query("alpha:ki", "knowledge_intelligence", "read ki", T0, commit=True)
    assert q.query_id.startswith("RAQ:")
    assert q.source_layer == "knowledge_intelligence"


def test_query_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_query("q", "layerA", now=T0, commit=True)
    with pytest.raises(M.ImmutableQueryError):
        e.register_query("q", "layerB", now=T1, commit=True)


def test_query_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_query("q", "layerA", now=T0, commit=True)
    e.register_query("q", "layerA", now=T1, commit=True)
    assert len(ledger.read_queries()) == 1


# ══════════════ register_view ══════════════
def test_view_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    v = _eng().register_view("v", "/p", ["col1", "col2"], "on_read", T0, commit=True)
    assert v.view_id.startswith("RAV:")
    assert v.columns == ["col1", "col2"]


def test_view_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_view("v", "/p", ["a"], now=T0, commit=True)
    with pytest.raises(ImmutableViewError):
        e.register_view("v", "/p", ["a", "b"], now=T1, commit=True)


# ══════════════ register_endpoint (권한 경계) ══════════════
def test_endpoint_register_get(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ep = _eng().register_endpoint("/api/v1/x", "get_x", ["layerA"], "GET", "", T0, commit=True)
    assert ep.endpoint_id.startswith("RAE:")
    assert ep.method == "GET"
    assert ep.read_only is True


def test_endpoint_rejects_post(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidEndpointMethod):
        _eng().register_endpoint("/api/v1/x", "get_x", ["layerA"], "POST", "", T0, commit=True)


def test_endpoint_rejects_put_delete_patch(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for m in ("PUT", "DELETE", "PATCH"):
        with pytest.raises(InvalidEndpointMethod):
            e.register_endpoint("/api/v1/x", "get_x", ["l"], m, "", T0, commit=True)


def test_endpoint_rejects_execute_verb(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ForbiddenEndpoint):
        _eng().register_endpoint("/api/v1/execute", "run", ["l"], "GET", "", T0, commit=True)


def test_endpoint_rejects_trade_order_deploy(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for path in ("/api/v1/trade", "/api/v1/order/new", "/api/v1/deploy", "/api/v1/allocate"):
        with pytest.raises(ForbiddenEndpoint):
            e.register_endpoint(path, "handler", ["l"], "GET", "", T0, commit=True)


def test_endpoint_rejects_forbidden_verb_in_function(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ForbiddenEndpoint):
        _eng().register_endpoint("/api/v1/x", "place_order", ["l"], "GET", "", T0, commit=True)


def test_endpoint_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_endpoint("/api/v1/x", "get_x", ["l"], "GET", "", T0, commit=True)
    with pytest.raises(ImmutableEndpointError):
        e.register_endpoint("/api/v1/x", "get_y", ["l"], "GET", "", T1, commit=True)


def test_is_forbidden_path_fn():
    assert M.is_forbidden_path("/api/v1/trade") is True
    assert M.is_forbidden_path("/api/v1/status") is False
    assert M.is_forbidden_path("/api/v1/x", "execute_now") is True


# ══════════════ bootstrap ══════════════
def test_bootstrap_registers_all(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().bootstrap(T0, commit=True)
    assert res["endpoints"] == len(M.ENDPOINT_META)
    assert res["schemas"] == len(M.ENDPOINT_META)
    assert len(ledger.read_endpoints()) == len(M.ENDPOINT_META)


def test_bootstrap_all_get_read_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().bootstrap(T0, commit=True)
    for e in ledger.read_endpoints():
        assert e["method"] == "GET"
        assert e["read_only"] is True


def test_bootstrap_no_forbidden_paths(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().bootstrap(T0, commit=True)
    for e in ledger.read_endpoints():
        assert not M.is_forbidden_path(e["path"], e["function"])


def test_bootstrap_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    e.bootstrap(T1, commit=True)
    assert len(ledger.read_endpoints()) == len(M.ENDPOINT_META)


def test_bootstrap_seven_endpoints():
    assert len(M.ENDPOINT_META) == 7


# ══════════════ get_system_status ══════════════
def test_system_status_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_system_status(T0, commit=True)
    assert r.endpoint == "get_system_status"
    assert r.read_only is True
    assert r.data["health_level"] == "UNKNOWN"
    assert set(r.data.keys()) == set(ENDPOINT_SCHEMAS["get_system_status"])


def test_system_status_from_control_plane(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_overview.jsonl", [{"component_count": 27, "active_component_count": 5,
                                      "dependency_count": 3, "health_level": "DEGRADED",
                                      "overall_score": 0.7, "category_distribution": {"RESEARCH": 9},
                                      "snapshot_at": T0}])
    _seed(sp, "rcp_health.jsonl", [{"level": "DEGRADED", "overall_score": 0.7}])
    r = _eng().get_system_status(T1, commit=True)
    assert r.data["component_count"] == 27
    assert r.data["health_level"] == "DEGRADED"
    assert r.data["overall_score"] == 0.7


def test_system_status_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_overview.jsonl", [{"component_count": 3, "snapshot_at": T0}])
    a = _eng().get_system_status(T1, commit=False)
    b = _eng().get_system_status(T2, commit=False)
    assert a.result_hash == b.result_hash  # 시각 달라도 데이터 동일


# ══════════════ get_research_timeline ══════════════
def test_timeline_merges_sources(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_timeline.jsonl", [{"kind": "HEALTH_COMPUTED", "reference": "h1",
                                      "occurred_at": T0}])
    _seed(sp, "rl_events.jsonl", [{"event_id": "ev1", "event_type": "IDEA", "created_at": T1}])
    r = _eng().get_research_timeline(0, T2, commit=True)
    assert r.data["event_count"] == 2
    sources = {e["source"] for e in r.data["events"]}
    assert sources == {"control_plane", "lifecycle"}


def test_timeline_sorted(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_timeline.jsonl", [{"kind": "B", "reference": "b", "occurred_at": T2},
                                     {"kind": "A", "reference": "a", "occurred_at": T0}])
    r = _eng().get_research_timeline(0, T1, commit=False)
    ats = [e["at"] for e in r.data["events"]]
    assert ats == sorted(ats)


def test_timeline_limit_truncates(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_timeline.jsonl", [{"kind": f"K{i}", "reference": str(i),
                                      "occurred_at": f"2026-07-24T00:0{i}:00Z"} for i in range(5)])
    r = _eng().get_research_timeline(2, T1, commit=False)
    assert r.data["truncated"] is True
    assert r.data["event_count"] == 5
    assert len(r.data["events"]) == 2


# ══════════════ get_strategy_lineage ══════════════
def test_lineage_from_transitions(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rl_transitions.jsonl", [
        {"subject": "stratX", "from_stage": "IDEA", "to_stage": "HYPOTHESIS", "created_at": T0},
        {"subject": "stratX", "from_stage": "HYPOTHESIS", "to_stage": "EXPERIMENT",
         "created_at": T1}])
    r = _eng().get_strategy_lineage("stratX", T2, commit=True)
    assert r.data["stage_count"] == 2
    assert r.data["stages"][0]["to"] == "HYPOTHESIS"


def test_lineage_filters_strategy(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rl_transitions.jsonl", [
        {"subject": "stratX", "from_stage": "A", "to_stage": "B", "created_at": T0},
        {"subject": "stratY", "from_stage": "A", "to_stage": "B", "created_at": T0}])
    r = _eng().get_strategy_lineage("stratX", T1, commit=False)
    assert r.data["stage_count"] == 1


def test_lineage_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_strategy_lineage("none", T0, commit=False)
    assert r.data["stage_count"] == 0
    assert r.data["strategy"] == "none"


# ══════════════ get_alpha_summary ══════════════
def test_alpha_summary(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ki_insights.jsonl", [{"insight_id": "i1", "insight_type": "RECOMMENDATION"},
                                    {"insight_id": "i2", "insight_type": "PATTERN"}])
    _seed(sp, "ki_patterns.jsonl", [{"pattern_id": "p1"}])
    _seed(sp, "ki_clusters.jsonl", [{"cluster_id": "c1"}, {"cluster_id": "c2"}])
    r = _eng().get_alpha_summary(T0, commit=True)
    assert r.data["insight_count"] == 2
    assert r.data["recommendation_count"] == 1
    assert r.data["pattern_count"] == 1
    assert r.data["cluster_count"] == 2


def test_alpha_summary_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_alpha_summary(T0, commit=False)
    assert r.data["insight_count"] == 0
    assert set(r.data.keys()) == set(ENDPOINT_SCHEMAS["get_alpha_summary"])


# ══════════════ get_risk_summary ══════════════
def test_risk_summary(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rr_assessments.jsonl", [{"assessment_id": "a1", "result": "WARNING"},
                                       {"assessment_id": "a2", "result": "PASS"},
                                       {"assessment_id": "a3", "result": "WARNING"}])
    _seed(sp, "rr_factors.jsonl", [{"factor_id": "f1"}])
    r = _eng().get_risk_summary(T0, commit=True)
    assert r.data["assessment_count"] == 3
    assert r.data["result_distribution"]["WARNING"] == 2
    assert r.data["factor_count"] == 1


# ══════════════ get_agent_summary ══════════════
def test_agent_summary(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "sa_audits.jsonl", [{"audit_id": "au1", "result": "PASS"},
                                  {"audit_id": "au2", "result": "CRITICAL"}])
    _seed(sp, "sa_checks.jsonl", [{"check_id": "c1"}])
    _seed(sp, "sa_violations.jsonl", [{"violation_id": "v1"}, {"violation_id": "v2"}])
    r = _eng().get_agent_summary(T0, commit=True)
    assert r.data["audit_count"] == 2
    assert r.data["check_count"] == 1
    assert r.data["violation_count"] == 2
    assert r.data["result_distribution"]["PASS"] == 1


# ══════════════ get_governance_report ══════════════
def test_governance_report(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "go_layers.jsonl", [{"event_id": "l1"}, {"event_id": "l2"}])
    _seed(sp, "go_reports.jsonl", [{"report_id": "r1"}])
    _seed(sp, "go_conflicts.jsonl", [{"conflict_id": "cf1"}])
    _seed(sp, "go_health.jsonl", [{"health_id": "h1", "level": "HEALTHY"}])
    r = _eng().get_governance_report(T0, commit=True)
    assert r.data["layer_count"] == 2
    assert r.data["report_count"] == 1
    assert r.data["conflict_count"] == 1
    assert r.data["health_level"] == "HEALTHY"


# ══════════════ 스키마 일관성 (모든 함수) ══════════════
@pytest.mark.parametrize("fn,params", [
    ("get_system_status", {}), ("get_research_timeline", {"limit": 0}),
    ("get_strategy_lineage", {"strategy": "x"}), ("get_alpha_summary", {}),
    ("get_risk_summary", {}), ("get_agent_summary", {}), ("get_governance_report", {})])
def test_response_keys_match_schema(tmp_path, monkeypatch, fn, params):
    _iso(tmp_path, monkeypatch)
    r = _eng().call(fn, params, T0, commit=False)
    assert set(r.data.keys()) == set(ENDPOINT_SCHEMAS[fn])
    assert r.schema_id.startswith("RAS:")
    assert r.read_only is True


@pytest.mark.parametrize("fn,params", [
    ("get_system_status", {}), ("get_alpha_summary", {}), ("get_risk_summary", {}),
    ("get_agent_summary", {}), ("get_governance_report", {})])
def test_response_deterministic_result_hash(tmp_path, monkeypatch, fn, params):
    _iso(tmp_path, monkeypatch)
    a = _eng().call(fn, params, T0, commit=False)
    b = _eng().call(fn, params, T1, commit=False)
    assert a.result_hash == b.result_hash


# ══════════════ 접근 감사 로그 ══════════════
def test_access_logged_on_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().get_system_status(T0, commit=True)
    logs = ledger.read_access()
    assert len(logs) == 1
    assert logs[0]["endpoint"] == "get_system_status"
    assert logs[0]["method"] == "GET"
    assert logs[0]["read_only"] is True


def test_access_not_logged_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().get_system_status(T0, commit=False)
    assert ledger.read_access() == []


def test_access_records_result_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_alpha_summary(T0, commit=True)
    assert ledger.read_access()[0]["result_hash"] == r.result_hash


def test_access_idempotent_same_call(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.get_system_status(T0, commit=True)
    e.get_system_status(T0, commit=True)  # 동일 endpoint+params+time → 동일 id
    assert len(ledger.read_access()) == 1


def test_access_distinct_across_endpoints(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.get_system_status(T0, commit=True)
    e.get_alpha_summary(T0, commit=True)
    assert len(ledger.read_access()) == 2


def test_access_log_query_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.get_system_status(T0, commit=True)
    e.get_alpha_summary(T0, commit=True)
    assert len(e.access_log("get_alpha_summary")) == 1


# ══════════════ call dispatch ══════════════
def test_call_unknown_endpoint(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEndpointError):
        _eng().call("get_secret", {}, T0)


def test_call_all_functions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for fn in e._FUNCTIONS:
        params = {"strategy": "x"} if fn == "get_strategy_lineage" else {}
        r = e.call(fn, params, T0, commit=False)
        assert r.endpoint == fn


# ══════════════ verify / replay ══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_after_bootstrap_and_calls(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api.verify import verify_chain
    e = _eng()
    e.bootstrap(T0, commit=True)
    e.get_system_status(T1, commit=True)
    e.get_alpha_summary(T1, commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    p = sp("rapi_endpoints.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["path"] = "/api/v1/hacked"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_api.verify import verify_chain
    assert verify_chain()["ok"] is False


def test_verify_schema_consistency(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api.verify import schema_consistency
    e = _eng()
    e.bootstrap(T0, commit=True)
    assert schema_consistency()["ok"] is True


def test_verify_permission_boundary_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api.verify import permission_boundary
    e = _eng()
    e.bootstrap(T0, commit=True)
    assert permission_boundary()["ok"] is True


def test_verify_permission_boundary_detects_bad_endpoint(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_endpoint("/api/v1/x", "get_x", ["l"], "GET", "", T0, commit=True)
    # 원장에 직접 위조 삽입(POST) — 권한 경계가 잡아야 함
    p = sp("rapi_endpoints.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["method"] = "POST"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_api.verify import permission_boundary
    assert permission_boundary()["ok"] is False


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api.verify import replay
    e = _eng()
    e.bootstrap(T0, commit=True)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    e.get_system_status(T1, commit=True)
    s = e.summary(T2)
    assert s.endpoint_count == len(M.ENDPOINT_META)
    assert s.schema_count == len(M.ENDPOINT_META)
    assert s.access_count == 1


# ══════════════ 상위 READ ONLY 보호 ══════════════
def test_source_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ki_insights.jsonl", [{"insight_id": "i1", "insight_type": "PATTERN"}])
    before = open(sp("ki_insights.jsonl")).read()
    e = _eng()
    e.get_alpha_summary(T0, commit=True)
    e.get_system_status(T0, commit=True)
    assert open(sp("ki_insights.jsonl")).read() == before


def test_only_rapi_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    for fn in ("get_system_status", "get_alpha_summary", "get_risk_summary", "get_agent_summary",
               "get_governance_report"):
        e.call(fn, {}, T1, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rapi_"), fn


def test_no_source_file_created(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _eng().get_governance_report(T0, commit=True)  # sources missing
    assert not os.path.exists(sp("go_layers.jsonl"))


# ══════════════ 보안 / 불변식 ══════════════
def test_no_forbidden_imports():
    import ast
    forbidden = ("execution", "broker", "order", "portfolio_execution", "capital_allocation",
                 "live_trading", "permission", "risk_controller")
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "ledger.py", "models.py", "verify.py", "__main__.py", "__init__.py"):
        tree = ast.parse(open(os.path.join(base, fn)).read())
        for n in ast.walk(tree):
            mods = []
            if isinstance(n, ast.Import):
                mods = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom):
                mods = [n.module or ""]
            for m in mods:
                for fb in forbidden:
                    assert not (m == f"jarvis.{fb}" or m.startswith(f"jarvis.{fb}.")), (fn, m)


def test_engine_has_no_execution_methods():
    e = ResearchAPIEngine()
    for bad in ("execute", "trade", "place_order", "submit_order", "allocate", "deploy",
                "post", "create_order", "activate", "liquidate", "rebalance"):
        assert not hasattr(e, bad), bad


def test_engine_has_required_functions():
    e = ResearchAPIEngine()
    for name in ("get_system_status", "get_research_timeline", "get_strategy_lineage",
                 "get_alpha_summary", "get_risk_summary", "get_agent_summary",
                 "get_governance_report"):
        assert hasattr(e, name), name


def test_no_delete_or_update_ledger_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_no_post_execution_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py", "__main__.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def execute", "def trade", "def place_order", "def submit_order",
                    "def deploy_"):
            assert bad not in src, (fn, bad)


def test_all_forbidden_methods_defined():
    assert set(M.FORBIDDEN_METHODS) == {"POST", "PUT", "PATCH", "DELETE"}
    assert M.ALLOWED_METHODS == ("GET",)


def test_records_frozen():
    r = M.APIResponse(endpoint="x", schema_id="RAS:x", read_only=True, data={}, result_hash="h",
                      disclaimer="d", generated_at=T0)
    with pytest.raises(Exception):
        r.endpoint = "y"  # type: ignore


def test_disclaimer_marks_read_only():
    from jarvis.research_api.engine import _DISCLAIMER
    assert "API ≠ TRADE" in _DISCLAIMER and "QUERY ≠ EXECUTE" in _DISCLAIMER


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.schema_id("x")[:4], M.query_id("x")[:4], M.view_id("x")[:4],
           M.endpoint_id("x")[:4], M.access_id("x", "p", T0)[:4]}
    assert len(ids) == 5


def test_five_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 5
    assert all(f.startswith("rapi_") for f in fns)


def test_source_catalog_covers_p23_to_p28():
    assert set(ledger.SOURCE_LEDGERS) == {
        "governance_orchestration", "self_audit_intelligence", "research_risk_intelligence",
        "research_lifecycle", "knowledge_intelligence", "research_control_plane"}


def test_seven_endpoint_schemas():
    assert len(ENDPOINT_SCHEMAS) == 7
    assert set(ENDPOINT_SCHEMAS) == {f for f, _, _ in M.ENDPOINT_META}


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_result_hash_deterministic():
    assert M.result_hash({"a": 1, "b": 2}) == M.result_hash({"b": 2, "a": 1})


def test_distribution_fn():
    recs = [{"result": "PASS"}, {"result": "FAIL"}, {"result": "PASS"}]
    assert M.distribution(recs, ("result",)) == {"FAIL": 1, "PASS": 2}
    assert M.distribution([], ("result",)) == {}


def test_read_role_missing_returns_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert ledger.read_role("knowledge_intelligence", "insights") == []
    assert ledger.read_role("nonexistent", "x") == []


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_api.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_bootstrap(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["bootstrap", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["registered"]["endpoints"] == 7


def test_cli_status(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["status"], capsys)
    assert rc == 0
    assert json.loads(out)["endpoint"] == "get_system_status"


def test_cli_timeline(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["timeline", "--limit", "5"], capsys)
    assert rc == 0
    assert json.loads(out)["data"]["truncated"] is False


def test_cli_lineage(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["lineage", "--strategy", "sX"], capsys)
    assert rc == 0
    assert json.loads(out)["data"]["strategy"] == "sX"


def test_cli_alpha_risk_agent_governance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    for cmd, ep in [("alpha", "get_alpha_summary"), ("risk", "get_risk_summary"),
                    ("agent", "get_agent_summary"), ("governance", "get_governance_report")]:
        rc, out = _run([cmd], capsys)
        assert rc == 0
        assert json.loads(out)["endpoint"] == ep


def test_cli_endpoints(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["bootstrap", "--commit"], capsys)
    rc, out = _run(["endpoints"], capsys)
    assert rc == 0
    assert len(json.loads(out)["endpoints"]) == 7


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["bootstrap", "--commit"], capsys)
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "endpoint_count" in json.loads(out)


# ══════════════ 추가 커버리지 ══════════════
def test_bootstrap_registers_views_and_queries(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().bootstrap(T0, commit=True)
    assert res["views"] == len(M.ENDPOINT_META)
    assert len(ledger.read_views()) == len(M.ENDPOINT_META)
    assert len(ledger.read_queries()) == res["queries"]
    assert res["queries"] >= len(M.ENDPOINT_META)


def test_endpoint_schema_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    sc = e.endpoint_schema("get_alpha_summary")
    assert sc is not None
    assert set(sc["fields"]) == set(ENDPOINT_SCHEMAS["get_alpha_summary"])


def test_list_endpoints_sorted(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.bootstrap(T0, commit=True)
    eps = e.list_endpoints()
    assert eps == sorted(eps)
    assert len(eps) == 7


def test_system_status_health_level_fallback(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # overview 만 있고 health 없음 → overview.health_level 폴백
    _seed(sp, "rcp_overview.jsonl", [{"component_count": 2, "health_level": "HEALTHY",
                                      "overall_score": 0.9, "snapshot_at": T0}])
    r = _eng().get_system_status(T1, commit=False)
    assert r.data["health_level"] == "HEALTHY"


def test_access_params_distinguish_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.get_strategy_lineage("sA", T0, commit=True)
    e.get_strategy_lineage("sB", T0, commit=True)  # 동일 시각·엔드포인트, 다른 params → 다른 id
    assert len(ledger.read_access()) == 2


def test_timeline_no_limit_not_truncated(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_timeline.jsonl", [{"kind": "A", "reference": "a", "occurred_at": T0}])
    r = _eng().get_research_timeline(0, T1, commit=False)
    assert r.data["truncated"] is False


def test_risk_summary_empty_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_risk_summary(T0, commit=False)
    assert r.data["result_distribution"] == {}
    assert r.data["assessment_count"] == 0


def test_governance_report_unknown_health_when_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_governance_report(T0, commit=False)
    assert r.data["health_level"] == "UNKNOWN"


def test_params_hash_fn():
    assert M.params_hash({"a": 1}) == M.params_hash({"a": 1})
    assert M.params_hash({"a": 1}) != M.params_hash({"a": 2})


def test_all_endpoint_paths_are_api_versioned():
    for _, path, _ in M.ENDPOINT_META:
        assert path.startswith("/api/v1/")


def test_field_types_defined():
    assert set(M.FIELD_TYPES) == {"int", "float", "str", "list", "dict", "bool"}


def test_response_envelope_shape(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _eng().get_alpha_summary(T0, commit=False).to_dict()
    assert set(d.keys()) == {"endpoint", "schema_id", "read_only", "data", "result_hash",
                             "disclaimer", "generated_at"}


# ══════════════ 통합 시나리오 ══════════════
def test_end_to_end_flow(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "rcp_overview.jsonl", [{"component_count": 27, "active_component_count": 5,
                                      "snapshot_at": T0, "category_distribution": {"RESEARCH": 9}}])
    _seed(sp, "rcp_health.jsonl", [{"level": "DEGRADED", "overall_score": 0.7}])
    _seed(sp, "ki_insights.jsonl", [{"insight_id": "i1", "insight_type": "RECOMMENDATION"}])
    _seed(sp, "rr_assessments.jsonl", [{"assessment_id": "a1", "result": "WARNING"}])
    _seed(sp, "sa_audits.jsonl", [{"audit_id": "au1", "result": "PASS"}])
    _seed(sp, "go_layers.jsonl", [{"event_id": "l1"}])
    _seed(sp, "rl_transitions.jsonl", [{"subject": "sX", "from_stage": "IDEA",
                                        "to_stage": "HYPOTHESIS", "created_at": T0}])
    e = _eng()
    e.bootstrap(T0, commit=True)
    assert e.get_system_status(T1, commit=True).data["component_count"] == 27
    assert e.get_alpha_summary(T1, commit=True).data["recommendation_count"] == 1
    assert e.get_risk_summary(T1, commit=True).data["assessment_count"] == 1
    assert e.get_agent_summary(T1, commit=True).data["audit_count"] == 1
    assert e.get_governance_report(T1, commit=True).data["layer_count"] == 1
    assert e.get_strategy_lineage("sX", T1, commit=True).data["stage_count"] == 1
    from jarvis.research_api.verify import verify_chain
    v = verify_chain()
    assert v["ok"] is True
    assert v["permission"]["ok"] is True
    assert v["schema"]["ok"] is True
