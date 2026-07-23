"""P9.10 Access Governance & Operator Identity 테스트. **신원 거버넌스·접근 감사 전용.**

운영자/역할(불변)·세션(active/expired)·접근 상태머신(REQUESTED→REVIEWED→APPROVED→EXPIRED, 차단
전이)·승인·감사 5체크(unknown operator/expired session/missing approval/unusual pattern/policy
mismatch)·verify(체인/변조/중복)·replay·CLI·보안(금지import·집행/브로커 없음·permission 파일 hash
불변·FORBIDDEN/autonomy 불변·role escalation 없음·기존 원장 무변경·삭제 API 없음·불변·append-only).

패키지 내부 tests/ — 상위 tests/conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import hashlib
import json
import os

import pytest

from jarvis.access_governance import ledger
from jarvis.access_governance import models as M
from jarvis.access_governance.engine import AccessGovernanceEngine
from jarvis.access_governance.models import (
    ACTIVE,
    APPROVE,
    APPROVED,
    CRITICAL,
    EXPIRED,
    INFO,
    REJECT,
    REJECTED,
    REQUESTED,
    REVIEWED,
    SESSION_EXPIRED,
    WARNING,
    ApprovalError,
    IllegalTransition,
    ImmutableOperatorError,
    ImmutableRoleError,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T_EXP = "2026-07-22T00:00:00Z"    # 과거 만료
T_LATE = "2026-07-25T00:00:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.access_governance.ledger.state_path", sp)
    return sp


def _eng():
    return AccessGovernanceEngine()


def _op(eng, oid="op1", roles=None, commit=True):
    return eng.register_operator(oid, f"{oid} name", f"{oid}@x.com", roles or ["viewer"],
                                 "ACTIVE", T0, commit=commit)


def _to_reviewed(eng, oid="op1", resource="res", scope="viewer"):
    rid = eng.request_access(oid, resource, scope, "need", T0, commit=True)
    eng.review_access(rid, T0, commit=True)
    return rid


# ── 1~10. models 순수 ──
def test_can_transition_allowed():
    assert M.can_transition("", REQUESTED) and M.can_transition(REQUESTED, REVIEWED)
    assert M.can_transition(REVIEWED, APPROVED) and M.can_transition(REVIEWED, REJECTED)
    assert M.can_transition(APPROVED, EXPIRED)


def test_can_transition_blocked():
    assert not M.can_transition(REQUESTED, APPROVED)
    assert not M.can_transition(EXPIRED, REQUESTED)
    assert not M.can_transition(REJECTED, APPROVED)


def test_identity_hash_deterministic():
    assert M.identity_hash("o", "n", "e", ["a"]) == M.identity_hash("o", "n", "e", ["a"])


def test_role_hash_deterministic():
    assert M.role_hash("r", "n", "d", ["a"]) == M.role_hash("r", "n", "d", ["a"])


def test_content_hash_excludes():
    a = {"x": 1, "previous_hash": "p1", "record_hash": "r1"}
    b = {"x": 1, "previous_hash": "p2", "record_hash": "r2"}
    assert M.content_hash(a) == M.content_hash(b)


def test_compliance_score_pure():
    assert M.compliance_score(0, 0, 0) == 100
    assert M.compliance_score(1, 0, 0) == 66
    assert M.compliance_score(0, 1, 0) == 92
    assert M.compliance_score(0, 0, 1) == 98


def test_session_status_active():
    assert M.session_status(T_LATE, T0) == ACTIVE


def test_session_status_expired():
    assert M.session_status(T_EXP, T0) == SESSION_EXPIRED


def test_is_valid_decision():
    assert M.is_valid_decision(APPROVE) and not M.is_valid_decision("GRANT_ALL")


def test_severity_rank():
    assert M.severity_rank(CRITICAL) > M.severity_rank(WARNING) > M.severity_rank(INFO)


# ── 11~14. Operator Registry ──
def test_register_operator_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    o = _op(_eng(), commit=False)
    assert o.operator_id == "op1" and o.identity_hash.startswith("sha256:")


def test_register_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _op(_eng())
    assert len(ledger.read_operators()) == 1


def test_register_duplicate_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng)
    _op(eng)
    assert len(ledger.read_operators()) == 1


def test_register_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng, oid="op1", roles=["viewer"])
    with pytest.raises(ImmutableOperatorError):
        _op(eng, oid="op1", roles=["admin"])


# ── 15~17. Role Registry ──
def test_register_role_creates(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().register_role("admin", "Admin", "desc", ["read", "write"], T0, commit=True)
    assert r.scope == ["read", "write"] and len(ledger.read_roles()) == 1


def test_role_immutable_violation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_role("admin", "Admin", "desc", ["read"], T0, commit=True)
    with pytest.raises(ImmutableRoleError):
        eng.register_role("admin", "Admin", "desc", ["read", "write"], T0, commit=True)


def test_role_is_metadata_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import ACTION_PERMISSIONS
    before = dict(ACTION_PERMISSIONS)
    _eng().register_role("superadmin", "Super", "d", ["expand_own_permission"], T0, commit=True)
    # 역할 등록은 실제 권한 정책을 변경하지 않음(메타 기록만)
    assert dict(ACTION_PERMISSIONS) == before


# ── 18~21. Session ──
def test_create_session_active(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_session("op1", T0, T_LATE, {}, T0, commit=True)
    assert s.status == ACTIVE


def test_create_session_expired(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    s = _eng().create_session("op1", T_EXP, T_EXP, {}, T0, commit=True)
    assert s.status == SESSION_EXPIRED


def test_session_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().create_session("op1", T0, T_LATE, {}, T0, commit=True)
    assert len(ledger.read_sessions()) == 1


def test_session_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("op1", T0, T_LATE, {}, T0, commit=True)
    eng.create_session("op1", T0, T_LATE, {}, T1, commit=True)
    assert len(ledger.read_sessions()) == 1


# ── 22~30. Access lifecycle ──
def test_request_access_requested(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = eng.request_access("op1", "res", "viewer", "need", T0, commit=True)
    assert eng.current_state(rid) == REQUESTED


def test_full_lifecycle_to_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    assert eng.current_state(rid) == APPROVED


def test_reject_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", REJECT, now=T0, commit=True)
    assert eng.current_state(rid) == REJECTED


def test_expire_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    eng.expire_access(rid, T1, commit=True)
    assert eng.current_state(rid) == EXPIRED


def test_illegal_transition_blocked(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = eng.request_access("op1", "res", "viewer", "need", T0, commit=True)
    with pytest.raises(IllegalTransition):
        eng.expire_access(rid, T0, commit=True)   # REQUESTED→EXPIRED 차단


def test_illegal_from_expired(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    eng.expire_access(rid, T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.review_access(rid, T1, commit=True)


def test_current_state_fold(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    assert eng.current_state(rid) == REVIEWED


def test_request_event_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    assert len(ledger.access_events_for(rid)) == 2


def test_request_duplicate_prevention(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = eng.request_access("op1", "res", "viewer", "need", T0, commit=True)
    eng.request_access("op1", "res", "viewer", "need", T1, commit=True)
    assert len(ledger.access_events_for(rid)) == 1


# ── 31~38. Approval ──
def test_approve_requires_reviewed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = eng.request_access("op1", "res", "viewer", "need", T0, commit=True)   # REQUESTED
    with pytest.raises(IllegalTransition):
        eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)


def test_approve_missing_approver(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    with pytest.raises(ApprovalError):
        eng.approve_access(rid, "", APPROVE, now=T0, commit=True)


def test_approve_invalid_decision(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    with pytest.raises(ApprovalError):
        eng.approve_access(rid, "boss", "GRANT_ALL", now=T0, commit=True)


def test_approve_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    assert eng.current_state(rid) == APPROVED


def test_reject_transitions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", REJECT, now=T0, commit=True)
    assert eng.current_state(rid) == REJECTED


def test_approval_records(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    assert len(ledger.read_approvals()) == 1


def test_approval_duplicate_prevented(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    try:
        eng.approve_access(rid, "boss", APPROVE, now=T1, commit=True)
    except IllegalTransition:
        pass
    assert len(ledger.read_approvals()) == 1


def test_approve_no_permission_grant(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import FORBIDDEN
    f0 = len(FORBIDDEN)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    assert len(FORBIDDEN) == f0   # 승인은 실제 권한 정책을 변경하지 않음


# ── 39~47. Audit checks (5종) ──
def test_audit_unknown_operator(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("ghost", T0, T_LATE, {}, T0, commit=True)   # 미등록 운영자
    rep = eng.audit_access(T0)
    assert any(f["rule"] == "unknown_operator" for f in rep.findings)


def test_audit_expired_session(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng, oid="op1")
    # 시작 시점엔 ACTIVE 로 기록되지만 이후 now 기준 만료
    eng.create_session("op1", T0, T1, {}, T0, commit=True)
    rep = eng.audit_access(T_LATE)   # T1 지난 시점
    assert any(f["rule"] == "expired_session" for f in rep.findings)


def test_audit_missing_approval(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    _op(_eng(), oid="op1")
    # APPROVED 상태 이벤트를 승인 기록 없이 주입(무결성 위반)
    with open(sp("ag_access_requests.jsonl"), "w") as f:
        f.write(json.dumps({"event_id": "E1", "request_id": "R1", "operator_id": "op1",
                            "resource": "res", "requested_scope": "viewer", "to_state": APPROVED}) + "\n")
    rep = _eng().audit_access(T0)
    assert any(f["rule"] == "missing_approval" and f["severity"] == CRITICAL
               for f in rep.findings)


def test_audit_unusual_pattern(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng, oid="op1", roles=["viewer"])
    for i in range(6):
        eng.request_access("op1", f"res{i}", "viewer", "need", T0, commit=True)
    rep = eng.audit_access(T0)
    assert any(f["rule"] == "unusual_access_pattern" for f in rep.findings)


def test_audit_policy_mismatch(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_role("viewer_role", "Viewer", "d", ["read_dashboard"], T0, commit=True)
    _op(eng, oid="op1", roles=["viewer_role"])
    eng.request_access("op1", "res", "nonexistent_scope_zzz", "need", T0, commit=True)
    rep = eng.audit_access(T0)
    assert any(f["rule"] == "policy_mismatch" for f in rep.findings)


def test_audit_clean_no_findings(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_role("viewer_role", "Viewer", "d", ["read_dashboard"], T0, commit=True)
    _op(eng, oid="op1", roles=["viewer_role"])
    eng.request_access("op1", "res", "read_dashboard", "need", T0, commit=True)
    rep = eng.audit_access(T0)
    assert rep.findings == [] and rep.compliance_score == 100


def test_audit_compliance_score(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("ghost", T0, T_LATE, {}, T0, commit=True)   # unknown → WARNING
    rep = eng.audit_access(T0)
    assert rep.compliance_score < 100


def test_audit_commit_appends(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _eng().audit_access(T0, commit=True)
    assert len(ledger.read_audit_reports()) == 1


def test_audit_report_fields(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().audit_access(T0).to_dict()
    for k in ("checks", "findings", "critical_findings", "warning_findings",
              "info_findings", "compliance_score"):
        assert k in r


# ── 48~51. Governance report ──
def test_report_operator_count(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng, oid="op1")
    _op(eng, oid="op2")
    assert eng.generate_report(T0).operator_count == 2


def test_report_active_sessions(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("op1", T0, T_LATE, {}, T0, commit=True)
    assert eng.generate_report(T0).active_sessions == 1


def test_report_request_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    rep = eng.generate_report(T0)
    assert rep.request_state_distribution.get(APPROVED) == 1


def test_report_pending_approved(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.request_access("op1", "r1", "viewer", "n", T0, commit=True)   # pending
    rid2 = _to_reviewed(eng, resource="r2")
    eng.approve_access(rid2, "boss", APPROVE, now=T0, commit=True)
    rep = eng.generate_report(T0)
    assert rep.pending_requests == 1 and rep.approved_requests == 1


# ── 52~57. Verify / tamper / replay ──
def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_chain_intact(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.verify import verify_chain
    eng = _eng()
    _op(eng)
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    res = verify_chain()
    assert res["ok"] and res["n"] >= 4


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.verify import verify_chain
    _op(_eng())
    path = sp("ag_operators.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[0]["email"] = "TAMPERED"
    with open(path, "w") as f:
        f.write(json.dumps(recs[0]) + "\n")
    assert verify_chain()["ledgers"]["ag_operators.jsonl"]["reason"] == "record_hash_mismatch"


def test_verify_detects_broken_previous_hash(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.verify import verify_chain
    eng = _eng()
    _op(eng, oid="op1")
    _op(eng, oid="op2")
    path = sp("ag_operators.jsonl")
    recs = [json.loads(ln) for ln in open(path) if ln.strip()]
    recs[1]["previous_hash"] = "sha256:deadbeef"
    with open(path, "w") as f:
        for r in recs:
            f.write(json.dumps(r) + "\n")
    assert verify_chain()["ledgers"]["ag_operators.jsonl"]["reason"] == "previous_hash_broken"


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.verify import verify_chain
    _op(_eng())
    path = sp("ag_operators.jsonl")
    rec = [json.loads(ln) for ln in open(path) if ln.strip()][0]
    with open(path, "a") as f:
        f.write(json.dumps(rec) + "\n")
    assert verify_chain()["ledgers"]["ag_operators.jsonl"]["reason"] in {"duplicate_id",
                                                                         "previous_hash_broken"}


def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.create_session("ghost", T0, T_LATE, {}, T0, commit=True)
    from jarvis.access_governance.verify import replay
    assert replay(eng, T0)["deterministic"] is True


# ── 58~66. CLI ──
def test_cli_operator(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    rc = main(["operator", "--operator-id", "op1", "--name", "n", "--email", "e@x.com",
               "--roles", "viewer", "--commit"])
    assert rc == 0 and "operator" in capsys.readouterr().out


def test_cli_role(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    rc = main(["role", "--role-id", "admin", "--name", "Admin", "--scope", "read,write",
               "--commit"])
    assert rc == 0 and "role" in capsys.readouterr().out


def test_cli_session(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    rc = main(["session", "--operator-id", "op1", "--started-at", T0, "--expires-at", T_LATE,
               "--commit"])
    assert rc == 0 and "session" in capsys.readouterr().out


def test_cli_request(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    rc = main(["request", "--operator-id", "op1", "--resource", "res", "--scope", "viewer",
               "--commit"])
    assert rc == 0 and "request_id" in capsys.readouterr().out


def test_cli_approve(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    rid = _to_reviewed(eng)
    from jarvis.access_governance.__main__ import main
    rc = main(["approve", "--request-id", rid, "--approver", "boss", "--decision", "APPROVE",
               "--commit"])
    assert rc == 0 and "approval" in capsys.readouterr().out


def test_cli_audit(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    assert main(["audit"]) == 0
    assert "compliance_score" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    assert main(["verify"]) == 0
    assert "ok" in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    assert main(["summary"]) == 0
    assert "operator_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.access_governance.__main__ import main
    assert main(["replay"]) == 0
    assert "deterministic" in capsys.readouterr().out


# ── 67~79. 보안/불변/무변경 ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    _j = "jarvis."
    forbidden = (_j + "execution", _j + "live_execution", _j + "paper_execution",
                 _j + "execution_control", _j + "execution_risk", _j + "execution_cost",
                 _j + "portfolio", _j + "broker_readonly", _j + "risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__init__", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.access_governance.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} references {f}"


def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.access_governance.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", ".buy(", ".sell(",
                       "kill_switch(", "grant_permission", "escalate_role"):
            assert banned not in src, f"{m} has execution/escalation verb {banned}"


def test_no_broker_or_portfolio():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.access_governance.{m}"))
        for banned in ("gateway.", "broker.submit", "broker_api", "portfolio.",
                       "rebalance(", "allocate_capital"):
            assert banned not in src, f"{m} has broker/portfolio verb {banned}"


def test_permissions_file_hash_unchanged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.permissions.policy as pol
    path = pol.__file__
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    eng = _eng()
    _op(eng, oid="op1", roles=["admin"])
    eng.register_role("admin", "Admin", "d", ["expand_own_permission"], T0, commit=True)
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    eng.audit_access(T0, commit=True)
    after = hashlib.sha256(open(path, "rb").read()).hexdigest()
    assert before == after   # 기존 permission 파일 무변경


def test_forbidden_and_autonomy_unchanged(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    import jarvis.config as cfg
    from jarvis.permissions.policy import FORBIDDEN
    a0, f0 = cfg.AUTONOMY_LEVEL, len(FORBIDDEN)
    eng = _eng()
    _op(eng)
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    assert cfg.AUTONOMY_LEVEL == a0 and len(FORBIDDEN) == f0


def test_ledger_no_delete_api():
    import inspect
    from jarvis.access_governance import ledger as L
    src = inspect.getsource(L)
    for banned in ("def delete", "def update", "def remove", "def overwrite"):
        assert banned not in src


def test_existing_approvals_ledger_unchanged(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    # 기존 P9.7 approvals.jsonl 을 두고 P9.10 이 절대 건드리지 않음
    with open(sp("approvals.jsonl"), "w") as f:
        f.write(json.dumps({"pre": "existing"}) + "\n")
    before = hashlib.sha256(open(sp("approvals.jsonl"), "rb").read()).hexdigest()
    eng = _eng()
    rid = _to_reviewed(eng)
    eng.approve_access(rid, "boss", APPROVE, now=T0, commit=True)
    after = hashlib.sha256(open(sp("approvals.jsonl"), "rb").read()).hexdigest()
    assert before == after
    assert os.path.exists(sp("ag_approvals.jsonl"))


def test_no_role_escalation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.permissions.policy import ACTION_PERMISSIONS
    before = dict(ACTION_PERMISSIONS)
    eng = _eng()
    eng.register_role("superadmin", "Super", "d", ["expand_own_permission", "delete_audit_log"],
                      T0, commit=True)
    _op(eng, oid="op1", roles=["superadmin"])
    # 역할/운영자 등록이 실제 ACTION_PERMISSIONS(권한)를 확장하지 않음
    assert dict(ACTION_PERMISSIONS) == before


def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    for kw in ("access_governance", "operator_grant", "session_grant"):
        assert not any(kw in a.lower() for a in ACTION_PERMISSIONS), kw


def test_append_only_never_deletes(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _op(eng, oid="op1")
    n1 = len(ledger.read_operators())
    _op(eng, oid="op2")
    assert len(ledger.read_operators()) > n1


def test_autonomy_invariant():
    from jarvis.config import AUTONOMY_LEVEL, MIN_LIVE_LEVEL, live_execution_enabled
    assert AUTONOMY_LEVEL == 5 and MIN_LIVE_LEVEL == 6
    assert live_execution_enabled() is False
