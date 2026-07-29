"""P34 research_dashboard_backend 테스트 — 패널·스냅샷(결정금지)·위젯·집계(통계/헬스/진행/...)·
계보·verify·replay·CLI·보안·READ ONLY 상위. AGGREGATION ≠ DECISION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_dashboard_backend import ledger
from jarvis.research_dashboard_backend import models as M
from jarvis.research_dashboard_backend.engine import ResearchDashboardBackendEngine
from jarvis.research_dashboard_backend.models import (
    FORBIDDEN_VERBS,
    PANEL_TYPES,
    content_hash,
    ratio,
)
from jarvis.research_dashboard_backend.verify import (
    duplicate_integrity,
    lineage_integrity,
    panel_integrity,
    replay,
    snapshot_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_dashboard_backend.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchDashboardBackendEngine()


# ═══════════════ panel ═══════════════
def test_register_panel(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().register_panel("STATISTICS", "overview", "system stats", T[0], commit=True)
    assert p.panel_id.startswith("DBP:")
    assert p.is_readonly is True


def test_panel_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_panel("NOPE", "n", now=T[0], commit=True)


def test_panel_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.register_panel("HEALTH", "h", now=T[0], commit=True).panel_id
    b = e.register_panel("HEALTH", "h", now=T[1], commit=True).panel_id
    assert a == b
    assert len(ledger.read_panels()) == 1


@pytest.mark.parametrize("pt", PANEL_TYPES)
def test_panel_types(tmp_path, monkeypatch, pt):
    _iso(tmp_path, monkeypatch)
    p = _eng().register_panel(pt, f"n-{pt}", now=T[0], commit=True)
    assert p.panel_type == pt


def test_panel_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_panel("MONITORING", "m", now=T[0], commit=True)
    assert any(a["artifact_type"] == "PANEL" for a in ledger.read_artifacts())


# ═══════════════ aggregation (READ ONLY, deterministic) ═══════════════
def test_aggregate_statistics(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        for i in range(3):
            f.write(json.dumps({"entity_id": f"e{i}"}) + "\n")
    stats = _eng().aggregate_statistics()
    assert stats["panel"] == "STATISTICS"
    assert stats["total"] == 3


def test_aggregate_health(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rmon_anomalies.jsonl"), "w") as f:
        f.write(json.dumps({"anomaly_id": "a0"}) + "\n")
    h = _eng().aggregate_health()
    assert h["anomalies"] == 1
    assert h["status"] == "DEGRADED"


def test_aggregate_health_nominal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().aggregate_health()
    assert h["status"] == "NOMINAL"


def test_knowledge_summary(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rmi_memories.jsonl"), "w") as f:
        f.write(json.dumps({"memory_event_id": "m0"}) + "\n")
    k = _eng().knowledge_summary()
    assert k["memories"] == 1


def test_research_progress(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("ar_cycles.jsonl"), "w") as f:
        f.write(json.dumps({"cycle_event_id": "c0"}) + "\n")
    p = _eng().research_progress()
    assert p["cycles"] == 1
    assert p["total_activity"] == 1


def test_monitoring_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().monitoring_summary()
    assert m["panel"] == "MONITORING"


def test_build_timeline(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "e0"}) + "\n")
    t = _eng().build_timeline()
    assert "knowledge_graph" in t["active_layers"]


def test_aggregation_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("kg_entities.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"entity_id": "e0"}) + "\n")
    before = open(p).read()
    _eng().aggregate_statistics()
    assert open(p).read() == before  # 상위 원장 불변


# ═══════════════ snapshot (no decision) ═══════════════
def test_create_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot("STATISTICS", T[0], commit=True)
    assert s.snapshot_id.startswith("DBS:")
    assert s.is_decision is False
    assert s.data_hash.startswith("sha256:")


def test_snapshot_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().create_snapshot("NOPE", T[0], commit=True)


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s1 = e.create_snapshot("HEALTH", T[0], commit=False)
    s2 = e.create_snapshot("HEALTH", T[0], commit=False)
    assert s1.to_dict() == s2.to_dict()


@pytest.mark.parametrize("pt", PANEL_TYPES)
def test_snapshot_each_panel(tmp_path, monkeypatch, pt):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_snapshot(pt, T[0], commit=True)
    assert s.panel_type == pt
    assert s.is_decision is False


def test_snapshot_never_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for pt in PANEL_TYPES:
        s = e.create_snapshot(pt, T[0], commit=True)
        assert s.is_decision is False


# ═══════════════ widget ═══════════════
def test_record_widget(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _eng().record_widget("STATISTICS", "total_experiments", 42, "count", T[0], commit=True)
    assert w.widget_id.startswith("DBW:")
    assert w.value == 42.0


def test_widget_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().record_widget("NOPE", "m", 1, now=T[0], commit=True)


def test_widget_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_widget("HEALTH", "m", 1, now=T[0], commit=True)
    e.record_widget("HEALTH", "m", 2, now=T[1], commit=True)
    assert len(ledger.widgets_by_panel("HEALTH")) == 2


def test_ratio_helper():
    assert ratio(1, 4) == 0.25
    assert ratio(3, 0) == 0.0


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("knowledge_graph", "memory_intelligence", "insight_intelligence", "meta_intelligence",
              "monitoring_health", "monitoring_anomalies", "reliability", "autonomous_research",
              "strategy_generation", "orchestration", "resource_manager", "agent_coordination"):
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
    e.register_panel("STATISTICS", "s", now=T[0], commit=True)
    e.create_snapshot("STATISTICS", T[1], commit=True)
    e.record_widget("STATISTICS", "m", 1, now=T[2], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("HEALTH", "h", now=T[0], commit=True)
    p = sp("rdb_panels.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_snapshot("STATISTICS", T[0], commit=True)
    e.create_snapshot("HEALTH", T[1], commit=True)
    p = sp("rdb_snapshots.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_snapshot_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_snapshot("STATISTICS", T[0], commit=True)
    assert snapshot_integrity()["ok"] is True


def test_snapshot_integrity_detects_decision(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.create_snapshot("STATISTICS", T[0], commit=True)
    p = sp("rdb_snapshots.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_decision"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert snapshot_integrity()["ok"] is False


def test_panel_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("HEALTH", "h", now=T[0], commit=True)
    assert panel_integrity()["ok"] is True


def test_panel_integrity_detects_non_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("HEALTH", "h", now=T[0], commit=True)
    p = sp("rdb_panels.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_readonly"] = False
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert panel_integrity()["ok"] is False


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("STATISTICS", "a", now=T[0], commit=True)
    e.register_panel("HEALTH", "b", now=T[1], commit=True)
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("STATISTICS", "s", now=T[0], commit=True)
    e.create_snapshot("STATISTICS", T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("STATISTICS", "s", now=T[0], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("STATISTICS", "s", now=T[0], commit=True)
    e.create_snapshot("STATISTICS", T[1], commit=True)
    r = e.generate_report("SYSTEM", T[2], commit=True)
    assert r.report_id.startswith("DBR:")
    assert r.is_binding is False
    assert r.panel_count == 1
    assert r.snapshot_count == 1
    assert r.panel_type_distribution.get("STATISTICS") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "DECISION" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["AGGREGATE", "DISPLAY", "SUMMARIZE", "SHOW", "RENDER"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_decide_membership():
    assert "DECIDE" in FORBIDDEN_VERBS
    assert "MAKE_DECISION" in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.panel_id, ("STATISTICS", "n"), "DBP:"),
    (M.snapshot_id, ("STATISTICS", "t"), "DBS:"),
    (M.widget_id, ("HEALTH", "m", 0), "DBW:"),
    (M.report_id, ("s", "t"), "DBR:"),
    (M.artifact_id, ("PANEL", "r"), "DBA:"),
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
    e.register_panel("HEALTH", "h", now=T[0], commit=True)
    e.create_snapshot("HEALTH", T[1], commit=True)
    s = e.summary(T[9])
    assert s.panel_count == 1
    assert s.snapshot_count == 1


def test_list_panels(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_panel("STATISTICS", "a", now=T[0], commit=True)
    e.register_panel("HEALTH", "b", now=T[1], commit=True)
    assert len(e.list_panels()) == 2


# ═══════════════ CLI ═══════════════
def test_cli_panel(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["panel", "--type", "STATISTICS", "--name", "overview", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["panel"]["is_readonly"] is True


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["snapshot", "--type", "HEALTH", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["snapshot"]["is_decision"] is False


def test_cli_widget(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["widget", "--type", "STATISTICS", "--metric", "m", "--value", "5",
                 "--commit"]) == 0


def test_cli_aggregate(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["aggregate", "--panel", "STATISTICS"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["panel"] == "STATISTICS"


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_dashboard_backend.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _eng().register_panel("HEALTH", "h", now=T[0], commit=True)
    with pytest.raises(Exception):
        p.name = "x"


def test_five_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rdb_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("rdb_panels.jsonl", "rdb_snapshots.jsonl", "rdb_widgets.jsonl",
                "rdb_reports.jsonl", "rdb_artifacts.jsonl"):
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
    bad = ("execute", "deploy", "trade", "allocate", "approve", "decide", "make_decision",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "select_strategy")
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
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "decide"):
        assert not hasattr(e, attr)


# ═══════════════ 추가 커버리지 ═══════════════
@pytest.mark.parametrize("pt", PANEL_TYPES)
def test_widget_each_panel(tmp_path, monkeypatch, pt):
    _iso(tmp_path, monkeypatch)
    w = _eng().record_widget(pt, "m", 1, now=T[0], commit=True)
    assert w.panel_type == pt


@pytest.mark.parametrize("pt", PANEL_TYPES)
def test_panel_readonly_always(tmp_path, monkeypatch, pt):
    _iso(tmp_path, monkeypatch)
    p = _eng().register_panel(pt, f"p-{pt}", now=T[0], commit=True)
    assert p.is_readonly is True


def test_snapshot_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_snapshot("STATISTICS", T[0], commit=False)
    assert ledger.read_snapshots() == []


def test_panel_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_panel("HEALTH", "h", now=T[0], commit=False)
    assert ledger.read_panels() == []


def test_all_aggregations_readonly_flag(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    assert e.aggregate_statistics()["layer_count"] == len(ledger.SOURCE_LAYERS)
    assert e.knowledge_summary()["panel"] == "KNOWLEDGE_SUMMARY"
    assert e.monitoring_summary()["panel"] == "MONITORING"


def test_snapshot_data_hash_changes(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    s0 = e.create_snapshot("STATISTICS", T[0], commit=False)
    with open(sp("kg_entities.jsonl"), "w") as f:
        f.write(json.dumps({"entity_id": "e0"}) + "\n")
    s1 = e.create_snapshot("STATISTICS", T[1], commit=False)
    assert s0.data_hash != s1.data_hash


def test_timeline_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    t = _eng().build_timeline()
    assert t["active_layers"] == []


def test_widget_value_float(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    w = _eng().record_widget("STATISTICS", "rate", 0.75, "ratio", T[0], commit=True)
    assert w.value == 0.75


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 계층 시드(READ ONLY 집계 대상)
    with open(sp("kg_entities.jsonl"), "w") as f:
        for i in range(4):
            f.write(json.dumps({"entity_id": f"kg:{i}"}) + "\n")
    with open(sp("ar_cycles.jsonl"), "w") as f:
        f.write(json.dumps({"cycle_event_id": "ar:1"}) + "\n")
    with open(sp("rmon_anomalies.jsonl"), "w") as f:
        f.write(json.dumps({"anomaly_id": "an:1"}) + "\n")
    e = _eng()
    # 패널 등록(백엔드 집계 정의)
    for pt in ("STATISTICS", "HEALTH", "RESEARCH_PROGRESS", "MONITORING"):
        e.register_panel(pt, f"panel-{pt}", "", T[0], commit=True)
    # 집계 스냅샷(결정 아님)
    stats = e.create_snapshot("STATISTICS", T[1], commit=True)
    assert stats.data["total"] == 6  # 4 kg + 1 ar + 1 anomaly
    assert stats.is_decision is False
    health = e.create_snapshot("HEALTH", T[2], commit=True)
    assert health.data["status"] == "DEGRADED"  # anomaly present
    progress = e.create_snapshot("RESEARCH_PROGRESS", T[3], commit=True)
    assert progress.data["cycles"] == 1
    # 위젯
    e.record_widget("STATISTICS", "total_entities", 4, "count", T[4], commit=True)
    # 리포트
    r = e.generate_report("SYSTEM", T[5], commit=True)
    assert r.panel_count == 4
    assert r.snapshot_count == 3
    assert r.is_binding is False  # AGGREGATION ≠ DECISION
    # 모든 스냅샷 결정 아님
    assert all(s["is_decision"] is False for s in ledger.read_snapshots())
    # 상위 원장 불변
    assert open(sp("kg_entities.jsonl")).read()
    assert verify_chain()["ok"] is True
    assert replay(e, T[6])["deterministic"] is True
