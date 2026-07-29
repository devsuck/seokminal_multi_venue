"""Access Governance Engine (P9.10) — 운영자/역할/세션/접근요청/승인/감사. **신원 거버넌스·감사 전용.**

운영자·역할을 불변으로 등록하고 세션·접근요청 상태머신(REQUESTED→REVIEWED→APPROVED→EXPIRED)·승인·
접근 감사를 관리한다. **실제 권한 부여 없음·permission 변경 없음·operator action 실행 없음.**
기존 permission 시스템은 READ ONLY(정책 대조용). execution/broker import 없음. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.access_governance import ledger
from jarvis.access_governance.models import (
    ACTIVE,
    APPROVE,
    APPROVED,
    CRITICAL,
    EXPIRED,
    GENESIS,
    INFO,
    REJECTED,
    REQUESTED,
    REVIEWED,
    WARNING,
    AccessApproval,
    AccessAuditReport,
    AccessGovernanceReport,
    AccessRequest,
    ApprovalError,
    IllegalTransition,
    ImmutableOperatorError,
    ImmutableRoleError,
    OperatorIdentity,
    RoleMetadata,
    SessionRecord,
    access_event_id,
    access_request_id,
    approval_id,
    audit_report_id,
    can_transition,
    compliance_score,
    content_hash,
    finding,
    identity_hash as _identity_hash,
    input_digest,
    is_pending,
    is_valid_decision,
    parse_ts,
    role_hash as _role_hash,
    session_id as _session_id,
    session_status,
)

_UNUSUAL_REQUEST_THRESHOLD = 5


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


def _known_actions() -> set:
    """기존 permission 정책의 알려진 action 집합(READ ONLY 대조용)."""
    try:
        from jarvis.permissions.policy import ACTION_PERMISSIONS
        return set(ACTION_PERMISSIONS)
    except Exception:  # noqa: BLE001
        return set()


class AccessGovernanceEngine:
    """접근 거버넌스 엔진. 불변·append-only·결정적. 권한부여/실행 없음."""

    # ── register_operator ──
    def register_operator(self, operator_id: str, name: str, email: str, roles: list,
                          status: str = "ACTIVE", now: str = "",
                          *, commit: bool = False) -> OperatorIdentity:
        ih = _identity_hash(operator_id, name, email, roles)
        for o in ledger.read_operators():
            if o.get("operator_id") == operator_id:
                if o.get("identity_hash") != ih:
                    raise ImmutableOperatorError(f"{operator_id} 신원 불변 — 변경 불가")
                return OperatorIdentity(**{k: v for k, v in o.items()
                                           if k in OperatorIdentity.__dataclass_fields__})
        rec = OperatorIdentity(
            operator_id=operator_id, name=name, email=email, roles=list(roles or []),
            status=status, created_at=now, identity_hash=ih, input_hash=ih,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.identity_hash_exists(ih):
            head = ledger.operators_head()
            ledger.append_operator(_seal(rec, head["record_hash"] if head else GENESIS))
        return OperatorIdentity(**rec)

    # ── register_role(서술 메타 — 실제 권한 부여 아님) ──
    def register_role(self, role_id: str, name: str, description: str, scope: list,
                      now: str = "", *, commit: bool = False) -> RoleMetadata:
        rh = _role_hash(role_id, name, description, scope)
        for r in ledger.read_roles():
            if r.get("role_id") == role_id:
                if r.get("role_hash") != rh:
                    raise ImmutableRoleError(f"{role_id} 역할 메타 불변 — 변경 불가")
                return RoleMetadata(**{k: v for k, v in r.items()
                                       if k in RoleMetadata.__dataclass_fields__})
        rec = RoleMetadata(
            role_hash=rh, role_id=role_id, name=name, description=description,
            scope=list(scope or []), created_at=now, input_hash=rh,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.role_hash_exists(rh):
            head = ledger.roles_head()
            ledger.append_role(_seal(rec, head["record_hash"] if head else GENESIS))
        return RoleMetadata(**rec)

    # ── create_session ──
    def create_session(self, operator_id: str, started_at: str, expires_at: str,
                       context: dict | None = None, now: str = "",
                       *, commit: bool = False) -> SessionRecord:
        sid = _session_id(operator_id, started_at)
        status = session_status(expires_at, now or started_at)
        rec = SessionRecord(
            session_id=sid, operator_id=operator_id, started_at=started_at,
            expires_at=expires_at, status=status, context=dict(context or {}),
            input_hash=input_digest(operator_id, started_at, expires_at),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.session_exists(sid):
            head = ledger.sessions_head()
            ledger.append_session(_seal(rec, head["record_hash"] if head else GENESIS))
        return SessionRecord(**rec)

    # ── 접근요청 상태머신 ──
    def _req_meta(self, rid: str) -> dict | None:
        evs = ledger.access_events_for(rid)
        return evs[0] if evs else None

    def current_state(self, rid: str) -> str:
        evs = ledger.access_events_for(rid)
        return evs[-1].get("to_state", "") if evs else ""

    def _emit(self, rid: str, meta: dict, frm: str, to: str, now: str,
              *, actor: str, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단")
        eid = access_event_id(rid, frm, to)
        rec = AccessRequest(
            event_id=eid, request_id=rid, operator_id=meta["operator_id"],
            resource=meta["resource"], requested_scope=meta["requested_scope"],
            reason=meta["reason"], from_state=frm, to_state=to, status=to, created_at=now,
            actor=actor, input_hash=input_digest(rid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.access_event_exists(eid):
            head = ledger.access_events_head()
            ledger.append_access_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def request_access(self, operator_id: str, resource: str, requested_scope: str,
                       reason: str = "", now: str = "", *, commit: bool = False) -> str:
        rid = access_request_id(operator_id, resource, requested_scope)
        meta = {"operator_id": operator_id, "resource": resource,
                "requested_scope": requested_scope, "reason": reason}
        if not ledger.access_events_for(rid):
            self._emit(rid, meta, "", REQUESTED, now, actor=operator_id, commit=commit)
        return rid

    def _advance(self, rid: str, to: str, now: str, *, actor: str, commit: bool) -> dict:
        meta = self._req_meta(rid)
        if meta is None:
            raise IllegalTransition(f"미존재 접근요청 {rid}")
        return self._emit(rid, meta, self.current_state(rid), to, now, actor=actor,
                          commit=commit)

    def review_access(self, rid: str, now: str = "", *, actor: str = "reviewer",
                      commit: bool = False) -> dict:
        return self._advance(rid, REVIEWED, now, actor=actor, commit=commit)

    def expire_access(self, rid: str, now: str = "", *, actor: str = "system",
                      commit: bool = False) -> dict:
        return self._advance(rid, EXPIRED, now, actor=actor, commit=commit)

    # ── approve_access (REVIEWED→APPROVED/REJECTED) ──
    def approve_access(self, rid: str, approver: str, decision: str, reason: str = "",
                       now: str = "", *, commit: bool = False) -> AccessApproval:
        if not approver:
            raise ApprovalError("승인자 필요")
        if not is_valid_decision(decision):
            raise ApprovalError(f"허용되지 않은 결정: {decision}")
        meta = self._req_meta(rid)
        if meta is None:
            raise ApprovalError(f"미존재 접근요청 {rid}")
        cur = self.current_state(rid)
        if cur != REVIEWED:
            raise IllegalTransition(f"승인은 REVIEWED 에서만 가능(현재 {cur})")
        aid = approval_id(rid, approver, decision)
        rec = AccessApproval(
            approval_id=aid, request_id=rid, approver=approver, decision=decision,
            reason=reason, created_at=now, input_hash=input_digest(rid, approver, decision),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.approval_exists(aid):
            head = ledger.approvals_head()
            ledger.append_approval(_seal(rec, head["record_hash"] if head else GENESIS))
        self._advance(rid, APPROVED if decision == APPROVE else REJECTED, now,
                      actor=approver, commit=commit)
        return AccessApproval(**rec)

    # ── audit_access (결정적 감사 체크) ──
    def audit_access(self, now: str = "", *, commit: bool = False) -> AccessAuditReport:
        operators = {o.get("operator_id") for o in ledger.read_operators()}
        # 역할 id → scope 집합, 운영자 → 할당 역할들의 scope 합집합
        role_scope_map = {r.get("role_id"): set(r.get("scope", []))
                          for r in ledger.read_roles()}
        role_scopes: dict = {}
        for o in ledger.read_operators():
            allowed: set = set()
            for rid in o.get("roles", []):
                allowed |= role_scope_map.get(rid, set())
            role_scopes[o.get("operator_id")] = allowed
        known_actions = _known_actions()
        approvals_by_req: dict = {}
        for a in ledger.read_approvals():
            approvals_by_req.setdefault(a.get("request_id"), []).append(a)

        # 접근요청 fold
        req_latest: dict = {}
        req_meta: dict = {}
        req_count_by_op: dict = {}
        for ev in ledger.read_access_events():
            rid = ev.get("request_id")
            req_latest[rid] = ev.get("to_state")
            if rid not in req_meta:
                req_meta[rid] = ev
                op = ev.get("operator_id")
                req_count_by_op[op] = req_count_by_op.get(op, 0) + 1

        findings = []

        # 1. unknown operator (세션/요청이 미등록 운영자 참조)
        for s in ledger.read_sessions():
            if s.get("operator_id") not in operators:
                findings.append(finding("unknown_operator", s.get("session_id", ""),
                                        WARNING, f"미등록 운영자 세션 {s.get('operator_id')}"))
        for rid, meta in sorted(req_meta.items()):
            if meta.get("operator_id") not in operators:
                findings.append(finding("unknown_operator", rid, WARNING,
                                        f"미등록 운영자 요청 {meta.get('operator_id')}"))

        # 2. expired session (만료됐는데 ACTIVE 로 기록됨)
        for s in ledger.read_sessions():
            if s.get("status") == ACTIVE and session_status(s.get("expires_at", ""), now) == EXPIRED:
                findings.append(finding("expired_session", s.get("session_id", ""), WARNING,
                                        "만료된 세션이 ACTIVE 상태로 기록됨"))

        # 3. missing approval (APPROVED 인데 승인 기록 없음)
        for rid, state in sorted(req_latest.items()):
            if state == APPROVED and not approvals_by_req.get(rid):
                findings.append(finding("missing_approval", rid, CRITICAL,
                                        "APPROVED 이나 승인 기록 부재"))

        # 4. unusual access pattern (요청 과다)
        for op, cnt in sorted(req_count_by_op.items()):
            if cnt > _UNUSUAL_REQUEST_THRESHOLD:
                findings.append(finding("unusual_access_pattern", str(op), INFO,
                                        f"접근요청 {cnt}건(임계 {_UNUSUAL_REQUEST_THRESHOLD} 초과)"))

        # 5. policy mismatch (요청 scope 가 운영자 역할/알려진 action 과 불일치)
        for rid, meta in sorted(req_meta.items()):
            scope = meta.get("requested_scope", "")
            op = meta.get("operator_id")
            in_role = scope in role_scopes.get(op, set())
            in_policy = (scope in known_actions) if known_actions else True
            if not in_role and not in_policy:
                findings.append(finding("policy_mismatch", rid, WARNING,
                                        f"요청 scope '{scope}' 가 역할/정책과 불일치"))

        findings = sorted({f.finding_id: f for f in findings}.values(),
                          key=lambda f: f.sort_key())
        crit = sum(1 for f in findings if f.severity == CRITICAL)
        warn = sum(1 for f in findings if f.severity == WARNING)
        info = sum(1 for f in findings if f.severity == INFO)
        score = compliance_score(crit, warn, info)
        checks = {"operators": len(operators), "sessions": len(ledger.read_sessions()),
                  "access_requests": len(req_meta), "approvals": len(ledger.read_approvals())}
        ih = input_digest([f.finding_id for f in findings], sorted(checks.items()))
        rid_ = audit_report_id(ih)
        rec = AccessAuditReport(
            report_id=rid_, timestamp=now, checks=checks,
            findings=[f.to_dict() for f in findings], critical_findings=crit,
            warning_findings=warn, info_findings=info, compliance_score=score, input_hash=ih,
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.audit_report_exists(rid_):
            head = ledger.audit_reports_head()
            ledger.append_audit_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return AccessAuditReport(**rec)

    # ── generate_report(요약) ──
    def generate_report(self, now: str = "") -> AccessGovernanceReport:
        operators = {o.get("operator_id") for o in ledger.read_operators()}
        roles = {r.get("role_id") for r in ledger.read_roles()}
        sessions = ledger.read_sessions()
        active = sum(1 for s in sessions
                     if session_status(s.get("expires_at", ""), now) == ACTIVE)
        rids = {ev.get("request_id") for ev in ledger.read_access_events()}
        dist: dict = {}
        pending = approved = 0
        for rid in rids:
            st = self.current_state(rid)
            dist[st] = dist.get(st, 0) + 1
            if is_pending(st):
                pending += 1
            elif st == APPROVED:
                approved += 1
        return AccessGovernanceReport(
            timestamp=now, operator_count=len(operators), role_count=len(roles),
            session_count=len(sessions), active_sessions=active,
            request_state_distribution=dict(sorted(dist.items())), pending_requests=pending,
            approved_requests=approved)
