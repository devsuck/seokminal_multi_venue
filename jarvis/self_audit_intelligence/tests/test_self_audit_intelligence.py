"""P10.24 Research Self Audit Intelligence 테스트. **전 생태계 무결성 메타 감사(READ ONLY) 전용.**

감사 정의(불변)·감사 실행(생명주기 CREATED→RUNNING→COMPLETED→ARCHIVED)·무결성 점검(PASS/WARNING/CRITICAL)·
위반 기록·감사 리포트(overall 롤업·결정적)·5대 탐지(깨진 해시체인·누락 부모·유효하지 않은 생명주기·미문서화
변경·누락 검증)·replay·상위 READ ONLY 보호·CLI·보안(금지import·repair/modify/fix/apply/deploy 없음·상위 원장
무변경·삭제 API 없음·불변·AUDIT≠REPAIR·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.self_audit_intelligence import ledger
from jarvis.self_audit_intelligence import models as M
from jarvis.self_audit_intelligence.engine import ResearchSelfAuditEngine
from jarvis.self_audit_intelligence.models import (
    ARCHIVED,
    COMPLETED,
    CREATED,
    CRITICAL,
    PASS,
    RUNNING,
    WARNING,
    IllegalTransition,
    UnknownRun,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"

# 대상 원장(감사 대상) — kind 별
L_CHAIN = "governance_memory"            # gm_entries.jsonl (chain)
F_CHAIN = "gm_entries.jsonl"
L_EVENT = "governance_orchestration"     # go_layers.jsonl (event)
F_EVENT = "go_layers.jsonl"
L_ART = "governance_orchestration_lineage"  # go_artifacts.jsonl (artifact)
F_ART = "go_artifacts.jsonl"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.self_audit_intelligence.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchSelfAuditEngine()


def _write_chain(sp, filename, cores):
    """정상 해시체인으로 대상 원장 작성(created_at 포함)."""
    prev = "GENESIS"
    with open(sp(filename), "w") as f:
        for c in cores:
            rec = dict(c)
            rec.setdefault("created_at", T0)
            rec["previous_hash"] = prev
            rec["record_hash"] = M.content_hash(rec)
            f.write(json.dumps(rec) + "\n")
            prev = rec["record_hash"]


def _run(eng, epoch="E1"):
    return eng.create_audit_run("ecosystem_integrity", "GLOBAL", None, epoch, T0, commit=True)


# ── Audit Run ──
def test_run_create(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _run(_eng())
    assert r.run_id.startswith("SAU:")
    assert r.to_state == CREATED


def test_run_registers_audit(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _run(_eng())
    assert len(ledger.read_audits()) == 1
    assert ledger.read_audits()[0]["audit_id"].startswith("SAA:")


def test_run_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_audit_run("x", "GLOBAL", None, "E1", T0, commit=False)
    assert ledger.read_run_events() == []


def test_run_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _run(_eng())
    assert r.run_id == M.run_id(M.audit_id("ecosystem_integrity"), "E1")


def test_run_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _run(eng)
    b = _run(eng)
    assert a.run_id == b.run_id
    assert len(ledger.distinct_runs()) == 1


def test_run_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng._advance_run(r.run_id, RUNNING, T1, commit=True)
    assert eng.run_state(r.run_id) == RUNNING
    eng._advance_run(r.run_id, COMPLETED, T2, commit=True)
    assert eng.run_state(r.run_id) == COMPLETED


def test_run_can_transition_table():
    assert M.can_transition_run("", CREATED)
    assert M.can_transition_run(CREATED, RUNNING)
    assert M.can_transition_run(RUNNING, COMPLETED)
    assert not M.can_transition_run(CREATED, COMPLETED)
    assert not M.can_transition_run(COMPLETED, RUNNING)


def test_run_illegal_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    meta = eng._run_meta(r.run_id)
    with pytest.raises(IllegalTransition):
        eng._emit_run_event(meta, CREATED, COMPLETED, T1, commit=True)


def test_scan_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().scan_layer_integrity("SAU:nope", L_CHAIN, T0, commit=True)


def test_run_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _run(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_RUN, r.run_id))


# ── scan_layer_integrity: hash chain ──
def test_scan_clean_chain_pass(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}, {"entry_id": "e2"}])
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    chain = next(c for c in checks if c.check_kind == M.CK_HASH_CHAIN)
    assert chain.result == PASS


def test_scan_advances_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    assert eng.run_state(r.run_id) == RUNNING


def test_scan_detects_broken_hash_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}, {"entry_id": "e2"}])
    # tamper: break previous_hash link on 2nd record
    rows = [json.loads(x) for x in open(sp(F_CHAIN)) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(sp(F_CHAIN), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    eng = _eng()
    run = _run(eng)
    checks = eng.scan_layer_integrity(run.run_id, L_CHAIN, T0, commit=True)
    chain = next(c for c in checks if c.check_kind == M.CK_HASH_CHAIN)
    assert chain.result == CRITICAL


def test_scan_detects_record_hash_mismatch(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    rows = [json.loads(x) for x in open(sp(F_CHAIN)) if x.strip()]
    rows[0]["entry_id"] = "TAMPERED"  # record_hash no longer matches
    with open(sp(F_CHAIN), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    eng = _eng()
    run = _run(eng)
    checks = eng.scan_layer_integrity(run.run_id, L_CHAIN, T0, commit=True)
    chain = next(c for c in checks if c.check_kind == M.CK_HASH_CHAIN)
    assert chain.result == CRITICAL


def test_scan_records_violation_on_critical(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    rows = [json.loads(x) for x in open(sp(F_CHAIN)) if x.strip()]
    rows[0]["record_hash"] = "sha256:wrong"
    with open(sp(F_CHAIN), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    eng = _eng()
    run = _run(eng)
    eng.scan_layer_integrity(run.run_id, L_CHAIN, T0, commit=True)
    assert len(ledger.violations_for(run.run_id)) >= 1


def test_scan_empty_target_pass(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    chain = next(c for c in checks if c.check_kind == M.CK_HASH_CHAIN)
    assert chain.result == PASS  # empty ledger has no integrity issues


def test_scan_unknown_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, "not_a_layer", T0, commit=True)
    assert checks[0].check_kind == M.CK_VALIDATION
    assert checks[0].result == WARNING


def test_scan_event_lifecycle_check(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_EVENT, [{"event_id": "ev1", "to_state": "REGISTERED", "from_state": ""}])
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, L_EVENT, T0, commit=True)
    assert any(c.check_kind == M.CK_LIFECYCLE for c in checks)


def test_scan_detects_invalid_lifecycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_EVENT, [{"event_id": "ev1", "to_state": "", "from_state": ""}])
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, L_EVENT, T0, commit=True)
    life = next(c for c in checks if c.check_kind == M.CK_LIFECYCLE)
    assert life.result == WARNING


def test_scan_check_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    checks = eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    chain = next(c for c in checks if c.check_kind == M.CK_HASH_CHAIN)
    assert chain.check_id == M.check_id(r.run_id, L_CHAIN, M.CK_HASH_CHAIN, "chain")


def test_scan_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    hc = [c for c in ledger.checks_for(r.run_id) if c["check_kind"] == M.CK_HASH_CHAIN]
    assert len(hc) == 1


# ── verify_lineage: missing parent ──
def test_verify_lineage_clean_pass(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": ""},
                             {"artifact_id": "A2", "parent_artifact": "A1"}])
    eng = _eng()
    r = _run(eng)
    c = eng.verify_lineage(r.run_id, L_ART, T0, commit=True)
    assert c.check_kind == M.CK_LINEAGE
    assert c.result == PASS


def test_verify_lineage_detects_missing_parent(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": "GHOST"}])
    eng = _eng()
    r = _run(eng)
    c = eng.verify_lineage(r.run_id, L_ART, T0, commit=True)
    assert c.result == CRITICAL
    assert "missing_parent" in c.detail


def test_verify_lineage_detects_cycle(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": "A2"},
                             {"artifact_id": "A2", "parent_artifact": "A1"}])
    eng = _eng()
    r = _run(eng)
    c = eng.verify_lineage(r.run_id, L_ART, T0, commit=True)
    assert c.result == CRITICAL
    assert any("cycle" in i for i in [c.detail])


def test_verify_lineage_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().verify_lineage("SAU:nope", L_ART, T0, commit=True)


# ── detect_missing_governance: missing validation ──
def test_missing_governance_all_absent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    checks = eng.detect_missing_governance(r.run_id, T0, commit=True)
    assert len(checks) == len(ledger.EXPECTED_GOVERNANCE_LAYERS)
    assert all(c.result == WARNING for c in checks)


def test_missing_governance_present_pass(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])  # governance_memory present
    eng = _eng()
    r = _run(eng)
    checks = eng.detect_missing_governance(r.run_id, T0, commit=True)
    gm = next(c for c in checks if c.layer == "governance_memory")
    assert gm.result == PASS


def test_missing_governance_empty_warning(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    open(sp(F_CHAIN), "w").close()  # empty file present
    eng = _eng()
    r = _run(eng)
    checks = eng.detect_missing_governance(r.run_id, T0, commit=True)
    gm = next(c for c in checks if c.layer == "governance_memory")
    assert gm.result == WARNING
    assert gm.detail == "governance_ledger_empty"


def test_missing_governance_records_violations(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    assert len(ledger.violations_for(r.run_id)) == len(ledger.EXPECTED_GOVERNANCE_LAYERS)


# ── detect_policy_drift: undocumented change ──
def test_drift_clean_pass(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    eng = _eng()
    r = _run(eng)
    c = eng.detect_policy_drift(r.run_id, L_CHAIN, T0, commit=True)
    assert c.check_kind == M.CK_DOCUMENTATION
    assert c.result == PASS


def test_drift_detects_undocumented(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # record missing created_at -> undocumented change
    with open(sp(F_CHAIN), "w") as f:
        rec = {"entry_id": "e1", "previous_hash": "GENESIS"}
        rec["record_hash"] = M.content_hash(rec)
        f.write(json.dumps(rec) + "\n")
    eng = _eng()
    r = _run(eng)
    c = eng.detect_policy_drift(r.run_id, L_CHAIN, T0, commit=True)
    assert c.result == WARNING
    assert "undocumented_change" in c.detail


def test_drift_unknown_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    c = eng.detect_policy_drift(r.run_id, "nope", T0, commit=True)
    assert c.check_kind == M.CK_VALIDATION


# ── generate_audit_report ──
def test_report_basic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert rep.report_id.startswith("SAP:")
    assert rep.check_count >= 1
    assert rep.overall_result == PASS


def test_report_completes_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    assert eng.run_state(r.run_id) == COMPLETED


def test_report_overall_critical(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": "GHOST"}])
    eng = _eng()
    r = _run(eng)
    eng.verify_lineage(r.run_id, L_ART, T0, commit=True)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert rep.overall_result == CRITICAL


def test_report_overall_warning(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)  # all WARNING
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert rep.overall_result == WARNING


def test_report_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    a = eng.generate_audit_report(r.run_id, T1, commit=False)
    b = eng.generate_audit_report(r.run_id, T1, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert "AUDIT ≠ REPAIR" in rep.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_unknown_run(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownRun):
        _eng().generate_audit_report("SAU:nope", T0, commit=True)


def test_report_distributions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert M.CK_VALIDATION in rep.check_kind_distribution
    assert WARNING in rep.check_result_distribution


def test_report_no_action_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_audit_report(_run(_eng()).run_id, T1, commit=True)
    d = rep.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("repair", "deploy", "place_order", "allocate_capital", "fix("):
        assert verb not in blob


# ── replay_audit ──
def test_replay_deterministic(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    res = _eng().replay_audit([L_CHAIN])
    assert res["deterministic"] is True
    assert res["overall_result"] == PASS


def test_replay_detects_overall(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": "GHOST"}])
    res = _eng().replay_audit([L_ART])
    assert res["overall_result"] == CRITICAL


def test_replay_all_targets(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    res = _eng().replay_audit(None)
    assert res["deterministic"] is True
    assert res["n_findings"] >= len(ledger.AUDIT_TARGETS)


# ── scan_all ──
def test_scan_all(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    eng = _eng()
    r = _run(eng)
    res = eng.scan_all(r.run_id, None, T0, commit=True)
    assert res["checks"] >= len(ledger.AUDIT_TARGETS)


def test_scan_all_then_report(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_all(r.run_id, None, T0, commit=True)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    # missing governance -> WARNING overall (no CRITICAL on empty ecosystem)
    assert rep.overall_result in (WARNING, PASS)
    assert eng.run_state(r.run_id) == COMPLETED


# ── pure-function detections ──
def test_audit_hash_chain_pass():
    prev = "GENESIS"
    recs = []
    for i in range(3):
        rec = {"id": f"r{i}", "previous_hash": prev}
        rec["record_hash"] = M.content_hash(rec)
        recs.append(rec)
        prev = rec["record_hash"]
    assert M.audit_hash_chain(recs, "id")["result"] == PASS


def test_audit_hash_chain_empty_pass():
    assert M.audit_hash_chain([])["result"] == PASS


def test_audit_hash_chain_broken():
    recs = [{"id": "r0", "previous_hash": "GENESIS", "record_hash": "x"}]
    assert M.audit_hash_chain(recs, "id")["result"] == CRITICAL


def test_audit_lineage_pass():
    recs = [{"artifact_id": "A", "parent_artifact": ""},
            {"artifact_id": "B", "parent_artifact": "A"}]
    assert M.audit_lineage(recs)["result"] == PASS


def test_audit_lineage_missing_parent():
    recs = [{"artifact_id": "A", "parent_artifact": "GHOST"}]
    assert M.audit_lineage(recs)["result"] == CRITICAL


def test_audit_lifecycle_pass():
    recs = [{"to_state": "X"}, {"to_state": "Y"}]
    assert M.audit_lifecycle(recs)["result"] == PASS


def test_audit_lifecycle_empty_to_state():
    recs = [{"to_state": ""}]
    assert M.audit_lifecycle(recs)["result"] == WARNING


def test_audit_documentation_pass():
    recs = [{"created_at": T0, "record_hash": "h"}]
    assert M.audit_documentation(recs)["result"] == PASS


def test_audit_documentation_undocumented():
    recs = [{"record_hash": "h"}]  # missing created_at
    assert M.audit_documentation(recs)["result"] == WARNING


def test_worst_result():
    assert M.worst_result([PASS, WARNING, CRITICAL]) == CRITICAL
    assert M.worst_result([PASS, WARNING]) == WARNING
    assert M.worst_result([PASS]) == PASS
    assert M.worst_result([]) == PASS


def test_result_rank():
    assert M.result_rank(CRITICAL) > M.result_rank(WARNING) > M.result_rank(PASS)


# ── verify (self) ──
def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    from jarvis.self_audit_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_self_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _run(_eng())
    p = sp("sa_audits.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["scope"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.self_audit_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.AUDITS)["ok"] is False


def test_verify_detects_self_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    p = sp("sa_checks.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(p, "w") as f:
        for row in rows:
            f.write(json.dumps(row) + "\n")
    from jarvis.self_audit_intelligence.verify import verify_ledger
    assert verify_ledger(ledger.CHECKS)["ok"] is False


def test_verify_run_transitions_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    from jarvis.self_audit_intelligence.verify import run_transition_validation
    assert run_transition_validation()["ok"] is True


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_all(r.run_id, None, T0, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    from jarvis.self_audit_intelligence.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["run_transitions"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_self_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    from jarvis.self_audit_intelligence.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── summary / analyze ──
def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    eng.generate_audit_report(r.run_id, T1, commit=True)
    s = eng.summary(T0)
    assert s.audit_count >= 1
    assert s.run_count >= 1
    assert s.check_count >= 1
    assert s.violation_count >= 1
    assert s.report_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_analyze(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    res = eng.analyze(r.run_id)
    assert res["overall_result"] == WARNING
    assert res["violation_count"] >= 1


# ── 상위 READ ONLY ──
def test_target_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    before = open(sp(F_CHAIN)).read()
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    eng.detect_policy_drift(r.run_id, L_CHAIN, T0, commit=True)
    assert open(sp(F_CHAIN)).read() == before  # 원본 무변경


def test_target_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}, {"entry_id": "e2"}])
    assert ledger.target_count(L_CHAIN) == 2
    assert ledger.target_count("nope") == 0


def test_target_exists(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    assert ledger.target_exists(L_CHAIN) is False
    open(sp(F_CHAIN), "w").close()
    assert ledger.target_exists(L_CHAIN) is True


def test_audit_targets_cover_all_layers():
    for layer in ("data_governance", "research_compliance", "governance_orchestration",
                  "governance_evolution", "research_os"):
        assert layer in ledger.AUDIT_TARGETS


# ── CLI ──
def test_cli_run(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    rc = main(["run", "--epoch", "E1", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["run"]["run_id"].startswith("SAU:")


def test_cli_scan(tmp_path, monkeypatch, capsys):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    from jarvis.self_audit_intelligence.__main__ import main
    main(["run", "--epoch", "E1", "--commit"])
    rid = json.loads(capsys.readouterr().out)["run"]["run_id"]
    rc = main(["scan", "--run-ref", rid, "--layer", L_CHAIN, "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["checks"][0]["check_id"].startswith("SAC:")


def test_cli_missing(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    main(["run", "--epoch", "E1", "--commit"])
    rid = json.loads(capsys.readouterr().out)["run"]["run_id"]
    rc = main(["missing", "--run-ref", rid, "--commit"])
    assert rc == 0
    assert len(json.loads(capsys.readouterr().out)["checks"]) >= 1


def test_cli_scan_all(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    main(["run", "--epoch", "E1", "--commit"])
    rid = json.loads(capsys.readouterr().out)["run"]["run_id"]
    rc = main(["scan-all", "--run-ref", rid, "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["scan_all"]["checks"] >= 1


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    main(["run", "--epoch", "E1", "--commit"])
    rid = json.loads(capsys.readouterr().out)["run"]["run_id"]
    rc = main(["report", "--run-ref", rid, "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("SAP:")


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    main(["run", "--epoch", "E1", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.self_audit_intelligence.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "audit_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.self_audit_intelligence.engine as eng_mod
    import jarvis.self_audit_intelligence.models as mdl_mod
    import jarvis.self_audit_intelligence.ledger as led_mod
    import jarvis.self_audit_intelligence.verify as ver_mod
    import jarvis.self_audit_intelligence.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_repair_methods():
    import jarvis.self_audit_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def repair", "def modify", "def fix", "def apply", "def deploy",
               "def execute", "def trade"):
        assert kw not in src


def test_no_repair_authority_api():
    api = set(dir(ResearchSelfAuditEngine))
    for banned in ("repair", "modify", "fix", "apply", "deploy", "execute", "trade",
                   "allocate", "place_order"):
        assert banned not in api


def test_audit_not_repair(tmp_path, monkeypatch):
    """점검 레코드에 repair/fix/apply/modify 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    checks = eng.detect_missing_governance(r.run_id, T0, commit=True)
    d = checks[0].to_dict()
    for banned in ("repair", "fix", "apply", "modify", "deploy"):
        assert banned not in d


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.scan_all(r.run_id, None, T0, commit=True)
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.self_audit_intelligence.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_sa(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("sa_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 6


def test_engine_no_upstream_layer_import():
    import jarvis.self_audit_intelligence.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.governance_orchestration", "import jarvis.governance_evolution",
               "import jarvis.research_compliance", "import jarvis.data_governance"):
        assert up not in src


def test_target_ledgers_not_sa_prefixed():
    for layer, spec in ledger.AUDIT_TARGETS.items():
        assert not spec[0].startswith("sa_")


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.audit_id("a")[:4],
        M.run_id("a", "b")[:4],
        M.run_event_id("a", "", CREATED)[:4],
        M.check_id("a", "b", "c", "d")[:4],
        M.violation_id("a", "b", "c", "d")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 7


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_results_count():
    assert len(M.RESULTS) == 3


def test_check_kinds_count():
    assert len(M.CHECK_KINDS) == 5


def test_run_states_count():
    assert len(M.RUN_STATES) == 4


def test_node_types_count():
    assert len(M.NODE_TYPES) == 5


def test_expected_governance_layers():
    assert "governance_orchestration" in ledger.EXPECTED_GOVERNANCE_LAYERS
    assert "data_governance" in ledger.EXPECTED_GOVERNANCE_LAYERS


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_audit_run("x", "GLOBAL", None, "E1", T0, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_run_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _run(_eng())
    d = r.to_dict()
    assert d["run_id"] == r.run_id
    assert set(("audit_ref", "scope", "epoch")).issubset(d)


def test_check_evidence_kept(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_ART, [{"artifact_id": "A1", "parent_artifact": "GHOST"}])
    eng = _eng()
    r = _run(eng)
    c = eng.verify_lineage(r.run_id, L_ART, T0, commit=True)
    assert len(c.evidence) >= 1


def test_violation_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    r = _run(eng)
    eng.detect_missing_governance(r.run_id, T0, commit=True)
    v = ledger.violations_for(r.run_id)[0]
    assert v["violation_id"] == M.violation_id(r.run_id, v["layer"], v["check_kind"], v["locus"])


def test_audit_immutable_metadata(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_audit_run("aud1", "GLOBAL", ["l1"], "E1", T0, commit=True)
    # same name re-register returns existing (idempotent), even if targets differ
    adef = eng._register_audit("aud1", "GLOBAL", ["l1", "l2"], T0, commit=True)
    assert adef["target_layers"] == ["l1"]


def test_report_layers_scanned(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    eng = _eng()
    r = _run(eng)
    eng.scan_layer_integrity(r.run_id, L_CHAIN, T0, commit=True)
    rep = eng.generate_audit_report(r.run_id, T1, commit=True)
    assert L_CHAIN in rep.layers_scanned


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.create_audit_run("a1", "GLOBAL", None, "E1", T0, commit=True)
    b = eng.create_audit_run("a2", "GLOBAL", None, "E1", T0, commit=True)
    assert a.run_id != b.run_id
    assert len(ledger.distinct_runs()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    rep = _eng().generate_audit_report(_run(_eng()).run_id, T1, commit=True)
    for phrase in ("AUDIT ≠ REPAIR", "FINDING ≠ FIX", "INSPECTION ≠ MODIFICATION",
                   "REPORT ≠ ACTION"):
        assert phrase in rep.disclaimer


def test_scan_all_detects_broken_upstream(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _write_chain(sp, F_CHAIN, [{"entry_id": "e1"}])
    rows = [json.loads(x) for x in open(sp(F_CHAIN)) if x.strip()]
    rows[0]["record_hash"] = "sha256:wrong"
    with open(sp(F_CHAIN), "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    eng = _eng()
    run = _run(eng)
    eng.scan_all(run.run_id, None, T0, commit=True)
    rep = eng.generate_audit_report(run.run_id, T1, commit=True)
    assert rep.overall_result == CRITICAL
