"""P30 meta_research_intelligence 테스트 — 메타 지표·품질·기회(적용금지)·관찰·compute·
계보·verify·replay·CLI·보안·READ ONLY 상위. OBSERVATION ≠ OPTIMIZATION."""
from __future__ import annotations

import ast
import json
import os

import pytest

from jarvis.meta_research_intelligence import ledger
from jarvis.meta_research_intelligence import models as M
from jarvis.meta_research_intelligence.engine import MetaResearchIntelligenceEngine
from jarvis.meta_research_intelligence.models import (
    FORBIDDEN_VERBS,
    META_METRIC_NAMES,
    OBSERVATION_ASPECTS,
    OPPORTUNITY_AREAS,
    QUALITY_DIMENSIONS,
    classify_quality,
    content_hash,
    opportunity_priority,
    ratio,
)
from jarvis.meta_research_intelligence.verify import (
    duplicate_integrity,
    lineage_integrity,
    metric_integrity,
    opportunity_integrity,
    quality_integrity,
    replay,
    verify_chain,
)

T = [f"2026-07-24T00:{i:02d}:00Z" for i in range(60)]


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.meta_research_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return MetaResearchIntelligenceEngine()


# ═══════════════ meta metrics ═══════════════
def test_record_meta_metric(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().record_meta_metric("research_efficiency", 0.8, "ratio", "efficiency", "meta", T[0],
                                  commit=True)
    assert m.metric_id.startswith("MTM:")
    assert m.is_observation is True


def test_metric_multiple(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("m", 1, now=T[0], commit=True)
    e.record_meta_metric("m", 2, now=T[1], commit=True)
    assert len(ledger.metrics_by_name("m")) == 2


def test_metric_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().record_meta_metric("m", 1, now=T[0], commit=False)
    assert ledger.read_meta_metrics() == []


@pytest.mark.parametrize("name", META_METRIC_NAMES)
def test_meta_metric_names(name):
    assert name in META_METRIC_NAMES


# ═══════════════ compute_meta_metrics (READ ONLY) ═══════════════
def test_compute_meta_metrics_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().compute_meta_metrics(T[0], commit=True)
    assert set(m) == set(META_METRIC_NAMES)


def test_compute_efficiency(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("ar_cycles.jsonl"), "w") as f:
        f.write(json.dumps({"cycle_event_id": "c0", "to_state": "COMPLETED"}) + "\n")
        f.write(json.dumps({"cycle_event_id": "c1", "to_state": "ANALYZING"}) + "\n")
    m = _eng().compute_meta_metrics(T[0], commit=True)
    assert m["research_efficiency"] == 0.5  # 1/2 completed


def test_compute_validation_quality(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rel_integrity_checks.jsonl"), "w") as f:
        f.write(json.dumps({"check_id": "c0", "result": "PASS"}) + "\n")
        f.write(json.dumps({"check_id": "c1", "result": "FAIL"}) + "\n")
    m = _eng().compute_meta_metrics(T[0], commit=True)
    assert m["validation_quality"] == 0.5


def test_compute_readonly(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    p = sp("rmi_retrievals.jsonl")
    with open(p, "w") as f:
        for i in range(3):
            f.write(json.dumps({"retrieval_id": f"r{i}"}) + "\n")
    before = open(p).read()
    m = _eng().compute_meta_metrics(T[0], commit=True)
    assert m["knowledge_reuse"] == 3.0
    assert open(p).read() == before  # 상위 원장 불변


# ═══════════════ quality ═══════════════
def test_assess_quality(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    q = _eng().assess_quality("exp:1", "VALIDATION", 0.9, "well validated", T[0], commit=True)
    assert q.quality_id.startswith("MTQ:")
    assert q.grade == "HIGH"


def test_quality_bad_dimension(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().assess_quality("s", "NOPE", 0.5, now=T[0], commit=True)


@pytest.mark.parametrize("d", QUALITY_DIMENSIONS)
def test_quality_dimensions(d):
    assert d in QUALITY_DIMENSIONS


@pytest.mark.parametrize("score,grade", [(0.9, "HIGH"), (0.6, "MEDIUM"), (0.2, "LOW")])
def test_classify_quality(score, grade):
    assert classify_quality(score) == grade


# ═══════════════ opportunity (no application) ═══════════════
def test_detect_opportunity(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _eng().detect_opportunity("EFFICIENCY", "reduce cycle time", {"evidence_count": 5}, T[0],
                                  commit=True)
    assert o.opportunity_id.startswith("MTO:")
    assert o.is_applied is False
    assert 0.0 <= o.priority_score <= 1.0


def test_opportunity_bad_area(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().detect_opportunity("NOPE", "d", now=T[0], commit=True)


@pytest.mark.parametrize("area", OPPORTUNITY_AREAS)
def test_opportunity_areas(area):
    assert area in OPPORTUNITY_AREAS


def test_opportunity_priority_helper():
    assert opportunity_priority(0) == 0.0
    assert 0.0 < opportunity_priority(5) < 1.0


# ═══════════════ observation ═══════════════
def test_record_observation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _eng().record_observation("PROCESS", "cycles cluster at end of week", {}, T[0], commit=True)
    assert o.observation_id.startswith("MTB:")


def test_observation_bad_aspect(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(ValueError):
        _eng().record_observation("NOPE", "f", now=T[0], commit=True)


@pytest.mark.parametrize("a", OBSERVATION_ASPECTS)
def test_observation_aspects(a):
    assert a in OBSERVATION_ASPECTS


def test_ratio_helper():
    assert ratio(1, 4) == 0.25
    assert ratio(3, 0) == 0.0


# ═══════════════ integration READ ONLY ═══════════════
def test_source_layers_present():
    for k in ("autonomous_research", "reliability_incidents", "reliability_checks", "monitoring",
              "memory_retrievals", "strategy_generation"):
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
    e.compute_meta_metrics(T[0], commit=True)
    e.assess_quality("s", "RIGOR", 0.8, now=T[1], commit=True)
    e.detect_opportunity("REUSE", "increase reuse", {"evidence_count": 2}, T[2], commit=True)
    e.record_observation("REUSE", "reuse is low", now=T[3], commit=True)
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("m", 1, now=T[0], commit=True)
    p = sp("mri_meta_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["value"] = 999
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("a", 1, now=T[0], commit=True)
    e.record_meta_metric("b", 2, now=T[1], commit=True)
    p = sp("mri_meta_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:bad"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ok"] is False


def test_metric_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("m", 1, now=T[0], commit=True)
    assert metric_integrity()["ok"] is True


def test_metric_integrity_detects_non_observation(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("m", 1, now=T[0], commit=True)
    p = sp("mri_meta_metrics.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_observation"] = False
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert metric_integrity()["ok"] is False


def test_opportunity_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_opportunity("VELOCITY", "d", {"evidence_count": 1}, T[0], commit=True)
    assert opportunity_integrity()["ok"] is True


def test_opportunity_integrity_detects_applied(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.detect_opportunity("VELOCITY", "d", {"evidence_count": 1}, T[0], commit=True)
    p = sp("mri_opportunities.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["is_applied"] = True
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert opportunity_integrity()["ok"] is False


def test_quality_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assess_quality("s", "EVIDENCE", 0.7, now=T[0], commit=True)
    assert quality_integrity()["ok"] is True


def test_duplicate_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assess_quality("a", "RIGOR", 0.8, now=T[0], commit=True)
    e.assess_quality("b", "RIGOR", 0.6, now=T[1], commit=True)
    assert duplicate_integrity()["ok"] is True


def test_lineage_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.record_meta_metric("m", 1, now=T[0], commit=True)
    e.assess_quality("s", "RIGOR", 0.8, now=T[1], commit=True)
    assert lineage_integrity()["ok"] is True


# ═══════════════ replay ═══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assess_quality("s", "RIGOR", 0.8, now=T[0], commit=True)
    assert replay(e, T[9])["deterministic"] is True


# ═══════════════ report ═══════════════
def test_generate_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.assess_quality("s", "VALIDATION", 0.9, now=T[0], commit=True)
    e.detect_opportunity("EFFICIENCY", "d", {"evidence_count": 3}, T[1], commit=True)
    r = e.generate_report("SYSTEM", T[2], commit=True)
    assert r.report_id.startswith("MTR:")
    assert r.is_binding is False
    assert set(r.meta_metrics) == set(META_METRIC_NAMES)
    assert r.quality_distribution.get("HIGH") == 1
    assert r.area_distribution.get("EFFICIENCY") == 1


def test_report_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("SYSTEM", T[0], commit=True)
    assert "OPTIMIZATION" in r.disclaimer


# ═══════════════ 금지 동사 ═══════════════
@pytest.mark.parametrize("verb", sorted(FORBIDDEN_VERBS))
def test_forbidden_verb(verb):
    assert M.is_forbidden_verb(verb) is True


@pytest.mark.parametrize("verb", ["OBSERVE", "ANALYZE", "MEASURE", "ASSESS", "RECORD"])
def test_allowed_verb(verb):
    assert M.is_forbidden_verb(verb) is False


def test_forbidden_optimize_membership():
    assert "OPTIMIZE" in FORBIDDEN_VERBS
    assert "AUTO_OPTIMIZE" in FORBIDDEN_VERBS


def test_forbidden_empty():
    assert M.is_forbidden_verb("") is False


# ═══════════════ ID / hash ═══════════════
@pytest.mark.parametrize("fn,args,prefix", [
    (M.metric_id, ("m", 0), "MTM:"),
    (M.quality_id, ("s", "RIGOR"), "MTQ:"),
    (M.opportunity_id, ("EFFICIENCY", "d"), "MTO:"),
    (M.observation_id, ("PROCESS", "f"), "MTB:"),
    (M.report_id, ("s", "t"), "MTR:"),
    (M.artifact_id, ("META_METRIC", "r"), "MTA:"),
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
    e.assess_quality("s", "RIGOR", 0.8, now=T[0], commit=True)
    e.detect_opportunity("REUSE", "d", now=T[1], commit=True)
    s = e.summary(T[9])
    assert s.quality_count == 1
    assert s.opportunity_count == 1


# ═══════════════ CLI ═══════════════
def test_cli_metric(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["metric", "--name", "research_velocity", "--value", "10", "--unit", "count",
                 "--commit"]) == 0


def test_cli_compute(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["compute", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert "research_efficiency" in out["meta_metrics"]


def test_cli_quality(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["quality", "--subject", "s", "--dimension", "RIGOR", "--score", "0.8",
                 "--commit"]) == 0


def test_cli_opportunity(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["opportunity", "--area", "EFFICIENCY", "--description", "d", "--evidence-count",
                 "3", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["opportunity"]["is_applied"] is False


def test_cli_observation(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["observation", "--aspect", "PROCESS", "--finding", "f", "--commit"]) == 0


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["report", "--commit"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["report"]["is_binding"] is False


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["verify"]) == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["summary"]) == 0


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.meta_research_intelligence.__main__ import main
    assert main(["replay"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["deterministic"] is True


# ═══════════════ 격리 / ledger ═══════════════
def test_records_frozen(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().record_meta_metric("m", 1, now=T[0], commit=True)
    with pytest.raises(Exception):
        m.value = 5


def test_six_ledgers():
    assert len(ledger.ALL_LEDGERS) == 6


def test_ledger_filenames_prefixed():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("mri_")


def test_required_ledgers_present():
    names = {f for f, _ in ledger.ALL_LEDGERS}
    for req in ("mri_meta_metrics.jsonl", "mri_quality_records.jsonl", "mri_opportunities.jsonl",
                "mri_observations.jsonl", "mri_reports.jsonl", "mri_artifacts.jsonl"):
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
    bad = ("execute", "deploy", "trade", "allocate", "approve", "optimize", "select",
           "execute_trade", "place_order", "allocate_capital", "deploy_strategy", "auto_optimize")
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
    for attr in ("execute", "deploy", "trade", "allocate", "approve", "optimize"):
        assert not hasattr(e, attr)


# ═══════════════ end-to-end ═══════════════
def test_end_to_end(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 상위 연구 과정 시드(READ ONLY)
    with open(sp("ar_cycles.jsonl"), "w") as f:
        f.write(json.dumps({"cycle_event_id": "c0", "to_state": "COMPLETED"}) + "\n")
        f.write(json.dumps({"cycle_event_id": "c1", "to_state": "COMPLETED"}) + "\n")
    with open(sp("rel_integrity_checks.jsonl"), "w") as f:
        f.write(json.dumps({"check_id": "k0", "result": "PASS"}) + "\n")
    with open(sp("rmi_retrievals.jsonl"), "w") as f:
        f.write(json.dumps({"retrieval_id": "r0"}) + "\n")
    e = _eng()
    # 연구 과정 메타 지표 산출(관찰만)
    metrics = e.compute_meta_metrics(T[0], commit=True)
    assert metrics["research_efficiency"] == 1.0  # 2/2 completed
    assert metrics["validation_quality"] == 1.0
    assert metrics["knowledge_reuse"] == 1.0
    # 품질 평가
    e.assess_quality("regime-study", "VALIDATION", 0.9, "well validated", T[1], commit=True)
    # 최적화 기회(적용 없음)
    o = e.detect_opportunity("REUSE", "knowledge reuse could be higher", {"evidence_count": 4}, T[2],
                             commit=True)
    assert o.is_applied is False  # OPPORTUNITY ≠ APPLIED
    # 메타 관찰
    e.record_observation("VELOCITY", "candidate generation accelerating", now=T[3], commit=True)
    # 리포트
    r = e.generate_report("SYSTEM", T[4], commit=True)
    assert r.is_binding is False  # OBSERVATION ≠ OPTIMIZATION
    assert r.opportunity_count == 1
    # 상위 원장 불변
    assert open(sp("ar_cycles.jsonl")).read()
    assert verify_chain()["ok"] is True
    assert replay(e, T[5])["deterministic"] is True
