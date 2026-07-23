"""Policy Governance Engine (P9.7) — 정책 등록·변경 워크플로·승인·스냅샷·drift. **관리·감사 전용.**

정책을 불변 버전으로 등록하고, 변경요청 상태머신(DRAFT→REQUESTED→REVIEWED→APPROVED→ACTIVE)을
관리하며, 승인 기록·설정 스냅샷·drift 감지를 남긴다. **APPROVED/ACTIVE 는 기록일 뿐 실제 적용
없음.** config/risk/autonomy/permission/kill switch 무변경·execution 호출 없음. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.policy_governance import ledger
from jarvis.policy_governance.models import (
    ACTIVE,
    APPROVE,
    APPROVED,
    CRITICAL_DRIFT,
    DRAFT,
    GENESIS,
    NO_DRIFT,
    REJECT,
    REJECTED,
    REQUESTED,
    REVIEWED,
    WARNING_DRIFT,
    ApprovalError,
    ApprovalRecord,
    DriftError,
    IllegalTransition,
    ImmutablePolicyError,
    PolicyChangeEvent,
    PolicyDefinition,
    PolicyDriftReport,
    PolicyGovernanceReport,
    PolicySnapshot,
    approval_id,
    can_transition,
    change_event_id,
    change_id,
    compliance_score,
    configuration_hash,
    content_hash,
    drift_report_id,
    input_digest,
    is_approved,
    is_pending,
    is_valid_decision,
    policy_hash as _policy_hash,
    snapshot_id,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _ver_key(v: str):
    try:
        return (0, int(v))
    except (ValueError, TypeError):
        return (1, str(v))


class PolicyGovernanceEngine:
    """정책 거버넌스 엔진. 읽기전용 참조·append-only 거버넌스 원장·결정적. 실제 적용 없음."""

    # ── 1. Policy Registry(불변 버전) ──
    def register_policy(self, policy_id: str, name: str, category: str, version: str,
                        parameters: dict, description: str, created_by: str, now: str = "",
                        *, commit: bool = False) -> PolicyDefinition:
        ph = _policy_hash(policy_id, name, category, version, parameters, description)
        # 불변성: 동일 policy_id+version 이 다른 내용으로 존재하면 위반
        for p in ledger.read_policies():
            if p.get("policy_id") == policy_id and p.get("version") == version:
                if p.get("policy_hash") != ph:
                    raise ImmutablePolicyError(
                        f"{policy_id} v{version} 는 불변 — 내용 변경 불가")
                # 동일 내용 재등록 = 멱등
                return PolicyDefinition(**{k: v for k, v in p.items()
                                           if k in PolicyDefinition.__dataclass_fields__})
        rec = PolicyDefinition(
            policy_id=policy_id, name=name, category=category, version=version,
            parameters=parameters, description=description, created_by=created_by,
            created_at=now, policy_hash=ph, input_hash=ph, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.policy_hash_exists(ph):
            head = ledger.policies_head()
            ledger.append_policy(_seal(rec, head["record_hash"] if head else GENESIS))
        return PolicyDefinition(**rec)

    def _active_policies(self) -> list[dict]:
        """policy_id 별 최신 버전(설정 스냅샷 대상)."""
        latest: dict = {}
        for p in ledger.read_policies():
            pid = p.get("policy_id")
            cur = latest.get(pid)
            if cur is None or _ver_key(p.get("version")) >= _ver_key(cur.get("version")):
                latest[pid] = p
        return [latest[k] for k in sorted(latest)]

    # ── 2. Change Workflow(상태머신) ──
    def _change_meta(self, cid: str) -> dict | None:
        evs = ledger.change_events_for(cid)
        return evs[0] if evs else None

    def current_status(self, cid: str) -> str:
        evs = ledger.change_events_for(cid)
        return evs[-1].get("to_status", "") if evs else ""

    def _emit_change(self, cid: str, meta: dict, frm: str, to: str, now: str,
                     *, actor: str, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단")
        eid = change_event_id(cid, frm, to)
        rec = PolicyChangeEvent(
            event_id=eid, change_id=cid, policy_id=meta["policy_id"], old_hash=meta["old_hash"],
            new_hash=meta["new_hash"], reason=meta["reason"], requested_by=meta["requested_by"],
            from_status=frm, to_status=to, status=to, timestamp=now, actor=actor,
            input_hash=input_digest(cid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.change_event_exists(eid):
            head = ledger.change_events_head()
            ledger.append_change_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_change_request(self, policy_id: str, new_hash: str, reason: str,
                              requested_by: str, now: str = "", *, commit: bool = False) -> str:
        active = {p["policy_id"]: p for p in self._active_policies()}
        old_hash = active.get(policy_id, {}).get("policy_hash", "")
        cid = change_id(policy_id, new_hash, requested_by)
        meta = {"policy_id": policy_id, "old_hash": old_hash, "new_hash": new_hash,
                "reason": reason, "requested_by": requested_by}
        if not ledger.change_events_for(cid):
            self._emit_change(cid, meta, "", DRAFT, now, actor=requested_by, commit=commit)
        return cid

    def _advance(self, cid: str, to: str, now: str, *, actor: str, commit: bool) -> dict:
        meta = self._change_meta(cid)
        if meta is None:
            raise IllegalTransition(f"미존재 변경요청 {cid}")
        return self._emit_change(cid, meta, self.current_status(cid), to, now,
                                 actor=actor, commit=commit)

    def submit_change(self, cid: str, now: str = "", *, actor: str = "operator",
                      commit: bool = False) -> dict:
        return self._advance(cid, REQUESTED, now, actor=actor, commit=commit)

    def review_change(self, cid: str, now: str = "", *, actor: str = "reviewer",
                      commit: bool = False) -> dict:
        return self._advance(cid, REVIEWED, now, actor=actor, commit=commit)

    def activate_change(self, cid: str, now: str = "", *, actor: str = "operator",
                        commit: bool = False) -> dict:
        """APPROVED→ACTIVE 기록만 — **실제 정책/설정 적용 없음.**"""
        return self._advance(cid, ACTIVE, now, actor=actor, commit=commit)

    def request(self, policy_id: str, new_hash: str, reason: str, requested_by: str,
                now: str = "", *, commit: bool = False) -> str:
        """CLI 편의: 변경요청 생성 → REQUESTED 까지."""
        cid = self.create_change_request(policy_id, new_hash, reason, requested_by, now,
                                         commit=commit)
        if self.current_status(cid) == DRAFT:
            self.submit_change(cid, now, actor=requested_by, commit=commit)
        return cid

    # ── 3. Approval Governance ──
    def approve_change(self, cid: str, approver: str, decision: str, reason: str = "",
                       now: str = "", *, expected_hash: str = "", commit: bool = False) -> dict:
        if not approver:
            raise ApprovalError("승인자 필요")
        if not is_valid_decision(decision):
            raise ApprovalError(f"허용되지 않은 결정: {decision}")
        meta = self._change_meta(cid)
        if meta is None:
            raise ApprovalError(f"미존재 변경요청 {cid}")
        if expected_hash and expected_hash != meta["new_hash"]:
            raise ApprovalError("change hash 불일치")
        cur = self.current_status(cid)
        if cur != REVIEWED:
            raise IllegalTransition(f"승인은 REVIEWED 에서만 가능(현재 {cur})")

        aid = approval_id(cid, approver, decision)
        rec = ApprovalRecord(
            approval_id=aid, change_id=cid, approver=approver, decision=decision, reason=reason,
            timestamp=now, change_hash=meta["new_hash"],
            input_hash=input_digest(cid, approver, decision), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.approval_exists(aid):
            head = ledger.approvals_head()
            ledger.append_approval(_seal(rec, head["record_hash"] if head else GENESIS))
        # 상태 전이(기록만)
        to = APPROVED if decision == APPROVE else REJECTED
        self._emit_change(cid, meta, cur, to, now, actor=approver, commit=commit)
        return rec

    # ── 4. Configuration Snapshot ──
    def snapshot(self, now: str = "", *, commit: bool = False) -> PolicySnapshot:
        active = self._active_policies()
        versions = {p["policy_id"]: p.get("version") for p in active}
        cfg_hash = configuration_hash(active)
        sid = snapshot_id(cfg_hash)
        rec = PolicySnapshot(
            snapshot_id=sid, policy_versions=versions, configuration_hash=cfg_hash,
            created_at=now, policy_count=len(active), input_hash=cfg_hash,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        return PolicySnapshot(**rec)

    # ── 5. Drift Detection ──
    def detect_drift(self, now: str = "", *, snapshot=None, current_active=None,
                     commit: bool = False) -> PolicyDriftReport:
        snap = snapshot.to_dict() if hasattr(snapshot, "to_dict") else snapshot
        if snap is None:
            snap = ledger.snapshots_head()
        if not snap:
            raise DriftError("비교할 스냅샷 없음")
        active = current_active if current_active is not None else self._active_policies()
        expected = snap.get("configuration_hash", "")
        actual = configuration_hash(active)

        findings: list = []
        if actual == expected:
            level = NO_DRIFT
            detected = False
        else:
            snap_vers = snap.get("policy_versions", {}) or {}
            cur_vers = {p["policy_id"]: p.get("version") for p in active}
            removed = sorted(set(snap_vers) - set(cur_vers))
            added = sorted(set(cur_vers) - set(snap_vers))
            changed = sorted(k for k in set(snap_vers) & set(cur_vers)
                             if snap_vers[k] != cur_vers[k])
            for k in removed:
                findings.append(f"removed:{k}")
            for k in added:
                findings.append(f"added:{k}")
            for k in changed:
                findings.append(f"changed:{k}:{snap_vers[k]}->{cur_vers[k]}")
            level = CRITICAL_DRIFT if removed else WARNING_DRIFT
            detected = True

        rid = drift_report_id(snap["snapshot_id"], actual)
        rec = PolicyDriftReport(
            report_id=rid, snapshot_id=snap["snapshot_id"], expected_hash=expected,
            actual_hash=actual, drift_detected=detected, drift_level=level, findings=findings,
            timestamp=now, input_hash=input_digest(snap["snapshot_id"], actual),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.drift_report_exists(rid):
            head = ledger.drift_reports_head()
            ledger.append_drift_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return PolicyDriftReport(**rec)

    # ── 6. Compliance Summary ──
    def governance_report(self, now: str = "") -> PolicyGovernanceReport:
        active = self._active_policies()
        versions = {p["policy_id"]: p.get("version") for p in active}
        # 변경요청 현재 상태 fold
        cids = {r.get("change_id") for r in ledger.read_change_events()}
        pending = approved = 0
        for cid in cids:
            st = self.current_status(cid)
            if is_pending(st):
                pending += 1
            elif is_approved(st):
                approved += 1
        drifts = ledger.read_drift_reports()
        crit = sum(1 for d in drifts if d.get("drift_level") == CRITICAL_DRIFT)
        warn = sum(1 for d in drifts if d.get("drift_level") == WARNING_DRIFT)
        drift_count = sum(1 for d in drifts if d.get("drift_detected"))
        score = compliance_score(crit, warn, pending)
        return PolicyGovernanceReport(
            timestamp=now, policy_count=len(active), active_versions=versions,
            pending_changes=pending, approved_changes=approved, drift_count=drift_count,
            compliance_score=score)
