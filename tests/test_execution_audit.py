"""P8.6 Execution Audit & Attestation 테스트. **AUDIT-ONLY.**

PASS/WARNING/FAILED 경로·누락(요청/생애주기/대조/비용/리스크)·중복탐지·해시체인·변조탐지·
append-only·결정적리플레이·타임스탬프순서·금지import없음·집행능력없음·브로커호출없음·
권한무결성·상태변경없음·CLI·해시안정성.
"""
from __future__ import annotations

import os

from jarvis.execution_audit.engine import ExecutionAuditEngine
from jarvis.execution_audit.models import FAILED, PASS, WARNING

_RID = "LXR:1"


def _lc(rid=_RID, states=("CREATED", "VALIDATED", "SUBMITTED"), t0=0):
    """유효 생애주기 이벤트 체인(previous_hash 연결)."""
    evs = []
    prev_state = ""
    prev_hash = "GENESIS"
    for i, st in enumerate(states):
        eh = f"sha256:lc{i}"
        evs.append({"event_id": f"OLE:{i}", "order_id": rid, "previous_state": prev_state,
                    "new_state": st, "timestamp": f"2026-07-22T00:00:0{i}Z",
                    "previous_hash": prev_hash, "event_hash": eh})
        prev_state, prev_hash = st, eh
    return evs


def _req(rid=_RID):
    return {"request_id": rid, "request_hash": "sha256:req1", "created_at": "2026-07-22T00:00:00Z"}


def _recon(rid=_RID, status="MATCHED"):
    return {"order_id": rid, "status": status, "report_hash": "sha256:rc1",
            "timestamp": "2026-07-22T00:00:03Z"}


def _cost(rid=_RID, status="EXPECTED"):
    return {"order_id": rid, "status": status, "cost_hash": "sha256:ct1",
            "timestamp": "2026-07-22T00:00:04Z"}


def _risk(rid=_RID, status="ALLOW", ts="2026-07-22T00:00:05Z"):
    return {"request_id": rid, "overall_status": status, "report_hash": "sha256:rk1",
            "timestamp": ts}


def _full(**over):
    src = dict(request=_req(), lifecycle=_lc(), reconciliation=_recon(), cost=_cost(), risk=_risk())
    src.update(over)
    return src


def _iso(tmp_path, monkeypatch):
    monkeypatch.setattr("jarvis.execution_audit.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    # 하위 원장 읽기도 빈 tmp로 격리(누락 소스 시뮬)
    monkeypatch.setattr("jarvis.execution_audit.engine.state_path",
                        lambda name: os.path.join(tmp_path, name))


def _chk(cert, name):
    return next(c for c in cert.checks if c["name"] == name)


# ── 1. PASS path ──
def test_pass_path():
    cert = ExecutionAuditEngine().audit(_RID, "2026-07-22T00:01:00Z", **_full())
    assert cert.audit_status == PASS and cert.audit_score == 1.0
    assert cert.errors == [] and cert.warnings == []
    assert len(cert.checks) == 15


def test_fifteen_checks_present():
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full())
    names = {c["name"] for c in cert.checks}
    assert len(names) == 15
    for req in ("request_exists", "lifecycle_chain_valid", "lifecycle_hash_chain",
                "fill_reconciliation_pass", "cost_report_exists", "risk_report_exists",
                "all_referenced_hashes_exist", "timestamp_monotonic", "no_duplicate_records"):
        assert req in names


# ── 2. WARNING path ──
def test_warning_path():
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full(reconciliation=_recon(status="WARNING")))
    assert cert.audit_status == WARNING
    assert _chk(cert, "fill_reconciliation_pass")["status"] == WARNING
    assert "fill_reconciliation_pass" in cert.warnings


def test_risk_block_is_warning():
    # 리스크 BLOCK은 감사상 WARNING(일관성 감사 — 승인 여부 아님)
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full(risk=_risk(status="BLOCK")))
    assert _chk(cert, "risk_report_exists")["status"] == WARNING
    assert cert.audit_status == WARNING


# ── 3. FAILED path ──
def test_failed_path():
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full(reconciliation=_recon(status="FAILED")))
    assert cert.audit_status == FAILED
    assert "fill_reconciliation_pass" in cert.errors


# ── 4. missing request ──
def test_missing_request(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cert = ExecutionAuditEngine().audit(_RID, "t", lifecycle=_lc(), reconciliation=_recon(),
                                        cost=_cost(), risk=_risk())
    assert _chk(cert, "request_exists")["status"] == FAILED and cert.audit_status == FAILED


# ── 5. missing lifecycle ──
def test_missing_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cert = ExecutionAuditEngine().audit(_RID, "t", request=_req(), reconciliation=_recon(),
                                        cost=_cost(), risk=_risk())
    assert _chk(cert, "lifecycle_chain_valid")["status"] == FAILED
    assert _chk(cert, "lifecycle_hash_chain")["status"] == FAILED
    assert cert.audit_status == FAILED


# ── 6. missing reconciliation ──
def test_missing_reconciliation(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cert = ExecutionAuditEngine().audit(_RID, "t", request=_req(), lifecycle=_lc(),
                                        cost=_cost(), risk=_risk())
    assert _chk(cert, "fill_reconciliation_pass")["status"] == FAILED and cert.audit_status == FAILED


# ── 7. missing cost ──
def test_missing_cost(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cert = ExecutionAuditEngine().audit(_RID, "t", request=_req(), lifecycle=_lc(),
                                        reconciliation=_recon(), risk=_risk())
    assert _chk(cert, "cost_report_exists")["status"] == FAILED and cert.audit_status == FAILED


# ── 8. missing risk ──
def test_missing_risk(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    cert = ExecutionAuditEngine().audit(_RID, "t", request=_req(), lifecycle=_lc(),
                                        reconciliation=_recon(), cost=_cost())
    assert _chk(cert, "risk_report_exists")["status"] == FAILED and cert.audit_status == FAILED


# ── 9. duplicate detection ──
def test_duplicate_detection():
    dup_lc = _lc() + [_lc()[0]]   # 같은 event_id 재등장
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full(lifecycle=dup_lc))
    assert _chk(cert, "no_duplicate_records")["status"] == FAILED


# ── 10. hash chain (lifecycle) broken ──
def test_lifecycle_hash_chain_broken():
    lc = _lc()
    lc[1]["previous_hash"] = "sha256:WRONG"   # 연결 깨기
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full(lifecycle=lc))
    assert _chk(cert, "lifecycle_hash_chain")["status"] == FAILED
    assert _chk(cert, "append_only_integrity")["status"] == FAILED


# ── 11. tampering detection (certificate ledger) ──
def test_tampering_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_audit.verify import verify_chain
    eng = ExecutionAuditEngine()
    eng.audit("LXR:a", "t", **_full(request=_req("LXR:a"), lifecycle=_lc("LXR:a"),
              reconciliation=_recon("LXR:a"), cost=_cost("LXR:a"), risk=_risk("LXR:a")), commit=True)
    eng.audit("LXR:b", "t", **_full(request=_req("LXR:b"), lifecycle=_lc("LXR:b"),
              reconciliation=_recon("LXR:b"), cost=_cost("LXR:b"), risk=_risk("LXR:b")), commit=True)
    assert verify_chain()["ok"]
    import json
    p = os.path.join(tmp_path, "execution_audit_certificates.jsonl")
    lines = open(p).read().splitlines()
    row = json.loads(lines[1]); row["previous_hash"] = "sha256:tampered"
    lines[1] = json.dumps(row)
    open(p, "w").write("\n".join(lines) + "\n")
    res = verify_chain()
    assert not res["ok"] and res["reason"] == "previous_hash_broken"


# ── 12. append-only + chain ──
def test_append_only(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_audit.ledger import read_certificates
    from jarvis.execution_audit.verify import verify_chain
    eng = ExecutionAuditEngine()
    eng.audit("LXR:a", "t", **_full(request=_req("LXR:a"), lifecycle=_lc("LXR:a"),
              reconciliation=_recon("LXR:a"), cost=_cost("LXR:a"), risk=_risk("LXR:a")), commit=True)
    eng.audit("LXR:b", "t", **_full(request=_req("LXR:b"), lifecycle=_lc("LXR:b"),
              reconciliation=_recon("LXR:b"), cost=_cost("LXR:b"), risk=_risk("LXR:b")), commit=True)
    certs = read_certificates()
    assert len(certs) == 2
    assert certs[0]["previous_hash"] == "GENESIS"
    assert certs[1]["previous_hash"] == certs[0]["certificate_hash"]
    assert verify_chain()["ok"]


def test_duplicate_certificate_not_reappended(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.execution_audit.ledger import read_certificates
    eng = ExecutionAuditEngine()
    eng.audit(_RID, "t", **_full(), commit=True)
    eng.audit(_RID, "t", **_full(), commit=True)   # 동일 → 재추가 안 됨
    assert len(read_certificates()) == 1


# ── 13. deterministic replay ──
def test_deterministic_replay():
    from jarvis.execution_audit.verify import replay
    eng = ExecutionAuditEngine()
    res = replay(eng, _RID, "t", **_full())
    assert res["deterministic"]


def test_hash_stability():
    eng = ExecutionAuditEngine()
    c1 = eng.audit(_RID, "t", **_full())
    c2 = eng.audit(_RID, "t", **_full())
    assert c1.certificate_hash == c2.certificate_hash and c1.to_dict() == c2.to_dict()
    c3 = eng.audit(_RID, "t", **_full(reconciliation=_recon(status="FAILED")))
    assert c3.certificate_hash != c1.certificate_hash


# ── 14. timestamp ordering ──
def test_timestamp_monotonic_violation():
    # 리스크 타임스탬프가 비용보다 앞섬 → 비단조
    cert = ExecutionAuditEngine().audit(_RID, "t",
                                        **_full(risk=_risk(ts="2026-07-22T00:00:01Z")))
    assert _chk(cert, "timestamp_monotonic")["status"] == FAILED


# ── 15. no forbidden imports ──
def test_no_forbidden_imports():
    import importlib
    import inspect
    forbidden = ("jarvis.execution.gateway", "jarvis.execution.arm", "jarvis.live_execution",
                 "jarvis.paper_execution", "jarvis.risk.governor")
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_audit.{m}"))
        for f in forbidden:
            assert f not in src, f"{m} imports {f}"


# ── 16. no execution capability / no broker calls ──
def test_no_execution_capability():
    import importlib
    import inspect
    for m in ("models", "engine", "ledger", "verify", "__main__"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_audit.{m}"))
        for banned in ("submit_order", "place_order", "cancel_order", "route_order",
                       ".buy(", ".sell(", "gateway", "adapter.submit", "broker_execution"):
            assert banned not in src


def test_no_autonomous_trigger():
    import importlib
    import inspect
    for m in ("engine", "__main__", "verify"):
        src = inspect.getsource(importlib.import_module(f"jarvis.execution_audit.{m}"))
        assert "LiveExecutionEngine" not in src and "live_execution.engine" not in src


# ── 17. no permission escalation ──
def test_no_permission_escalation():
    from jarvis.permissions.policy import ACTION_PERMISSIONS, FORBIDDEN
    assert len(FORBIDDEN) == 6
    assert not any("execution_audit" in a for a in ACTION_PERMISSIONS)
    assert not any("attestation" in a for a in ACTION_PERMISSIONS)


# ── 18. no mutation (paper ledger immutable) ──
def test_no_mutation(tmp_path, monkeypatch):
    import hashlib

    def sp(name):
        return os.path.join(tmp_path, name)
    import jarvis.paper_execution.ledger as pel
    monkeypatch.setattr(pel, "state_path", sp)
    from jarvis.paper_execution.engine import PaperExecutionEngine
    PaperExecutionEngine(capital=10000).execute_proposal(
        {"proposal_id": "PP:1", "strategy": "A", "allocation": {"A": 0.5}, "created_at": "t"},
        True, {"decision": "ALLOW"}, lambda s, ts: 100.0, "t", commit=True)
    pos = sp("paper_positions.jsonl")
    before = hashlib.sha256(open(pos, "rb").read()).hexdigest()
    monkeypatch.setattr("jarvis.execution_audit.ledger.state_path", sp)
    ExecutionAuditEngine().audit(_RID, "t", **_full(), commit=True)
    assert hashlib.sha256(open(pos, "rb").read()).hexdigest() == before   # 페이퍼 불변


# ── 19. CLI verify (empty) ──
def test_cli_verify_empty(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("jarvis.execution_audit.ledger.state_path",
                        lambda name: os.path.join(tmp_path, name))
    from jarvis.execution_audit.__main__ import main
    rc = main(["verify"])
    assert rc == 0
    out = capsys.readouterr().out
    assert '"ok": true' in out


# ── 20. certificate is attestation-only (no trade authorization fields) ──
def test_certificate_is_attestation_only():
    cert = ExecutionAuditEngine().audit(_RID, "t", **_full())
    keys = set(cert.to_dict())
    assert keys == {"certificate_id", "timestamp", "request_id", "audit_status", "audit_score",
                    "checks", "warnings", "errors", "input_hash", "certificate_hash",
                    "previous_hash"}
    for f in ("authorized", "order_id_submitted", "broker", "execute", "route"):
        assert f not in keys


# ── 21. all referenced hashes exist check ──
def test_all_referenced_hashes():
    ok = ExecutionAuditEngine().audit(_RID, "t", **_full())
    assert _chk(ok, "all_referenced_hashes_exist")["status"] == PASS
    # 요청 해시 누락 → FAILED
    bad_req = {"request_id": _RID, "created_at": "2026-07-22T00:00:00Z"}   # request_hash 없음
    bad = ExecutionAuditEngine().audit(_RID, "t", **_full(request=bad_req))
    assert _chk(bad, "all_referenced_hashes_exist")["status"] == FAILED
