"""P9.7 Policy & Configuration Governance 테스트. **관리·감사 전용.**

정책 레지스트리(불변 버전·중복방지)·변경 워크플로(상태머신·차단전이)·승인 거버넌스·스냅샷·drift
(NO/WARNING/CRITICAL)·거버넌스 리포트·verify(체인/변조/중복)·replay·CLI·보안(금지import·집행/브로커/
포트폴리오 없음·config/permission/autonomy 무변경·삭제 API 없음·append-only·불변).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.policy_governance import ledger
from jarvis.policy_governance import models as M
from jarvis.policy_governance.engine import PolicyGovernanceEngine
from jarvis.policy_governance.models import (
    ACTIVE,
    APPROVE,
    APPROVED,
    CRITICAL_DRIFT,
    DRAFT,
    NO_DRIFT,
    REJECT,
    REJECTED,
    REQUESTED,
    REVIEWED,
    WARNING_DRIFT,
    ApprovalError,
    DriftError,
    IllegalTransition,
    ImmutablePolicyError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.policy_governance.ledger.state_path", sp)
    return sp


def _eng():
    return PolicyGovernanceEngine()


def _reg(eng, pid="P1", ver="1", params=None, cat="risk", name=None, commit=True):
    return eng.register_policy(pid, name or f"{pid} name", cat, ver, params or {"x": 1},
                               f"{pid} desc", "author", T0, commit=commit)


# ── 1~10. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", DRAFT) and M.can_transition(DRAFT, REQUESTED)
    assert M.can_transition(REQUESTED, REVIEWED) and M.can_transition(REVIEWED, APPROVED)
    assert M.can_transition(APPROVED, ACTIVE) and M.can_transition(REVIEWED, REJECTED)


def test_can_transition_blocked():
    assert not M.can_transition(DRAFT, APPROVED)
    assert not M.can_transition(REQUESTED, ACTIVE)
    assert not M.can_transition(ACTIVE, REVIEWED)
    assert not M.can_transition(REJECTED, APPROVED)


def test_policy_hash_deterministic():
    a = M.policy_hash("P", "n", "risk", "1", {"a": 1}, "d")
    b = M.policy_hash("P", "n", "risk", "1", {"a": 1}, "d")
    assert a == b


def test_policy_hash_changes_on_params():
    a = M.policy_hash("P", "n", "risk", "1", {"a": 1}, "d")
    b = M.policy_hash("P", "n", "risk", "1", {"a": 2}, "d")
    assert a != b


def test_content_hash_excludes_hash_fields():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_change_id_deterministic():
    assert M.change_id("P", "h", "op") == M.change_id("P", "h", "op")
    assert M.change_id("P", "h", "op").startswith("PCR:")


def test_approval_id_deterministic():
    assert M.approval_id("C", "b", APPROVE) == M.approval_id("C", "b", APPROVE)


def test_configuration_hash_deterministic():
    ps = [{"policy_id": "A", "version": "1", "policy_hash": "h1"}]
    assert M.configuration_hash(ps) == M.configuration_hash(list(ps))


def test_compliance_score_pure():
    assert M.compliance_score(0, 0, 0) == 100
    assert M.compliance_score(1, 0, 0) == 66
    assert M.compliance_score(0, 1, 0) == 92
    assert M.compliance_score(0, 0, 3) == 94
    assert M.compliance_score(3, 0, 0) == 0


def test_is_valid_decision():
    assert M.is_valid_decision(APPROVE) and M.is_valid_decision(REJECT)
    assert not M.is_valid_decision("ENABLE_LIVE")


# ── 11~17. Policy Registry ──
def test_register_policy_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    d = _reg(_eng(), commit=False)
    assert d.policy_id == "P1" and d.version == "1" and d.policy_hash


def test_register_policy_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _reg(_eng())
    assert len(ledger.read_policies()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    _reg(eng)   # 동일 내용 → 멱등
    assert len(ledger.read_policies()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, params={"x": 1})
    with pytest.raises(ImmutablePolicyError):
        _reg(eng, params={"x": 999})   # 동일 id+version, 내용 상이 → 불변 위반


def test_register_new_version_allowed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, ver="1", params={"x": 1})
    _reg(eng, ver="2", params={"x": 2})
    assert len(ledger.read_policies()) == 2


def test_active_policies_latest_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, ver="1", params={"x": 1})
    _reg(eng, ver="2", params={"x": 2})
    active = eng._active_policies()
    assert len(active) == 1 and active[0]["version"] == "2"


def test_register_policy_hash_present(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _reg(_eng())
    assert ledger.read_policies()[0]["policy_hash"].startswith("sha256:")


# ── 18~26. Change Workflow ──
def test_create_change_request_draft(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    assert eng.current_status(cid) == DRAFT


def test_request_reaches_requested(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.request("P1", "sha256:new", "r", "op", T0, commit=True)
    assert eng.current_status(cid) == REQUESTED


def test_full_workflow_to_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.submit_change(cid, T0, commit=True)
    eng.review_change(cid, T0, commit=True)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    eng.activate_change(cid, T0, commit=True)
    assert eng.current_status(cid) == ACTIVE


def test_illegal_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.review_change(cid, T0, commit=True)   # DRAFT→REVIEWED 차단


def test_illegal_transition_from_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.submit_change(cid, T0, commit=True)
    eng.review_change(cid, T0, commit=True)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    eng.activate_change(cid, T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.submit_change(cid, T0, commit=True)   # ACTIVE 는 종료


def test_current_status_fold(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.review_change(cid, T0, commit=True)
    assert eng.current_status(cid) == REVIEWED


def test_change_event_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.request("P1", "sha256:new", "r", "op", T0, commit=True)
    assert len(ledger.change_events_for(cid)) == 2   # DRAFT + REQUESTED


def test_change_event_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)   # 동일 → 중복 방지
    assert len(ledger.change_events_for(cid)) == 1


def test_activate_is_record_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, params={"x": 1})
    before = ledger.read_policies()[0]["policy_hash"]
    cid = eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.submit_change(cid, T0, commit=True)
    eng.review_change(cid, T0, commit=True)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    eng.activate_change(cid, T0, commit=True)
    # ACTIVE 는 기록일 뿐 — 레지스트리 정책 실제 미변경
    assert ledger.read_policies()[0]["policy_hash"] == before
    assert len(ledger.read_policies()) == 1


# ── 27~35. Approval Governance ──
def _to_reviewed(eng, cid=None):
    cid = cid or eng.create_change_request("P1", "sha256:new", "r", "op", T0, commit=True)
    eng.submit_change(cid, T0, commit=True)
    eng.review_change(cid, T0, commit=True)
    return cid


def test_approve_requires_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = eng.request("P1", "sha256:new", "r", "op", T0, commit=True)   # REQUESTED
    with pytest.raises(IllegalTransition):
        eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)


def test_approve_missing_approver_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    with pytest.raises(ApprovalError):
        eng.approve_change(cid, "", APPROVE, now=T0, commit=True)


def test_approve_hash_mismatch_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    with pytest.raises(ApprovalError):
        eng.approve_change(cid, "boss", APPROVE, now=T0, expected_hash="sha256:WRONG",
                           commit=True)


def test_approve_hash_match_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    rec = eng.approve_change(cid, "boss", APPROVE, now=T0, expected_hash="sha256:new",
                             commit=True)
    assert rec["decision"] == APPROVE


def test_approve_records_approval(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    assert len(ledger.read_approvals()) == 1


def test_approve_transitions_to_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    assert eng.current_status(cid) == APPROVED


def test_reject_transitions_to_rejected(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", REJECT, now=T0, commit=True)
    assert eng.current_status(cid) == REJECTED


def test_approval_duplicate_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    # 동일 승인 재시도(이미 APPROVED) — 전이는 막히지만 승인 원장은 1건 유지
    try:
        eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    except IllegalTransition:
        pass
    assert len(ledger.read_approvals()) == 1


def test_approve_invalid_decision_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    with pytest.raises(ApprovalError):
        eng.approve_change(cid, "boss", "ENABLE_LIVE", now=T0, commit=True)


# ── 36~40. Snapshot ──
def test_snapshot_captures_versions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1", ver="2")
    s = eng.snapshot(T0)
    assert s.policy_versions == {"P1": "2"} and s.policy_count == 1


def test_snapshot_config_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    assert eng.snapshot(T0).configuration_hash.startswith("sha256:")


def test_snapshot_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    assert eng.snapshot(T0).snapshot_id == eng.snapshot(T1).snapshot_id


def test_snapshot_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    eng.snapshot(T0, commit=True)
    eng.snapshot(T1, commit=True)   # 동일 config → 중복 방지
    assert len(ledger.read_snapshots()) == 1


def test_snapshot_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().snapshot(T0)
    assert s.policy_count == 0 and s.policy_versions == {}


# ── 41~48. Drift ──
def test_drift_no_drift(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    snap = eng.snapshot(T0, commit=True)
    d = eng.detect_drift(T0, snapshot=snap)
    assert d.drift_level == NO_DRIFT and d.drift_detected is False


def test_drift_warning_on_added(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1", ver="1")
    snap = eng.snapshot(T0, commit=True)
    _reg(eng, pid="P2", ver="1")   # 스냅샷 이후 정책 추가
    d = eng.detect_drift(T0, snapshot=snap)
    assert d.drift_level == WARNING_DRIFT and d.drift_detected is True
    assert any("added:P2" in f for f in d.findings)


def test_drift_warning_on_changed_version(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1", ver="1", params={"x": 1})
    snap = eng.snapshot(T0, commit=True)
    _reg(eng, pid="P1", ver="2", params={"x": 2})
    d = eng.detect_drift(T0, snapshot=snap)
    assert d.drift_level == WARNING_DRIFT
    assert any("changed:P1" in f for f in d.findings)


def test_drift_critical_on_removed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1", ver="1")
    snap = eng.snapshot(T0, commit=True)
    d = eng.detect_drift(T0, snapshot=snap, current_active=[])   # 정책 사라짐
    assert d.drift_level == CRITICAL_DRIFT and d.drift_detected is True
    assert any("removed:P1" in f for f in d.findings)


def test_drift_no_snapshot_raises(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(DriftError):
        _eng().detect_drift(T0)


def test_drift_report_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    snap = eng.snapshot(T0, commit=True)
    d = eng.detect_drift(T0, snapshot=snap).to_dict()
    for k in ("snapshot_id", "expected_hash", "actual_hash", "drift_detected",
              "drift_level", "findings"):
        assert k in d


def test_drift_append_dedup(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    snap = eng.snapshot(T0, commit=True)
    eng.detect_drift(T0, snapshot=snap, commit=True)
    eng.detect_drift(T1, snapshot=snap, commit=True)   # 동일 상태 → 중복 방지
    assert len(ledger.read_drift_reports()) == 1


def test_drift_findings_list_empty_on_no_drift(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    snap = eng.snapshot(T0, commit=True)
    assert eng.detect_drift(T0, snapshot=snap).findings == []


# ── 49~53. Governance report ──
def test_governance_report_policy_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1")
    _reg(eng, pid="P2")
    assert eng.governance_report(T0).policy_count == 2


def test_governance_report_pending_changes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.request("P1", "sha256:new", "r", "op", T0, commit=True)   # REQUESTED = pending
    assert eng.governance_report(T0).pending_changes == 1


def test_governance_report_approved_changes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    assert eng.governance_report(T0).approved_changes == 1


def test_governance_report_drift_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1")
    snap = eng.snapshot(T0, commit=True)
    _reg(eng, pid="P2")
    eng.detect_drift(T0, snapshot=snap, commit=True)
    assert eng.governance_report(T0).drift_count == 1


def test_governance_report_score_deducts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, pid="P1")
    snap = eng.snapshot(T0, commit=True)
    eng.detect_drift(T0, snapshot=snap, current_active=[], commit=True)   # CRITICAL
    assert eng.governance_report(T0).compliance_score < 100


# ── 54~59. Verify / tamper / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.verify import verify_chain
    res = verify_chain()
    assert res["ok"] and res["n"] == 0


def test_verify_chain_intact_after_flow(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.verify import verify_chain
    eng = _eng()
    _reg(eng)
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    eng.snapshot(T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 4


def test_verify_detects_policy_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.verify import verify_chain
    _reg(_eng())
    path = sp("policies.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["parameters"] = {"x": 999}   # 콘텐츠 변조
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    res = verify_chain()
    assert res["ledgers"]["policies.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.verify import verify_chain
    eng = _eng()
    _reg(eng, ver="1", params={"x": 1})
    _reg(eng, ver="2", params={"x": 2})
    path = sp("policies.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    res = verify_chain()
    assert res["ledgers"]["policies.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.verify import verify_chain
    _reg(_eng())
    path = sp("policies.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    res = verify_chain()
    assert res["ledgers"]["policies.jsonl"]["reason"] in {"duplicate_id", "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    from jarvis.policy_governance.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 60~67. CLI ──
def test_cli_register(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.__main__ import main
    rc = main(["register", "--policy-id", "P1", "--name", "n", "--category", "risk",
               "--version", "1", "--by", "author", "--params-json", '{"x":1}', "--commit"])
    assert rc == 0 and "policy" in capsys.readouterr().out


def test_cli_request(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.__main__ import main
    rc = main(["request", "--policy-id", "P1", "--new-hash", "sha256:new",
               "--by", "op", "--reason", "r", "--commit"])
    assert rc == 0 and "change_id" in capsys.readouterr().out


def test_cli_approve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    cid = _to_reviewed(eng)
    from jarvis.policy_governance.__main__ import main
    rc = main(["approve", "--change-id", cid, "--approver", "boss",
               "--decision", "APPROVE", "--commit"])
    assert rc == 0 and "approval" in capsys.readouterr().out


def test_cli_snapshot(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    _reg(_eng())
    from jarvis.policy_governance.__main__ import main
    assert main(["snapshot", "--commit"]) == 0
    assert "configuration_hash" in capsys.readouterr().out


def test_cli_drift(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng)
    eng.snapshot(T0, commit=True)
    from jarvis.policy_governance.__main__ import main
    assert main(["drift"]) == 0
    assert "drift_level" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.__main__ import main
    assert main(["summary"]) == 0
    assert "compliance_score" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.policy_governance.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 68~76. 보안/불변/무변경 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.policy_governance.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.policy_governance.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "disarm(", "kill_switch(", "LiveExecutionEngine", "set_autonomy"):
            assert banned not in src, f"{m} has execution/mutation verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.policy_governance.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate("):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_no_config_or_permission_mutation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, m0, f0 = cfg.AUTONOMY_LEVEL, cfg.MIN_LIVE_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _reg(eng)
    cid = _to_reviewed(eng)
    eng.approve_change(cid, "boss", APPROVE, now=T0, commit=True)
    eng.activate_change(cid, T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and cfg.MIN_LIVE_LEVEL == m0
    assert len(FORBIDDEN) == f0   # 권한/설정 무변경


def test_ledger_no_delete_or_update_api():
    import inspect
    from jarvis.policy_governance import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src, f"ledger exposes mutation API: {banned}"


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("policy_governance", "change_policy", "governance_override"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, ver="1", params={"x": 1})
    n1 = len(ledger.read_policies())
    _reg(eng, ver="2", params={"x": 2})
    assert len(ledger.read_policies()) > n1   # 오직 증가


def test_immutable_version_never_overwritten(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _reg(eng, ver="1", params={"x": 1})
    h0 = ledger.read_policies()[0]["policy_hash"]
    with pytest.raises(ImmutablePolicyError):
        _reg(eng, ver="1", params={"x": 2})
    assert ledger.read_policies()[0]["policy_hash"] == h0   # 원본 불변


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
