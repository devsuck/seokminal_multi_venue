"""P33 research_api_gateway 테스트 — 읽기전용 서비스·질의·응답·금지서비스거부·즉시조회·
계보·verify·replay·CLI·보안·READ ONLY 상위. GATEWAY ≠ EXECUTION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_api_gateway import ledger
from jarvis.research_api_gateway import models as M
from jarvis.research_api_gateway.engine import ResearchApiGatewayEngine
from jarvis.research_api_gateway.models import (
    FORBIDDEN_SERVICE_TYPES,
    FORBIDDEN_VERBS,
    SERVICE_TYPES,
    ForbiddenServiceError,
    content_hash,
    is_readonly_service,
)
from jarvis.research_api_gateway.verify import (
    duplicate_integrity,
    lineage_integrity,
    readonly_integrity,
    replay,
    response_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_api_gateway.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchApiGatewayEngine()


# ═══════════════ service registration (read-only only) ═══════════════
def test_register_service(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_service("KNOWLEDGE_QUERY", "kg-lookup", "query KG", T[0], commit=True)
    assert s.service_id.startswith("GWS:")
    assert s.is_readonly is True


@pytest.mark.parametrize("st", FORBIDDEN_SERVICE_TYPES)
def test_forbidden_service_rejected(tmp_path, monkeypatch, st):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ForbiddenServiceError):
        _eng().register_service(st, "n", now=T[0], commit=True)


def test_service_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_service("NOPE", "n", now=T[0], commit=True)


def test_service_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_service("METRICS", "m", now=T[0], commit=True).service_id
    b = e.register_service("METRICS", "m", now=T[1], commit=True).service_id
    assert a == b
    assert len(ledger.read_services()) == 1


@pytest.mark.parametrize("st", SERVICE_TYPES)
def test_service_types_allowed(tmp_path, monkeypatch, st):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_service(st, f"n-{st}", now=T[0], commit=True)
    assert s.service_type == st


def test_is_readonly_service():
    assert is_readonly_service("KNOWLEDGE_QUERY") is True
    assert is_readonly_service("TRADE") is False
    assert is_readonly_service("EXECUTE") is False


# ═══════════════ query (read-only) ═══════════════
def test_query(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[0], commit=True)
    assert r.response_id.startswith("GWP:")
    assert r.is_readonly is True


def test_query_forbidden_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ForbiddenServiceError):
        _eng().query("EXECUTE", now=T[0], commit=True)


def test_query_readonly_upstream(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("kg_entities.jsonl")
    with open(p, "w") as f:
        for i in range(4):
            f.write(json.dumps({"entity_id": f"e{i}"}) + "\n")
    before = open(p).read()
    r = _eng().query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[0], commit=True)
    assert r.result_count == 4
    assert open(p).read() == before  # 상위 원장 불변


def test_query_default_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().query("METRICS", now=T[0], commit=True)
    assert r.target_layer == "meta_intelligence"


def test_query_logs_query_and_response(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.query("HISTORY", "orchestration", {}, T[0], commit=True)
    assert len(ledger.read_queries()) == 1
    assert len(ledger.read_responses()) == 1


# ═══════════════ read-only helpers ═══════════════
def test_get_knowledge(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_knowledge()
    assert r["service"] == "KNOWLEDGE_QUERY"
    assert r["read_only"] is True


def test_get_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_summary()
    assert r["read_only"] is True
    assert set(r["counts"]) == set(ledger.SOURCE_LAYERS)


def test_get_metrics_history_reports_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    assert e.get_metrics()["read_only"] is True
    assert e.get_history()["read_only"] is True
    assert e.get_reports()["read_only"] is True
    assert e.get_lineage()["read_only"] is True


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("knowledge_graph", "memory_intelligence", "insight_intelligence", "meta_intelligence",
              "monitoring", "reliability", "autonomous_research", "strategy_generation",
              "orchestration", "resource_manager"):
        assert k in ledger.SOURCE_LAYERS


def test_all_source_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert set(ledger.all_source_counts()) == set(ledger.SOURCE_LAYERS)


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("KNOWLEDGE_QUERY", "kg", now=T[0], commit=True)
    e.query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[1], commit=True)
    e.query("METRICS", "meta_intelligence", {}, T[2], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    p = sp("rgw_services.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[0], commit=True)
    e.query("METRICS", "meta_intelligence", {}, T[1], commit=True)
    p = sp("rgw_queries.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_readonly_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    assert readonly_integrity()["ok"] is True


def test_readonly_integrity_detects_forbidden(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    p = sp("rgw_services.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["service_type"] = "TRADE"  # 금지 서비스 주입
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert readonly_integrity()["ok"] is False


def test_readonly_integrity_detects_non_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    p = sp("rgw_services.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_readonly"] = False
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert readonly_integrity()["ok"] is False


def test_response_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[0], commit=True)
    assert response_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "a", now=T[0], commit=True)
    e.register_service("HISTORY", "b", now=T[1], commit=True)
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("KNOWLEDGE_QUERY", "kg", now=T[0], commit=True)
    e.query("KNOWLEDGE_QUERY", "knowledge_graph", {}, T[1], commit=True)
    r = e.generate_report("SYSTEM", T[2], commit=True)
    assert r.report_id.startswith("GWR:")
    assert r.is_binding is False
    assert r.service_count == 1
    assert r.query_count == 1
    assert r.service_type_distribution.get("KNOWLEDGE_QUERY") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "READ ONLY" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["QUERY", "READ", "GET", "FETCH", "LIST"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_service_types_complete():
    for st in ("TRADE", "DEPLOY", "EXECUTE", "APPROVE", "ALLOCATE"):
        assert st in FORBIDDEN_SERVICE_TYPES


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.service_id, ("METRICS", "n"), "GWS:"),
    (M.query_id, ("METRICS", "l", 0), "GWQ:"),
    (M.response_id, ("q",), "GWP:"),
    (M.report_id, ("s", "t"), "GWR:"),
    (M.artifact_id, ("SERVICE", "r"), "GWA:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ summary ═══════════════
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "m", now=T[0], commit=True)
    e.query("METRICS", "meta_intelligence", {}, T[1], commit=True)
    s = e.summary(T[9])
    assert s.service_count == 1
    assert s.query_count == 1
    assert s.response_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_service(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["service", "--type", "KNOWLEDGE_QUERY", "--name", "kg", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["service"]["is_readonly"] is True


def test_cli_query(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["query", "--type", "METRICS", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["response"]["is_readonly"] is True


def test_cli_get(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["get", "--service", "RESEARCH_SUMMARY"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["read_only"] is True


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_api_gateway.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().register_service("METRICS", "m", now=T[0], commit=True)
    with pytest.raises(Exception):
        s.name = "x"


def test_five_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rgw_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rgw_services.jsonl", "rgw_queries.jsonl", "rgw_responses.jsonl",
                "rgw_reports.jsonl", "rgw_artifacts.jsonl"):
        assert req in names


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC)
def test_no_forbidden_method_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "deploy", "trade", "allocate", "approve", "provision", "mutate",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "write_upstream")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def purge_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


def test_engine_no_forbidden_methods():
    e = _eng()
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "provision"):
        assert not hasattr(e, attr)


# ═══════════════ 추가 커버리지 ═══════════════
@pytest.mark.parametrize("st", SERVICE_TYPES)
def test_query_each_service_type(tmp_path, monkeypatch, st):
    _iso(tmp_path, monkeypatch)
    r = _eng().query(st, None, {}, T[0], commit=True)
    assert r.service_type == st
    assert r.is_readonly is True


@pytest.mark.parametrize("layer", sorted(ledger.SOURCE_LAYERS))
def test_query_each_layer(tmp_path, monkeypatch, layer):
    _iso(tmp_path, monkeypatch)
    r = _eng().query("KNOWLEDGE_QUERY", layer, {}, T[0], commit=True)
    assert r.target_layer == layer
    assert r.result_count == 0


@pytest.mark.parametrize("st", FORBIDDEN_SERVICE_TYPES)
def test_query_forbidden_each(tmp_path, monkeypatch, st):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ForbiddenServiceError):
        _eng().query(st, now=T[0], commit=True)


def test_query_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().query("METRICS", "meta_intelligence", {}, T[0], commit=False)
    assert ledger.read_queries() == []


def test_query_multiple_same(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.query("METRICS", "meta_intelligence", {}, T[0], commit=True)
    e.query("METRICS", "meta_intelligence", {}, T[1], commit=True)
    assert len(ledger.read_queries()) == 2


def test_list_services(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_service("METRICS", "a", now=T[0], commit=True)
    e.register_service("HISTORY", "b", now=T[1], commit=True)
    assert len(e.list_services()) == 2


def test_service_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_service("METRICS", "m", now=T[0], commit=False)
    assert ledger.read_services() == []


def test_response_references_query(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.query("HISTORY", "orchestration", {}, T[0], commit=True)
    q = ledger.read_queries()[0]
    assert r.query_id == q["query_id"]


def test_get_knowledge_custom_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().get_knowledge("memory_intelligence")
    assert r["layer"] == "memory_intelligence"


def test_all_service_types_readonly():
    for st in SERVICE_TYPES:
        assert is_readonly_service(st) is True


def test_all_forbidden_not_readonly():
    for st in FORBIDDEN_SERVICE_TYPES:
        assert is_readonly_service(st) is False


def test_service_readonly_always_true(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for st in SERVICE_TYPES:
        s = e.register_service(st, f"svc-{st}", now=T[0], commit=True)
        assert s.is_readonly is True


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 계층 시드(READ ONLY 대상)
    with open(sp("kg_entities.jsonl"), "w") as f:
        for i in range(5):
            f.write(json.dumps({"entity_id": f"kg:{i}"}) + "\n")
    with open(sp("mri_meta_metrics.jsonl"), "w") as f:
        f.write(json.dumps({"metric_id": "mtm:1"}) + "\n")
    e = _eng()
    # 읽기 전용 서비스 등록(변경 서비스 거부)
    e.register_service("KNOWLEDGE_QUERY", "kg-lookup", "query knowledge graph", T[0], commit=True)
    e.register_service("METRICS", "meta-metrics", "query meta metrics", T[1], commit=True)
    for forbidden in ("TRADE", "DEPLOY", "EXECUTE", "APPROVE", "ALLOCATE"):
        with pytest.raises(ForbiddenServiceError):
            e.register_service(forbidden, "x", now=T[2], commit=True)
    # 읽기 전용 질의(상위 원장 변경 없음)
    r1 = e.query("KNOWLEDGE_QUERY", "knowledge_graph", {"limit": 10}, T[3], commit=True)
    assert r1.result_count == 5
    assert r1.is_readonly is True
    r2 = e.query("METRICS", "meta_intelligence", {}, T[4], commit=True)
    assert r2.result_count == 1
    # 즉시 조회
    assert e.get_summary()["read_only"] is True
    # 리포트
    rep = e.generate_report("SYSTEM", T[5], commit=True)
    assert rep.service_count == 2
    assert rep.query_count == 2
    assert rep.is_binding is False  # GATEWAY ≠ EXECUTION
    # 모든 응답 읽기 전용
    assert all(x["is_readonly"] is True for x in ledger.read_responses())
    # 상위 원장 불변
    assert open(sp("kg_entities.jsonl")).read()
    assert verify_chain()["ok"] is True
    assert replay(e, T[6])["deterministic"] is True
