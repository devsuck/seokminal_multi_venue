"""P23 research_monitoring 테스트 — 세션 생애주기·지표·헬스·관찰·활동·이상(자동조치 금지)·
스냅샷 결정성·계보·verify·replay·CLI·보안·금지능력·READ ONLY 상위."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.research_monitoring import ledger
from jarvis.research_monitoring import models as M
from jarvis.research_monitoring.engine import ResearchMonitoringEngine
from jarvis.research_monitoring.models import (
    ANOMALY_RULES,
    FORBIDDEN_VERBS,
    GENESIS,
    HEALTH_STATUSES,
    METRIC_TYPES,
    SESSION_STATES,
    SEVERITIES,
    S_ANALYZED,
    S_ARCHIVED,
    S_COLLECTING,
    S_CREATED,
    S_SNAPSHOTTED,
    IllegalSessionTransition,
    UnknownEntityError,
    aggregate_health,
    can_session_transition,
    classify_health,
    content_hash,
)
from jarvis.research_monitoring.verify import (
    anomaly_integrity,
    duplicate_integrity,
    lineage_integrity,
    reference_integrity,
    replay,
    session_lifecycle_integrity,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_monitoring.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchMonitoringEngine()


def _sess(e, name="s1", now=T[0]):
    return e.create_session(name, now, commit=True).session_id


# ═══════════════ session lifecycle ═══════════════
def test_create_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ev = _eng().create_session("s", T[0], commit=True)
    assert ev.to_state == S_CREATED
    assert ev.session_id.startswith("MOC:")
    assert ev.session_event_id.startswith("MON:")


def test_session_full_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_collecting(sess, T[1], commit=True)
    e.analyze_session(sess, T[2], commit=True)
    e.snapshot_session(sess, T[3], commit=True)
    e.archive_session(sess, T[4], commit=True)
    assert e.session_state(sess) == S_ARCHIVED


def test_session_no_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    with pytest.raises(IllegalSessionTransition):
        e.analyze_session(sess, T[1], commit=True)  # CREATED→ANALYZED skip


def test_session_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.create_session("s", T[0], commit=True).session_id
    b = e.create_session("s", T[1], commit=True).session_id
    assert a == b
    assert len(ledger.session_events(a)) == 1


def test_session_unknown(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownEntityError):
        _eng().start_collecting("MOC:nope", T[1], commit=True)


def test_session_artifact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    assert any(a["artifact_type"] == "SESSION" for a in ledger.read_artifacts())


@pytest.mark.parametrize("frm,to,ok", [
    (S_CREATED, S_COLLECTING, True), (S_CREATED, S_ANALYZED, False),
    (S_COLLECTING, S_ANALYZED, True), (S_ANALYZED, S_SNAPSHOTTED, True),
    (S_SNAPSHOTTED, S_ARCHIVED, True), (S_SNAPSHOTTED, S_COLLECTING, True),
    (S_ARCHIVED, S_COLLECTING, False),
])
def test_session_transition_matrix(frm, to, ok):
    assert can_session_transition(frm, to) is ok


@pytest.mark.parametrize("s", SESSION_STATES)
def test_session_states(s):
    assert s in SESSION_STATES


# ═══════════════ metrics ═══════════════
def test_register_metric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = e.register_metric("task_completion_rate", 0.85, "RATIO", "research_automation", "ra:wf",
                          T[0], commit=True)
    assert m.metric_id.startswith("MOM:")
    assert m.value == 0.85
    assert m.hash.startswith("sha256:")


def test_metric_bad_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().register_metric("m", 1, "NOPE", now=T[0], commit=True)


def test_metric_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    e.register_metric("m", 2, now=T[1], commit=True)
    assert len(ledger.metrics_by_name("m")) == 2


def test_metric_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_metric("m", 1, now=T[0], commit=False)
    assert ledger.read_metrics() == []


@pytest.mark.parametrize("mt", METRIC_TYPES)
def test_metric_types(mt):
    assert mt in METRIC_TYPES


# ═══════════════ health checks ═══════════════
def test_record_health_check(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    h = e.record_health_check("data_pipeline", 0.9, {"latency": 5}, T[0], commit=True)
    assert h.health_id.startswith("MOH:")
    assert h.status == "HEALTHY"


@pytest.mark.parametrize("score,status", [
    (1.0, "HEALTHY"), (0.8, "HEALTHY"), (0.7, "WARNING"), (0.5, "WARNING"),
    (0.4, "FAILED"), (0.0, "FAILED"), (1.5, "WARNING"), (-0.1, "WARNING"),
])
def test_classify_health(score, status):
    assert classify_health(score) == status


def test_classify_health_bad():
    assert classify_health("x") == "WARNING"


def test_evaluate_system_health(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_health_check("data", 0.9, {}, T[0], commit=True)
    e.record_health_check("pipeline", 0.7, {}, T[1], commit=True)
    health = e.evaluate_system_health(T[2])
    assert health["score"] == 0.8
    assert health["status"] == "HEALTHY"


def test_aggregate_health():
    r = aggregate_health({"a": 0.9, "b": 0.3})
    assert r["score"] == 0.6
    assert r["status"] == "WARNING"


def test_aggregate_empty():
    assert aggregate_health({})["status"] == "WARNING"


@pytest.mark.parametrize("s", HEALTH_STATUSES)
def test_health_statuses(s):
    assert s in HEALTH_STATUSES


# ═══════════════ observation / activity / observe_pipeline ═══════════════
def test_record_observation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    o = e.record_observation("research_automation", "PIPELINE_OBSERVED", {"count": 5}, T[0],
                             commit=True)
    assert o.observation_id.startswith("MOO:")


def test_record_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.record_activity("research_automation", "RECORD_COUNT", 10, "wf", T[0], commit=True)
    assert a.activity_event_id.startswith("MOV:")
    assert a.count == 10


def test_observe_pipeline_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("ra_workflows.jsonl")
    with open(p, "w") as f:
        for i in range(4):
            f.write(json.dumps({"workflow_event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    e = _eng()
    res = e.observe_pipeline("research_automation", "wf1", T[0], commit=True)
    assert res["count"] == 4
    assert open(p).read() == before  # 상위 원장 불변


# ═══════════════ anomaly (detection only) ═══════════════
def test_detect_anomaly(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    a = e.detect_anomaly("REPEATED_EXPERIMENT_FAILURES", "exp1", "HIGH", "5 fails", T[0],
                         commit=True)
    assert a.anomaly_id.startswith("MOA:")
    assert a.severity == "HIGH"
    assert a.is_actionable is False


def test_anomaly_bad_rule(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().detect_anomaly("NOPE", "x", now=T[0], commit=True)


def test_anomaly_bad_severity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().detect_anomaly("BROKEN_LINEAGE", "x", "NUCLEAR", now=T[0], commit=True)


def test_scan_missing_upstream(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # 소스 원장 미존재 → 모든 대상 MISSING_UPSTREAM_LEDGER
    anomalies = e.scan_missing_upstream(T[0], commit=True)
    assert len(anomalies) == len(ledger.SOURCE_LAYERS)
    assert all(a.rule == "MISSING_UPSTREAM_LEDGER" for a in anomalies)


def test_scan_missing_upstream_present(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 한 소스만 존재하게
    for layer, spec in ledger.SOURCE_LAYERS.items():
        pass
    p = sp("ra_workflows.jsonl")
    with open(p, "w") as f:
        f.write(json.dumps({"workflow_event_id": "e0"}) + "\n")
    e = _eng()
    anomalies = e.scan_missing_upstream(T[0], commit=True)
    # research_automation 은 존재 → 이상 아님
    assert not any(a.source_reference == "research_automation" for a in anomalies)


@pytest.mark.parametrize("rule", ANOMALY_RULES)
def test_anomaly_rules(rule):
    assert rule in ANOMALY_RULES


@pytest.mark.parametrize("sev", SEVERITIES)
def test_severities(sev):
    assert sev in SEVERITIES


# ═══════════════ snapshot (deterministic) ═══════════════
def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    s1 = e.create_snapshot("SYSTEM", T[5], commit=False)
    s2 = e.create_snapshot("SYSTEM", T[5], commit=False)
    assert s1.to_dict() == s2.to_dict()


def test_snapshot_id_prefix(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_snapshot("SYSTEM", T[0]).snapshot_id.startswith("MOS:")


def test_snapshot_not_binding(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().create_snapshot("SYSTEM", T[0]).is_binding is False


def test_snapshot_metrics_hash_changes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    s0 = e.create_snapshot("SYSTEM", T[0], commit=False)
    e.register_metric("m", 1, now=T[1], commit=True)
    s1 = e.create_snapshot("SYSTEM", T[2], commit=False)
    assert s0.metrics_hash != s1.metrics_hash


def test_snapshot_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    e.record_health_check("c", 0.9, {}, T[1], commit=True)
    e.detect_anomaly("BROKEN_LINEAGE", "x", "LOW", "", T[2], commit=True)
    s = e.create_snapshot("SYSTEM", T[3], commit=True)
    assert s.metric_count == 1
    assert s.health_count == 1
    assert s.anomaly_count == 1


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_health_check("data", 0.9, {}, T[0], commit=True)
    e.detect_anomaly("DATA_QUALITY_DEGRADATION", "ds1", "MEDIUM", "", T[1], commit=True)
    r = e.generate_report("SYSTEM", T[2], commit=True)
    assert r.report_id.startswith("MOR:")
    assert r.is_binding is False
    assert r.overall_health == "HEALTHY"
    assert r.anomaly_severity_distribution.get("MEDIUM") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "APPROVAL" in r.disclaimer


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers(tmp_path, monkeypatch):
    for k in ("data_governance", "research_automation", "continuous_learning",
              "production_readiness", "research_operations"):
        assert k in ledger.SOURCE_LAYERS


def test_source_count_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("cl_memories.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"memory_event_id": f"e{i}"}) + "\n")
    before = open(p).read()
    assert ledger.source_count("continuous_learning") == 3
    assert open(p).read() == before


# ═══════════════ verify ═══════════════
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert verify_chain()["ok"] is True


def test_verify_after_activity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_collecting(sess, T[1], commit=True)
    e.register_metric("m", 1, now=T[2], commit=True)
    e.record_health_check("c", 0.9, {}, T[3], commit=True)
    e.detect_anomaly("BROKEN_LINEAGE", "x", "LOW", "", T[4], commit=True)
    e.create_snapshot("SYSTEM", T[5], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    p = sp("rmon_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["value"] = 999
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("a", 1, now=T[0], commit=True)
    e.register_metric("b", 2, now=T[1], commit=True)
    p = sp("rmon_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    p = sp("rmon_sessions.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    with open(p, "a") as f:
        f.write(json.dumps(rows[0]) + "\n")
    assert verify_chain()["ok"] is False


def test_session_lifecycle_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    sess = _sess(e)
    e.start_collecting(sess, T[1], commit=True)
    assert session_lifecycle_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e, "a")
    _sess(e, "b")
    assert duplicate_integrity()["ok"] is True


def test_anomaly_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_anomaly("FAILED_VERIFICATION", "x", "HIGH", "", T[0], commit=True)
    assert anomaly_integrity()["ok"] is True


def test_anomaly_integrity_detects_actionable(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_anomaly("FAILED_VERIFICATION", "x", "HIGH", "", T[0], commit=True)
    p = sp("rmon_anomalies.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_actionable"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert anomaly_integrity()["ok"] is False


def test_reference_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_health_check("c", 0.9, {}, T[0], commit=True)
    e.register_metric("m", 1, now=T[1], commit=True)
    assert reference_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e)
    e.create_snapshot("SYSTEM", T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["OBSERVE", "MONITOR", "MEASURE", "DETECT", "REPORT", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


@pytest.mark.parametrize("v", ["EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL",
                                "DEPLOY_STRATEGY", "PROMOTE_MODEL", "ACTIVATE_LIVE",
                                "CHANGE_PERMISSION", "CONTROL_AGENT", "MODIFY_WORKFLOW"])
def test_forbidden_membership(v):
    assert v in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.session_id, ("n",), "MOC:"),
    (M.session_event_id, ("s", "S", 0), "MON:"),
    (M.metric_id, ("m", "r", 0), "MOM:"),
    (M.health_id, ("c", 0), "MOH:"),
    (M.observation_id, ("s", "e", 0), "MOO:"),
    (M.activity_event_id, ("l", "a", 0), "MOV:"),
    (M.anomaly_id, ("r", "s", 0), "MOA:"),
    (M.snapshot_id, ("s", "t"), "MOS:"),
    (M.report_id, ("s", "t"), "MOR:"),
    (M.artifact_id, ("SESSION", "r"), "MOF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_content_hash_excludes_meta():
    a = content_hash({"x": 1, "previous_hash": "p", "record_hash": "r"})
    b = content_hash({"x": 1, "previous_hash": "Q", "record_hash": "Z"})
    assert a == b


# ═══════════════ 조회 ═══════════════
def test_list_sessions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _sess(e, "a")
    _sess(e, "b")
    assert len(e.list_sessions()) == 2


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_metric("m", 1, now=T[0], commit=True)
    e.detect_anomaly("BROKEN_LINEAGE", "x", "LOW", "", T[1], commit=True)
    s = e.summary(T[9])
    assert s.metric_count == 1
    assert s.anomaly_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_metric(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["metric", "--name", "m", "--value", "0.9", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["metric"]["value"] == 0.9


def test_cli_health(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["health", "--component", "data", "--score", "0.9", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["health"]["status"] == "HEALTHY"


def test_cli_anomaly(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["anomaly", "--rule", "BROKEN_LINEAGE", "--ref", "x", "--severity", "HIGH",
                 "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["anomaly"]["is_actionable"] is False


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["snapshot", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["snapshot"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["verify"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


def test_cli_observe(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_monitoring.__main__ import main
    assert main(["observe", "--layer", "research_automation", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "count" in out["observed"]


# ═══════════════ 격리 / ledger ═══════════════
def test_no_write_without_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_metric("m", 1, now=T[0], commit=False)
    assert not os.path.exists(os.path.join(tmp_path, "rmon_metrics.jsonl"))


def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().register_metric("m", 1, now=T[0], commit=True)
    with pytest.raises(Exception):
        m.value = 5


def test_nine_ledgers():
    assert len(ledger.ALL_LEDGERS) == 9


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rmon_")


# ═══════════════ 보안 스캔 ═══════════════
_PKG = os.path.dirname(os.path.dirname(__file__))
_SRC = [os.path.join(_PKG, f) for f in os.listdir(_PKG) if f.endswith(".py")]

_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_portfolio", "jarvis.permission_control",
    "jarvis.portfolio", "jarvis.risk", "jarvis.permission", "jarvis.deployment", "jarvis.live",
    "jarvis.order", "jarvis.live_execution",
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
    bad = ("execute", "deploy", "approve", "allocate", "promote", "trade", "execute_trade",
           "place_order", "allocate_capital", "deploy_strategy", "promote_model", "activate_live",
           "change_permission")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC)
def test_no_model_id_leak(path):
    assert "claude-opus" not in open(path).read().lower()


@pytest.mark.parametrize("path", _SRC)
def test_no_destructive_ledger_api(path):
    src = open(path).read()
    for bad in ("def delete_", "def overwrite_", "def drop_", "def truncate", "def update_"):
        assert bad not in src


def test_ledger_append_only():
    src = open(os.path.join(_PKG, "ledger.py")).read()
    assert '"a"' in src
    assert '"w"' not in src


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 소스 시드(READ ONLY 대상)
    p = sp("ra_workflows.jsonl")
    with open(p, "w") as f:
        for i in range(6):
            f.write(json.dumps({"workflow_event_id": f"e{i}"}) + "\n")
    e = _eng()
    sess = e.create_session("nightly-monitoring", T[0], commit=True).session_id
    e.start_collecting(sess, T[1], commit=True)
    # 파이프라인 관찰(자동화) → 지표
    obs = e.observe_pipeline("research_automation", "ra:wf", T[2], commit=True)
    assert obs["count"] == 6
    # 건강 체크(구성요소별)
    e.record_health_check("data_health", 0.9, {"missing": 0}, T[3], commit=True)
    e.record_health_check("pipeline_health", 0.85, {"completion": 0.9}, T[4], commit=True)
    e.record_health_check("experiment_health", 0.6, {"failure_ratio": 0.3}, T[5], commit=True)
    e.record_health_check("automation_health", 0.8, {}, T[6], commit=True)
    e.record_health_check("integrity_health", 1.0, {}, T[7], commit=True)
    health = e.evaluate_system_health(T[8])
    assert health["status"] in ("HEALTHY", "WARNING")
    # 이상 탐지(탐지·기록만)
    e.detect_anomaly("REPEATED_EXPERIMENT_FAILURES", "exp:mom", "MEDIUM", "3 consecutive", T[9],
                     commit=True)
    e.analyze_session(sess, T[10], commit=True)
    # 스냅샷(결정적)
    snap = e.create_snapshot("SYSTEM", T[11], commit=True)
    e.snapshot_session(sess, T[12], commit=True)
    # 리포트
    r = e.generate_report("SYSTEM", T[13], commit=True)
    assert r.health_check_count == 5
    assert r.anomaly_count == 1
    assert r.is_binding is False  # HEALTH ≠ APPROVAL
    e.archive_session(sess, T[14], commit=True)
    assert e.session_state(sess) == S_ARCHIVED
    assert open(p).read()  # 상위 원장 여전히 존재·불변
    assert verify_chain()["ok"] is True
    assert replay(e, T[15])["deterministic"] is True
