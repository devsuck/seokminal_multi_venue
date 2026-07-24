"""P10.30 Research OS Core 테스트 (Phase 10 최종). **상위 연구 운영 환경 — 관측 전용.**

모듈 등록(불변)·완전 모듈 발견(10대 도메인 × P9.8~P10.29)·모듈 카탈로그·OS 스냅샷(결정적·재현·불변)·OS 헬스
(결정적·불변)·글로벌 리포트·글로벌 상태·도메인 의존성 무결성·거버넌스 컴플라이언스·전체 무결성 검증·replay·
상위 READ ONLY 보호·CLI·보안(금지import·execute/trade/deploy/allocate/modify 없음·실행 경로 없음·상위 원장
무변경·삭제 API 없음·불변·OBSERVE≠EXECUTE·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_os_core import ledger
from jarvis.research_os_core import models as M
from jarvis.research_os_core.engine import ResearchOSCoreEngine
from jarvis.research_os_core.models import (
    DOMAINS,
    HEALTH_CRITICAL,
    HEALTH_DEGRADED,
    HEALTH_HEALTHY,
    HEALTH_UNKNOWN,
    STATE_ACTIVE,
    STATE_EMPTY,
    STATE_MISSING,
    ImmutableCatalogError,
    ImmutableModuleError,
    ImmutableSnapshotError,
    ImmutableStateError,
    InvalidDomain,
)

T0 = "2026-07-24T00:00:00Z"
T1 = "2026-07-24T00:01:00Z"
T2 = "2026-07-24T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_os_core.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchOSCoreEngine()


def _seed(sp, filename, rows):
    with open(sp(filename), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def _reg_active(e, sp, name, domain, filename, now=T0):
    _seed(sp, filename, [{"id": "x1"}])
    return e.register_module(name, domain, "P10", filename, "id", now, commit=True)


def _reg_missing(e, name, domain, filename="missing.jsonl", now=T0):
    return e.register_module(name, domain, "P10", filename, "id", now, commit=True)


def _all_domains_active(e, sp, now=T0):
    for i, d in enumerate(DOMAINS):
        _reg_active(e, sp, f"mod_{d}", d, f"src_{i}.jsonl", now)


# ══════════════ register_module ══════════════
def test_register_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().register_module("alpha_intelligence", "ALPHA", "P10.2", "ai_signals.jsonl",
                               "signal_hash", T0, commit=True)
    assert m.module_id.startswith("OSM:")
    assert m.domain == "ALPHA"


def test_register_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    a = _eng().register_module("x", "DATA", now=T0, commit=False)
    b = _eng().register_module("x", "DATA", now=T1, commit=False)
    assert a.module_id == b.module_id


def test_register_commit_persists(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_module("x", "DATA", now=T0, commit=True)
    assert len(ledger.read_modules()) == 1


def test_register_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().register_module("x", "DATA", now=T0, commit=False)
    assert ledger.read_modules() == []


def test_register_invalid_domain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidDomain):
        _eng().register_module("x", "NOPE", now=T0, commit=True)


def test_register_all_ten_domains(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    for d in DOMAINS:
        m = e.register_module(f"m_{d}", d, now=T0, commit=True)
        assert m.domain == d
    assert len(ledger.read_modules()) == 10


def test_register_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", "P1", now=T0, commit=True)
    e.register_module("x", "DATA", "P1", now=T1, commit=True)
    assert len(ledger.read_modules()) == 1


def test_register_immutable_domain_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", "P1", now=T0, commit=True)
    with pytest.raises(ImmutableModuleError):
        e.register_module("x", "MODEL", "P1", now=T1, commit=True)


def test_register_immutable_phase_change(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", "P1", now=T0, commit=True)
    with pytest.raises(ImmutableModuleError):
        e.register_module("x", "DATA", "P2", now=T1, commit=True)


def test_register_has_record_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    m = _eng().register_module("x", "DATA", now=T0, commit=True)
    assert m.record_hash.startswith("sha256:")


# ══════════════ discover_modules (complete module discovery) ══════════════
def test_discover_registers_all(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ms = _eng().discover_modules(T0, commit=True)
    expected = len(ledger.catalog_modules())
    assert len(ms) == expected
    assert len(ledger.read_modules()) == expected


def test_discover_creates_catalog(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().discover_modules(T0, commit=True)
    assert len(ledger.read_catalog()) == len(ledger.catalog_modules())


def test_discover_covers_ten_domains(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().discover_modules(T0, commit=True)
    doms = {m["domain"] for m in ledger.read_modules()}
    assert doms == set(DOMAINS)


def test_discover_deterministic_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    ms = _eng().discover_modules(T0, commit=False)
    doms = [m.domain for m in ms]
    assert doms == sorted(doms)


def test_discover_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    e.discover_modules(T1, commit=True)
    assert len(ledger.read_modules()) == len(ledger.catalog_modules())


def test_discover_includes_p10_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    names = {m.name for m in _eng().discover_modules(T0, commit=True)}
    for layer in ("research_control_plane", "research_api", "knowledge_intelligence",
                  "governance_orchestration", "research_lifecycle", "self_audit_intelligence",
                  "research_risk_intelligence"):
        assert layer in names


def test_discover_includes_p9_layers(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    names = {m.name for m in _eng().discover_modules(T0, commit=True)}
    assert "research_governance" in names
    assert "research_validation" in names


def test_discover_complete_status(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    ds = e.module_discovery_status()
    assert ds["complete"] is True
    assert ds["missing"] == []


def test_catalog_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e._register_catalog("DATA", "m", "f1.jsonl", "P", T0, commit=True)
    with pytest.raises(ImmutableCatalogError):
        e._register_catalog("DATA", "m", "f2.jsonl", "P", T1, commit=True)


def test_catalog_modules_count():
    # 10 도메인에 걸친 카탈로그 — P9.8~P10.29 대표 계층.
    assert len(ledger.catalog_modules()) >= 30


# ══════════════ 모듈 상태 ══════════════
def test_module_state_active(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _reg_active(e, sp, "x", "DATA", "src.jsonl")
    assert e._module_state(m.to_dict()) == STATE_ACTIVE


def test_module_state_empty(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "src.jsonl", [])
    e = _eng()
    m = e.register_module("x", "DATA", "P", "src.jsonl", "id", T0, commit=True)
    assert e._module_state(m.to_dict()) == STATE_EMPTY


def test_module_state_missing(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    m = _reg_missing(e, "x", "DATA")
    assert e._module_state(m.to_dict()) == STATE_MISSING


# ══════════════ dependency integrity ══════════════
def test_dependency_integrity_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().check_dependency_integrity()
    assert res["ok"] is True
    assert res["node_count"] == 10


def test_dependency_edge_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().check_dependency_integrity()["edge_count"] == len(M.DOMAIN_DEPS)


def test_domain_deps_acyclic():
    assert M.detect_cycle(list(M.DOMAIN_DEPS)) == []


def test_domain_deps_nodes_valid():
    nodes = set(DOMAINS)
    for a, b in M.DOMAIN_DEPS:
        assert a in nodes and b in nodes


def test_detect_cycle_pure():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []
    cyc = M.detect_cycle([("a", "b"), ("b", "a")])
    assert cyc and cyc[0] == cyc[-1]


def test_dependency_issues_pure():
    assert M.dependency_issues([("A", "B")], ["A", "B"]) == []
    iss = M.dependency_issues([("A", "Z")], ["A"])
    assert any("unknown_target" in i for i in iss)


def test_dependency_issues_cycle_flag():
    iss = M.dependency_issues([("A", "B"), ("B", "A")], ["A", "B"])
    assert any("dependency_cycle" in i for i in iss)


# ══════════════ governance compliance ══════════════
def test_compliance_ok_after_discover(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    assert e.check_governance_compliance()["ok"] is True


def test_compliance_missing_domain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)  # only 1 domain
    res = e.check_governance_compliance()
    assert res["ok"] is False
    assert any("missing_domain_catalog" in i or "missing_required_domain" in i
               for i in res["issues"])


def test_compliance_requires_audit_and_control(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    # register all catalog entries but no AUDIT/CONTROL registered modules
    for d in DOMAINS:
        e._register_catalog(d, f"m_{d}", "f.jsonl", "P", T0, commit=True)
    e.register_module("m_DATA", "DATA", now=T0, commit=True)
    res = e.check_governance_compliance()
    assert any("missing_required_domain:AUDIT" in i for i in res["issues"])


# ══════════════ build_os_snapshot (reproducibility) ══════════════
def test_snapshot_basic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "DATA", "src.jsonl")
    s = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert s.snapshot_id.startswith("OSN:")
    assert s.module_count == 1
    assert s.active_module_count == 1


def test_snapshot_per_domain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "DATA", "src.jsonl")
    s = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert s.per_domain["DATA"]["active"] == 1


def test_snapshot_reproducible(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "DATA", "src.jsonl")
    a = e.build_os_snapshot("GLOBAL", T1, commit=False)
    b = e.build_os_snapshot("GLOBAL", T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_snapshot_reproducible_diff_time_same_data(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "DATA", "src.jsonl")
    a = e.build_os_snapshot("GLOBAL", T1, commit=False)
    b = e.build_os_snapshot("GLOBAL", T2, commit=False)
    # snapshot_id 는 시각 포함하나 데이터 필드는 동일해야
    assert a.module_count == b.module_count
    assert a.per_domain == b.per_domain
    assert a.overall_score == b.overall_score


def test_snapshot_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("a", "DATA", now=T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.register_module("b", "MODEL", now=T0, commit=True)
    with pytest.raises(ImmutableSnapshotError):
        e.build_os_snapshot("GLOBAL", T1, commit=True)


def test_snapshot_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().build_os_snapshot("GLOBAL", T0, commit=True)
    assert "OBSERVE ≠ EXECUTE" in s.disclaimer


def test_snapshot_full_coverage_healthy(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _all_domains_active(e, sp)
    s = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert s.domain_coverage == 1.0
    assert s.health_level == HEALTH_HEALTHY


# ══════════════ calculate_os_health ══════════════
def test_health_all_active(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _all_domains_active(e, sp)
    h = e.calculate_os_health("GLOBAL", T1, commit=True)
    assert h.state_id.startswith("OSS:")
    assert h.overall_score == 1.0
    assert h.level == HEALTH_HEALTHY


def test_health_unknown_when_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    h = _eng().calculate_os_health("GLOBAL", T0, commit=True)
    assert h.level == HEALTH_UNKNOWN
    assert h.module_count == 0


def test_health_critical_none_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_missing(e, "x", "DATA")
    h = e.calculate_os_health("GLOBAL", T1, commit=True)
    # coverage 0, activity 0, integrity 1 -> 0.2 -> CRITICAL
    assert h.overall_score == round(0.2, 8)
    assert h.level == HEALTH_CRITICAL


def test_health_degraded(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    # 5/10 도메인 active, 모든 등록 모듈 active -> cov .5, act 1 -> .25+.3+.2=.75 DEGRADED
    for i, d in enumerate(DOMAINS[:5]):
        _reg_active(e, sp, f"m{i}", d, f"s{i}.jsonl")
    h = e.calculate_os_health("GLOBAL", T1, commit=True)
    assert h.overall_score == round(0.5 * 0.5 + 0.3 * 1.0 + 0.2, 8)
    assert h.level == HEALTH_DEGRADED


def test_health_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    a = e.calculate_os_health("GLOBAL", T1, commit=False)
    b = e.calculate_os_health("GLOBAL", T1, commit=False)
    assert a.overall_score == b.overall_score
    assert a.state_id == b.state_id


def test_health_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    assert len(ledger.read_state()) == 1


def test_health_immutable(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "a", "DATA", "s.jsonl")
    e.calculate_os_health("GLOBAL", T1, commit=True)
    _reg_active(e, sp, "b", "MODEL", "s2.jsonl")  # score 변화
    with pytest.raises(ImmutableStateError):
        e.calculate_os_health("GLOBAL", T1, commit=True)


def test_health_records_state(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    assert len(ledger.read_state()) == 1


def test_os_health_score_pure():
    assert M.os_health_score(1.0, 1.0, True) == 1.0
    assert M.os_health_score(0.0, 0.0, True) == round(0.2, 8)
    assert M.os_health_score(0.0, 0.0, False) == 0.0
    assert M.os_health_score(0.6, 1.0, True) == round(0.5 * 0.6 + 0.3 + 0.2, 8)


def test_health_level_pure():
    assert M.health_level(0.9, 5) == HEALTH_HEALTHY
    assert M.health_level(0.6, 5) == HEALTH_DEGRADED
    assert M.health_level(0.2, 5) == HEALTH_CRITICAL
    assert M.health_level(0.9, 0) == HEALTH_UNKNOWN


def test_domain_coverage_pure():
    assert M.domain_coverage(5, 10) == 0.5
    assert M.domain_coverage(0, 0) == 0.0


# ══════════════ generate_global_report ══════════════
def test_report_basic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "DATA", "src.jsonl")
    r = e.generate_global_report("GLOBAL", {"k": 1}, T1, commit=True)
    assert r.report_id.startswith("OSR:")
    assert r.module_count == 1
    assert r.metrics["k"] == 1


def test_report_dependency_and_compliance_flags(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    r = e.generate_global_report("GLOBAL", {}, T1, commit=True)
    assert r.dependency_ok is True
    assert r.compliance_ok is True


def test_report_per_domain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "x", "KNOWLEDGE", "src.jsonl")
    r = e.generate_global_report("GLOBAL", {}, T1, commit=True)
    assert "KNOWLEDGE" in r.per_domain


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    a = e.generate_global_report("GLOBAL", {}, T1, commit=False)
    b = e.generate_global_report("GLOBAL", {}, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    e.generate_global_report("GLOBAL", {}, T1, commit=True)
    e.generate_global_report("GLOBAL", {}, T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_global_report("GLOBAL", {}, T0, commit=True)
    assert "REPORT ≠ TRADE" in r.disclaimer


def test_report_phase_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", "P9.10", now=T0, commit=True)
    r = e.generate_global_report("GLOBAL", {}, T1, commit=True)
    assert r.phase_distribution.get("P9.10") == 1


# ══════════════ verify_all_integrity (no execution path etc.) ══════════════
def test_verify_all_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().verify_all_integrity()
    assert res["ok"] is True
    assert res["dependency"]["ok"] is True


def test_verify_all_after_full_flow(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    e.generate_global_report("GLOBAL", {}, T1, commit=True)
    res = e.verify_all_integrity()
    assert res["ok"] is True
    assert res["compliance"]["ok"] is True
    assert res["discovery"]["complete"] is True


def test_verify_all_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    p = sp("rosc_registry.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[0]["domain"] = "MODEL"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert e.verify_all_integrity()["ok"] is False


def test_verify_all_detects_chain_break(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("a", "DATA", now=T0, commit=True)
    e.register_module("b", "MODEL", now=T0, commit=True)
    p = sp("rosc_registry.jsonl")
    rows = [json.loads(x) for x in open(p)]
    rows[1]["previous_hash"] = "GENESIS"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    assert e.verify_all_integrity()["ok"] is False


def test_verify_all_includes_all_sections(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().verify_all_integrity()
    for key in ("chain", "dependency", "compliance", "discovery"):
        assert key in res


def test_verify_chain_per_ledger(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os_core.verify import verify_chain
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    res = verify_chain()
    assert "rosc_registry.jsonl" in res["ledgers"]


def test_module_discovery_status_incomplete(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("data_governance", "DATA", now=T0, commit=True)
    ds = e.module_discovery_status()
    assert ds["complete"] is False
    assert len(ds["missing"]) > 0


# ══════════════ replay / summary ══════════════
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_os_core.verify import replay
    e = _eng()
    e.discover_modules(T0, commit=True)
    assert replay(e, T1)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    e.generate_global_report("GLOBAL", {}, T1, commit=True)
    s = e.summary(T2)
    assert s.module_count == 1
    assert s.snapshot_count == 1
    assert s.state_count == 1
    assert s.report_count == 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    assert e.summary(T1).to_dict() == e.summary(T1).to_dict()


# ══════════════ query helpers ══════════════
def test_list_modules_by_domain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("a", "DATA", now=T0, commit=True)
    e.register_module("b", "MODEL", now=T0, commit=True)
    assert e.list_modules("DATA") == ["a"]
    assert sorted(e.list_modules()) == ["a", "b"]


def test_domains_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("a", "DATA", now=T0, commit=True)
    e.register_module("b", "AUDIT", now=T0, commit=True)
    assert e.domains_present() == ["AUDIT", "DATA"]


def test_latest_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("a", "DATA", now=T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert e.latest_snapshot("GLOBAL") is not None


# ══════════════ 상위 READ ONLY 보호 ══════════════
def test_source_never_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "ki_insights.jsonl", [{"insight_id": "i1"}])
    before = open(sp("ki_insights.jsonl")).read()
    e = _eng()
    e.discover_modules(T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    assert open(sp("ki_insights.jsonl")).read() == before


def test_no_source_created(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", "P", "ai_signals.jsonl", "id", T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)  # source missing
    assert not os.path.exists(sp("ai_signals.jsonl"))


def test_only_rosc_files_written(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    e.build_os_snapshot("GLOBAL", T1, commit=True)
    e.calculate_os_health("GLOBAL", T1, commit=True)
    e.generate_global_report("GLOBAL", {}, T1, commit=True)
    for fn in os.listdir(tmp_path):
        assert fn.startswith("rosc_"), fn


# ══════════════ 보안 / 불변식 (no execution path) ══════════════
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


def test_engine_no_execution_methods():
    e = ResearchOSCoreEngine()
    for bad in ("execute", "trade", "deploy", "allocate", "modify", "place_order", "activate",
                "approve", "promote", "liquidate", "rebalance", "submit_order"):
        assert not hasattr(e, bad), bad


def test_engine_required_functions():
    e = ResearchOSCoreEngine()
    for name in ("register_module", "build_os_snapshot", "calculate_os_health",
                 "generate_global_report", "verify_all_integrity"):
        assert hasattr(e, name), name


def test_no_delete_or_update_api():
    import inspect
    src = inspect.getsource(ledger)
    for bad in ("def delete", "def update", "def remove", "def overwrite", "def edit_"):
        assert bad not in src, bad


def test_ledger_only_appends():
    import inspect
    src = inspect.getsource(ledger)
    assert '"a"' in src
    assert 'open(p, "w"' not in src


def test_no_execution_path_in_source():
    base = os.path.dirname(os.path.dirname(__file__))
    for fn in ("engine.py", "models.py", "__main__.py"):
        src = open(os.path.join(base, fn)).read()
        for bad in ("def execute", "def trade", "def deploy", "def allocate", "def modify_",
                    "def place_order"):
            assert bad not in src, (fn, bad)


def test_disclaimer_marks_observe_only():
    from jarvis.research_os_core.engine import _DISCLAIMER
    assert "OBSERVE ≠ EXECUTE" in _DISCLAIMER
    assert "REPORT ≠ TRADE" in _DISCLAIMER


def test_records_frozen():
    m = M.ModuleRecord(module_id="OSM:x", name="a", domain="DATA", phase="P", ledger_file="",
                       id_field="", registered_at=T0)
    with pytest.raises(Exception):
        m.domain = "MODEL"  # type: ignore


# ══════════════ 커버리지: id 접두사·상수 ══════════════
def test_id_prefixes_distinct():
    ids = {M.module_id("x")[:4], M.catalog_id("d", "m")[:4], M.state_id("x", T0)[:4],
           M.snapshot_id("x", T0)[:4], M.report_id("x", T0)[:4]}
    assert len(ids) == 5


def test_five_owned_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5
    fns = {l[0] for l in ledger.ALL_LEDGERS}
    assert len(fns) == 5
    assert all(f.startswith("rosc_") for f in fns)


def test_ten_domains():
    assert len(DOMAINS) == 10
    assert set(DOMAINS) == {"DATA", "MODEL", "ALPHA", "PORTFOLIO", "SIMULATION", "DECISION",
                            "AGENT", "KNOWLEDGE", "AUDIT", "CONTROL_PLANE"}


def test_catalog_covers_all_domains():
    cat_domains = {row[0] for row in ledger.catalog_modules()}
    assert cat_domains == set(DOMAINS)


def test_three_states():
    assert len(M.STATES) == 3


def test_four_health_levels():
    assert len(M.HEALTH_LEVELS) == 4


def test_content_hash_excludes_hash_fields():
    r = {"a": 1, "previous_hash": "p", "record_hash": "r"}
    assert M.content_hash(r) == M.content_hash({"a": 1, "previous_hash": "z", "record_hash": "q"})


def test_input_digest_deterministic():
    assert M.input_digest("a", "b") == M.input_digest("a", "b")
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_catalog_module_filenames_unique():
    files = [row[2] for row in ledger.catalog_modules()]
    assert len(files) == len(set(files))


def test_catalog_module_names_unique():
    names = [row[1] for row in ledger.catalog_modules()]
    assert len(names) == len(set(names))


def test_control_plane_domain_richest():
    # Control Plane 도메인이 최상위 조율 계층들을 포함
    cp = [row[1] for row in ledger.catalog_modules() if row[0] == "CONTROL_PLANE"]
    assert "research_control_plane" in cp
    assert "research_api" in cp
    assert "research_os" in cp


# ══════════════ CLI ══════════════
def _run(argv, capsys):
    from jarvis.research_os_core.__main__ import main
    rc = main(argv)
    return rc, capsys.readouterr().out


def test_cli_discover(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["discover", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["count"] == len(ledger.catalog_modules())


def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["register", "--name", "x", "--domain", "DATA", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["module"]["domain"] == "DATA"


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["snapshot", "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["snapshot"]["snapshot_id"].startswith("OSN:")


def test_cli_health(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["register", "--name", "x", "--domain", "DATA", "--commit"], capsys)
    rc, out = _run(["health", "--commit"], capsys)
    assert rc == 0
    assert "health" in json.loads(out)


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["report", "--metrics-json", '{"k":1}', "--commit"], capsys)
    assert rc == 0
    assert json.loads(out)["report"]["metrics"]["k"] == 1


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["verify"], capsys)
    assert rc == 0
    assert json.loads(out)["ok"] is True


def test_cli_modules(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["discover", "--commit"], capsys)
    rc, out = _run(["modules", "--domain", "CONTROL_PLANE"], capsys)
    assert rc == 0
    assert "research_api" in json.loads(out)["modules"]


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _run(["discover", "--commit"], capsys)
    rc, out = _run(["replay"], capsys)
    assert rc == 0
    assert json.loads(out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    rc, out = _run(["summary"], capsys)
    assert rc == 0
    assert "module_count" in json.loads(out)


# ══════════════ 파라미터화 커버리지 (도메인·카탈로그·헬스) ══════════════
@pytest.mark.parametrize("domain", list(DOMAINS))
def test_register_each_domain(tmp_path, monkeypatch, domain):
    _iso(tmp_path, monkeypatch)
    m = _eng().register_module(f"m_{domain}", domain, "P", now=T0, commit=True)
    assert m.domain == domain
    assert ledger.get_module(m.module_id)["domain"] == domain


@pytest.mark.parametrize("domain", list(DOMAINS))
def test_each_domain_has_catalog_module(domain):
    mods = [row for row in ledger.catalog_modules() if row[0] == domain]
    assert len(mods) >= 1


@pytest.mark.parametrize("domain", list(DOMAINS))
def test_discover_registers_domain_modules(tmp_path, monkeypatch, domain):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    assert domain in {m["domain"] for m in ledger.read_modules()}
    assert len(e.list_modules(domain)) >= 1


@pytest.mark.parametrize("cov,act,integ,expect", [
    (1.0, 1.0, True, 1.0),
    (0.0, 0.0, True, round(0.2, 8)),
    (0.0, 0.0, False, 0.0),
    (0.6, 1.0, True, round(0.5 * 0.6 + 0.3 + 0.2, 8)),
    (1.0, 0.0, True, round(0.5 + 0.2, 8)),
    (0.5, 0.5, True, round(0.25 + 0.15 + 0.2, 8)),
])
def test_os_health_score_param(cov, act, integ, expect):
    assert M.os_health_score(cov, act, integ) == expect


@pytest.mark.parametrize("score,n,expect", [
    (1.0, 5, HEALTH_HEALTHY), (0.8, 5, HEALTH_HEALTHY), (0.79, 5, HEALTH_DEGRADED),
    (0.5, 5, HEALTH_DEGRADED), (0.49, 5, HEALTH_CRITICAL), (0.0, 5, HEALTH_CRITICAL),
    (0.9, 0, HEALTH_UNKNOWN),
])
def test_health_level_param(score, n, expect):
    assert M.health_level(score, n) == expect


@pytest.mark.parametrize("phase", ["P10.23", "P10.24", "P10.25", "P10.26", "P10.27", "P10.28",
                                   "P10.29"])
def test_catalog_includes_recent_phase(phase):
    phases = {row[4] for row in ledger.catalog_modules()}
    assert phase in phases


@pytest.mark.parametrize("which", list(ledger.ALL_LEDGERS))
def test_each_ledger_reads_empty(tmp_path, monkeypatch, which):
    _iso(tmp_path, monkeypatch)
    assert ledger.read_jsonl(which[0]) == []


@pytest.mark.parametrize("record_cls,kwargs", [
    (M.ModuleRecord, dict(module_id="OSM:x", name="a", domain="DATA", phase="P", ledger_file="",
                          id_field="", registered_at=T0)),
    (M.CatalogRecord, dict(catalog_id="OSC:x", domain="DATA", module="m", ledger_file="f",
                           phase="P", created_at=T0)),
    (M.GlobalStateRecord, dict(state_id="OSS:x", scope="G", module_count=0, active_module_count=0,
                               covered_domains=0, domain_coverage=0.0, module_activity=0.0,
                               integrity_ok=True, overall_score=0.2, level="CRITICAL",
                               computed_at=T0)),
    (M.SnapshotRecord, dict(snapshot_id="OSN:x", scope="G", module_count=0, active_module_count=0,
                            domain_count=0, covered_domains=0, domain_coverage=0.0, per_domain={},
                            overall_score=0.2, health_level="CRITICAL", phase_distribution={},
                            disclaimer="d", snapshot_at=T0)),
])
def test_records_have_to_dict(record_cls, kwargs):
    r = record_cls(**kwargs)
    d = r.to_dict()
    assert isinstance(d, dict)
    assert d[record_cls.__dataclass_fields__["previous_hash"].name] == "GENESIS"


def test_per_domain_multiple_modules(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "a1", "KNOWLEDGE", "s1.jsonl")
    _reg_active(e, sp, "a2", "KNOWLEDGE", "s2.jsonl")
    _reg_missing(e, "a3", "KNOWLEDGE", "miss.jsonl")
    snap = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert snap.per_domain["KNOWLEDGE"]["total"] == 3
    assert snap.per_domain["KNOWLEDGE"]["active"] == 2


def test_discover_deterministic_ids(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e1 = _eng()
    e1.discover_modules(T0, commit=True)
    ids1 = {m["module_id"] for m in ledger.read_modules()}
    e2 = _eng()
    ids2 = {m.module_id for m in e2.discover_modules(T0, commit=False)}
    assert ids1 == ids2


def test_snapshot_domain_count_after_discover(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.discover_modules(T0, commit=True)
    snap = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert snap.domain_count == 10


def test_health_covered_domains_field(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "a", "DATA", "s1.jsonl")
    _reg_active(e, sp, "b", "MODEL", "s2.jsonl")
    h = e.calculate_os_health("GLOBAL", T1, commit=True)
    assert h.covered_domains == 2


def test_catalog_get_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    c = e._register_catalog("DATA", "m", "f.jsonl", "P", T0, commit=True)
    assert ledger.get_catalog(c.catalog_id)["module"] == "m"


def test_report_covered_domains(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    e = _eng()
    _reg_active(e, sp, "a", "AUDIT", "s.jsonl")
    r = e.generate_global_report("GLOBAL", {}, T1, commit=True)
    assert r.covered_domains == 1


def test_verify_all_dependency_node_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().verify_all_integrity()
    assert res["dependency"]["node_count"] == 10


def test_state_get_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    h = e.calculate_os_health("GLOBAL", T1, commit=True)
    assert ledger.get_state(h.state_id) is not None


def test_snapshot_get_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    e.register_module("x", "DATA", now=T0, commit=True)
    s = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert ledger.get_snapshot(s.snapshot_id) is not None


def test_report_get_helper(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e = _eng()
    r = e.generate_global_report("GLOBAL", {}, T0, commit=True)
    assert ledger.get_report(r.report_id) is not None


def test_source_count_helper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _seed(sp, "s.jsonl", [{"a": 1}, {"a": 2}])
    assert ledger.source_count("s.jsonl") == 2
    assert ledger.source_count("missing.jsonl") == 0


def test_all_catalog_phases_p9_or_p10():
    for row in ledger.catalog_modules():
        assert row[4].startswith("P9.") or row[4].startswith("P10.")


def test_domains_present_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().domains_present() == []


def test_list_modules_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_modules() == []


def test_latest_snapshot_none(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().latest_snapshot("GLOBAL") is None


def test_snapshot_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().build_os_snapshot("GLOBAL", T0, commit=False)
    assert ledger.read_snapshots() == []


def test_health_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().calculate_os_health("GLOBAL", T0, commit=False)
    assert ledger.read_state() == []


def test_report_no_commit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().generate_global_report("GLOBAL", {}, T0, commit=False)
    assert ledger.read_reports() == []


def test_control_plane_module_count():
    cp = [row for row in ledger.catalog_modules() if row[0] == "CONTROL_PLANE"]
    assert len(cp) >= 10  # 최상위 조율 계층 집합


def test_knowledge_domain_modules():
    kn = {row[1] for row in ledger.catalog_modules() if row[0] == "KNOWLEDGE"}
    assert "research_kg" in kn
    assert "knowledge_intelligence" in kn


def test_audit_domain_modules():
    au = {row[1] for row in ledger.catalog_modules() if row[0] == "AUDIT"}
    assert "research_compliance" in au
    assert "research_risk_intelligence" in au


# ══════════════ 통합 시나리오 (Phase 10 완성) ══════════════
def test_end_to_end_phase10(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 여러 도메인 소스 시드
    seeds = {
        "ai_signals.jsonl": [{"signal_hash": "s1"}],
        "ki_insights.jsonl": [{"insight_id": "i1"}],
        "rcp_overview.jsonl": [{"overview_id": "o1"}],
        "rapi_endpoints.jsonl": [{"endpoint_id": "e1"}],
        "sa_audits.jsonl": [{"audit_id": "a1"}],
        "rr_assessments.jsonl": [{"assessment_id": "r1"}],
    }
    for fn, rows in seeds.items():
        _seed(sp, fn, rows)
    e = _eng()
    ms = e.discover_modules(T0, commit=True)
    assert len(ms) == len(ledger.catalog_modules())
    snap = e.build_os_snapshot("GLOBAL", T1, commit=True)
    assert snap.domain_count == 10
    assert snap.active_module_count >= 6
    health = e.calculate_os_health("GLOBAL", T1, commit=True)
    assert health.level in ("HEALTHY", "DEGRADED", "CRITICAL")
    report = e.generate_global_report("GLOBAL", {"phase": 10}, T1, commit=True)
    assert report.dependency_ok is True
    assert report.compliance_ok is True
    res = e.verify_all_integrity()
    assert res["ok"] is True
    assert res["discovery"]["complete"] is True


def test_end_to_end_deterministic_snapshot(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    e1 = _eng()
    e1.discover_modules(T0, commit=True)
    s1 = e1.build_os_snapshot("GLOBAL", T1, commit=False)
    e2 = _eng()
    e2.discover_modules(T0, commit=False)
    s2 = e2.build_os_snapshot("GLOBAL", T1, commit=False)
    assert s1.per_domain == s2.per_domain
    assert s1.overall_score == s2.overall_score
