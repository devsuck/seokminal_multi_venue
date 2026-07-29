"""Autonomous Research Organization Engine (P11.13) — 조직 조정. **조직 전용.**

연구 에이전트·프로세스·지식·의사결정 시스템의 조직 조정을 관리한다. **거래 실행·전략 배포·라이브 승인·자본
배분·모델/전략 수정·권한 변경·자율 실행 인가를 하지 않는다.** execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. 건강 지표는 분석 전용 — 자동 재배정·승인·실행을 유발하지 않는다. ORGANIZATION
≠ EXECUTION · ROLE ≠ AUTHORIZATION · METRIC ≠ ACTION. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_organization import ledger
from jarvis.research_organization.models import (
    AGENT_ROLES,
    ART_ORG,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_UNIT,
    GENESIS,
    O_ACTIVE,
    O_ARCHIVED,
    O_CONFIGURED,
    O_COORDINATING,
    O_CREATED,
    O_REVIEWED,
    RESP_DEFINED,
    UNIT_TYPES,
    ArtifactRecord,
    CircularDependencyError,
    DanglingReferenceError,
    IllegalOrgTransition,
    ImmutableOrganizationError,
    ImmutablePolicyError,
    ImmutableResponsibilityError,
    ImmutableRoleError,
    ImmutableTeamError,
    ImmutableUnitError,
    ImmutableWorkflowError,
    InvalidAgentRole,
    InvalidUnitType,
    MissingOwnerError,
    OrgEventRecord,
    OrgReportRecord,
    OrgSummary,
    PolicyRecord,
    ResponsibilityRecord,
    RoleRecord,
    SnapshotRecord,
    TeamRecord,
    UnitRecord,
    UnknownOrganizationError,
    UnknownUnitError,
    WorkflowOwnershipRecord,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    detect_cycle,
    input_digest,
    org_event_id as _org_event_id,
    org_id as _org_id,
    policy_id as _policy_id,
    ratio,
    report_id as _report_id,
    responsibility_id as _responsibility_id,
    role_id as _role_id,
    snapshot_id as _snapshot_id,
    team_id as _team_id,
    unit_id as _unit_id,
    workflow_id as _workflow_id,
)

_DISCLAIMER = ("Research Organization 데이터 — ORGANIZATION ≠ EXECUTION · ROLE ≠ AUTHORIZATION · METRIC ≠ "
               "ACTION. 조직 조정·기록·분석 전용 — 거래 실행·전략 배포·라이브 승인·자본 배분·모델/전략 수정·"
               "권한/설정 변경·자율 실행 인가 없음. 건강 지표는 분석 전용이며 자동 재배정/승인/실행을 유발하지 "
               "않는다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOrganizationEngine:
    """자율 연구 조직 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/배포/승인/인가 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ 조직 생애주기(event-sourced) ══════════════
    def _org_event(self, org: str, name: str, mandate: str, frm: str, to: str, note: str, now: str,
                *, commit: bool) -> OrgEventRecord:
        seq = len(ledger.org_events(org))
        eid = _org_event_id(org, to, seq)
        rec = OrgEventRecord(org_event_id=eid, org_id=org, name=name, mandate=mandate, from_state=frm,
                             to_state=to, note=note, occurred_at=now,
                             input_hash=input_digest(org, to, seq), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.org_event_exists(eid):
            head = ledger.organizations_head()
            ledger.append_org_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return OrgEventRecord(**rec)

    def _org_meta(self, org: str) -> dict:
        evs = ledger.org_events(org)
        if not evs:
            raise UnknownOrganizationError(f"미등록 조직 {org}")
        g = evs[0]
        return {"org_id": org, "name": g.get("name"), "mandate": g.get("mandate"),
                "state": evs[-1].get("to_state")}

    def current_state(self, org: str) -> str | None:
        evs = ledger.org_events(org)
        return evs[-1].get("to_state") if evs else None

    def _require_org(self, org: str) -> str:
        st = self.current_state(org)
        if st is None:
            raise UnknownOrganizationError(f"미등록 조직 {org}")
        return st

    def _transition(self, org: str, to: str, note: str, now: str,
                  *, commit: bool) -> OrgEventRecord:
        frm = self._require_org(org)
        if not can_transition(frm, to):
            raise IllegalOrgTransition(f"{org} {frm}→{to} 불가")
        m = self._org_meta(org)
        return self._org_event(org, m["name"], m["mandate"], frm, to, note, now, commit=commit)

    # ══════════════ register_organization ══════════════
    def register_organization(self, name: str, mandate: str = "", now: str = "",
                           *, commit: bool = False) -> OrgEventRecord:
        """조직 생성(genesis CREATED). **등록만.**"""
        org = _org_id(name)
        evs = ledger.org_events(org)
        if evs:
            g = evs[0]
            if g.get("mandate") != mandate:
                raise ImmutableOrganizationError(f"{org} 조직 불변 — 변경 불가")
            return OrgEventRecord(**{k: v for k, v in g.items()
                                     if k in OrgEventRecord.__dataclass_fields__})
        ev = self._org_event(org, name, mandate, GENESIS, O_CREATED, "created", now, commit=commit)
        self._artifact(ART_ORG, org, "", now, commit=commit)
        return ev

    def org_meta(self, org: str) -> dict:
        return self._org_meta(org)

    # ══════════════ create_research_unit (→CONFIGURED) ══════════════
    def create_research_unit(self, org: str, unit_type: str, name: str, description: str = "",
                          now: str = "", *, commit: bool = False) -> UnitRecord:
        """연구 유닛 생성(불변). 첫 유닛에서 CREATED→CONFIGURED. **구조 정의만.**"""
        st = self._require_org(org)
        if unit_type not in UNIT_TYPES:
            raise InvalidUnitType(f"미등록 유닛 유형 {unit_type}")
        uid = _unit_id(org, unit_type, name)
        existing = ledger.get_unit(uid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableUnitError(f"{uid} 유닛 불변 — 변경 불가")
            return UnitRecord(**{k: v for k, v in existing.items()
                                 if k in UnitRecord.__dataclass_fields__})
        rec = UnitRecord(unit_id=uid, org_id=org, unit_type=unit_type, name=name,
                         description=description, created_at=now,
                         input_hash=input_digest(org, unit_type, name),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.unit_exists(uid):
            head = ledger.units_head()
            ledger.append_unit(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == O_CREATED:
            self._transition(org, O_CONFIGURED, "configured", now, commit=commit)
        parent = _artifact_id(ART_ORG, org)
        self._artifact(ART_UNIT, uid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return UnitRecord(**rec)

    def _require_unit(self, uid: str) -> dict:
        rec = ledger.get_unit(uid)
        if rec is None:
            raise UnknownUnitError(f"미등록 유닛 {uid}")
        return rec

    # ══════════════ create_research_team ══════════════
    def create_research_team(self, unit: str, name: str, description: str = "", now: str = "",
                          *, commit: bool = False) -> TeamRecord:
        """연구 팀 생성(불변, 유닛 하위). **구조 정의만.**"""
        u = self._require_unit(unit)
        tid = _team_id(unit, name)
        existing = ledger.get_team(tid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableTeamError(f"{tid} 팀 불변 — 변경 불가")
            return TeamRecord(**{k: v for k, v in existing.items()
                                 if k in TeamRecord.__dataclass_fields__})
        rec = TeamRecord(team_id=tid, unit_id=unit, org_id=u.get("org_id"), name=name,
                         description=description, created_at=now, input_hash=input_digest(unit, name),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.team_exists(tid):
            head = ledger.teams_head()
            ledger.append_team(_seal(rec, head["record_hash"] if head else GENESIS))
        return TeamRecord(**rec)

    # ══════════════ assign_agent_role ══════════════
    def assign_agent_role(self, unit: str, agent: str, role: str, team: str = "", now: str = "",
                       *, commit: bool = False) -> RoleRecord:
        """에이전트 역할 배정(불변). 유닛 필수(orphan 방지). **배정 기록만 — 인가 아님.**"""
        u = self._require_unit(unit)
        if role not in AGENT_ROLES:
            raise InvalidAgentRole(f"미등록 역할 {role}")
        if team and not ledger.team_exists(team):
            raise DanglingReferenceError(f"미등록 팀 {team}")
        rid = _role_id(unit, agent, role)
        existing = ledger.get_role(rid)
        if existing is not None:
            if existing.get("team_id") != team:
                raise ImmutableRoleError(f"{rid} 역할 배정 불변 — 변경 불가")
            return RoleRecord(**{k: v for k, v in existing.items()
                                 if k in RoleRecord.__dataclass_fields__})
        rec = RoleRecord(role_id=rid, org_id=u.get("org_id"), unit_id=unit, team_id=team,
                         agent=agent, role=role, created_at=now,
                         input_hash=input_digest(unit, agent, role),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.role_exists(rid):
            head = ledger.roles_head()
            ledger.append_role(_seal(rec, head["record_hash"] if head else GENESIS))
        return RoleRecord(**rec)

    # ══════════════ define_responsibility ══════════════
    def define_responsibility(self, org: str, owner: str, scope: str, input_sources=None,
                           expected_output: str = "", evidence_reference: str = "",
                           lifecycle_state: str = RESP_DEFINED, now: str = "",
                           *, commit: bool = False) -> ResponsibilityRecord:
        """책임 정의(불변). owner·scope·input_sources·expected_output·evidence·lifecycle 보존. **정의·기록만.**"""
        self._require_org(org)
        if not owner:
            raise MissingOwnerError("책임 소유자 누락")
        rid = _responsibility_id(org, owner, scope)
        existing = ledger.get_responsibility(rid)
        if existing is not None:
            if existing.get("expected_output") != expected_output:
                raise ImmutableResponsibilityError(f"{rid} 책임 불변 — 변경 불가")
            return ResponsibilityRecord(**{k: v for k, v in existing.items()
                                           if k in ResponsibilityRecord.__dataclass_fields__})
        rec = ResponsibilityRecord(
            responsibility_id=rid, org_id=org, owner=owner, scope=scope,
            input_sources=sorted(set(input_sources or [])), expected_output=expected_output,
            evidence_reference=evidence_reference, lifecycle_state=lifecycle_state, created_at=now,
            input_hash=input_digest(org, owner, scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.responsibility_exists(rid):
            head = ledger.responsibilities_head()
            ledger.append_responsibility(_seal(rec, head["record_hash"] if head else GENESIS))
        return ResponsibilityRecord(**rec)

    # ══════════════ map_workflow_owner ══════════════
    def _workflow_edges(self) -> list:
        out: list = []
        for w in ledger.read_workflows():
            for dep in w.get("depends_on", []):
                out.append((w.get("workflow_id"), dep))
        return out

    def map_workflow_owner(self, org: str, workflow_name: str, owner_unit: str, input_sources=None,
                        depends_on=None, now: str = "", *, commit: bool = False) -> WorkflowOwnershipRecord:
        """워크플로 소유 매핑(불변). owner 유닛 검증·의존 순환 거부. **매핑·기록만.**"""
        self._require_org(org)
        if owner_unit and not ledger.unit_exists(owner_unit):
            raise DanglingReferenceError(f"미등록 소유 유닛 {owner_unit}")
        wid = _workflow_id(org, workflow_name)
        deps = sorted(set(depends_on or []))
        existing = ledger.get_workflow(wid)
        if existing is not None:
            if existing.get("owner_unit") != owner_unit:
                raise ImmutableWorkflowError(f"{wid} 워크플로 소유 불변 — 변경 불가")
            return WorkflowOwnershipRecord(**{k: v for k, v in existing.items()
                                              if k in WorkflowOwnershipRecord.__dataclass_fields__})
        for dep in deps:
            if not ledger.workflow_exists(dep):
                raise DanglingReferenceError(f"미등록 의존 워크플로 {dep}")
        if deps:
            edges = self._workflow_edges() + [(wid, d) for d in deps]
            if detect_cycle(edges):
                raise CircularDependencyError(f"순환 워크플로 의존성 — 거부 {wid}")
        rec = WorkflowOwnershipRecord(
            workflow_id=wid, org_id=org, workflow_name=workflow_name, owner_unit=owner_unit,
            input_sources=sorted(set(input_sources or [])), depends_on=deps, created_at=now,
            input_hash=input_digest(org, workflow_name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workflow_exists(wid):
            head = ledger.workflows_head()
            ledger.append_workflow(_seal(rec, head["record_hash"] if head else GENESIS))
        return WorkflowOwnershipRecord(**rec)

    # ══════════════ create_coordination_policy (→COORDINATING) ══════════════
    def create_coordination_policy(self, org: str, name: str, policy_type: str = "", rule: str = "",
                                now: str = "", *, commit: bool = False) -> PolicyRecord:
        """조정 정책 생성(불변). ACTIVE→COORDINATING 전이. **정책 정의만 — 실행 아님.**"""
        st = self._require_org(org)
        pid = _policy_id(org, name)
        existing = ledger.policy_exists(pid)
        cur = None
        for r in ledger.org_policies(org):
            if r.get("policy_id") == pid:
                cur = r
                break
        if cur is not None:
            if cur.get("rule") != rule:
                raise ImmutablePolicyError(f"{pid} 정책 불변 — 변경 불가")
            return PolicyRecord(**{k: v for k, v in cur.items()
                                   if k in PolicyRecord.__dataclass_fields__})
        rec = PolicyRecord(policy_id=pid, org_id=org, name=name, policy_type=policy_type, rule=rule,
                           created_at=now, input_hash=input_digest(org, name),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not existing:
            head = ledger.policies_head()
            ledger.append_policy(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == O_ACTIVE:
            self._transition(org, O_COORDINATING, "coordinating", now, commit=commit)
        return PolicyRecord(**rec)

    # ══════════════ 조직 상태 전이 헬퍼(수동, 자동 아님) ══════════════
    def activate_organization(self, org: str, now: str = "", *, commit: bool = False) -> OrgEventRecord:
        """CONFIGURED→ACTIVE (수동 전이). **상태 기록만.**"""
        return self._transition(org, O_ACTIVE, "active", now, commit=commit)

    def review_organization(self, org: str, now: str = "", *, commit: bool = False) -> OrgEventRecord:
        """COORDINATING→REVIEWED (수동 전이). **상태 기록만.**"""
        return self._transition(org, O_REVIEWED, "reviewed", now, commit=commit)

    def archive_organization(self, org: str, now: str = "", *, commit: bool = False) -> OrgEventRecord:
        return self._transition(org, O_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ evaluate_organization_state (분석 전용, 자동 실행 없음) ══════════════
    def evaluate_organization_state(self, org: str) -> dict:
        """조직 건강 지표(분석 전용). **자동 재배정/승인/실행 없음 — 순수 분석.**"""
        self._require_org(org)
        units = ledger.org_units(org)
        uids = {u.get("unit_id") for u in units}
        workflows = ledger.org_workflows(org)
        resps = ledger.org_responsibilities(org)
        # coordination_completeness: 역할+책임 관련 유닛 비율
        role_units = {r.get("unit_id") for r in ledger.read_roles() if r.get("org_id") == org}
        complete_units = sum(1 for u in uids if u in role_units)
        coordination_completeness = ratio(complete_units, len(uids))
        # ownership_coverage: 소유 유닛이 존재하는 워크플로 비율
        owned = sum(1 for w in workflows if w.get("owner_unit") in uids)
        ownership_coverage = ratio(owned, len(workflows))
        # dependency_clarity: 의존이 존재 워크플로를 참조하는 비율 + 순환 없음
        wids = {w.get("workflow_id") for w in workflows}
        total_deps = sum(len(w.get("depends_on", [])) for w in workflows)
        clear_deps = sum(1 for w in workflows for d in w.get("depends_on", []) if d in wids)
        has_cycle = bool(detect_cycle(self._workflow_edges()))
        dependency_clarity = 0.0 if has_cycle else ratio(clear_deps, total_deps)
        # research_throughput: 유닛+워크플로+역할 활동량(분석 카운트)
        research_throughput = len(units) + len(workflows) + len(role_units)
        # unresolved_conflicts: orphan 역할 + dangling 워크플로 의존 + 소유자 누락 책임
        orphan_roles = sum(1 for r in ledger.read_roles()
                           if r.get("org_id") == org and r.get("unit_id") not in uids)
        dangling_deps = total_deps - clear_deps
        ownerless_resp = sum(1 for r in resps if not r.get("owner"))
        unresolved_conflicts = orphan_roles + dangling_deps + ownerless_resp
        return {"org_id": org, "state": self.current_state(org),
                "coordination_completeness": coordination_completeness,
                "ownership_coverage": ownership_coverage,
                "dependency_clarity": dependency_clarity,
                "research_throughput": research_throughput,
                "unresolved_conflicts": unresolved_conflicts,
                "has_dependency_cycle": has_cycle,
                "is_analytical": True,
                "note": "METRIC ≠ ACTION — no automatic reassignment/approval/execution"}

    # ══════════════ 조정 프레임워크 조회 ══════════════
    def dependency_map(self, org: str) -> dict:
        return {w.get("workflow_id"): sorted(w.get("depends_on", []))
                for w in ledger.org_workflows(org)}

    def ownership_graph(self, org: str) -> dict:
        return {w.get("workflow_id"): w.get("owner_unit")
                for w in ledger.org_workflows(org)}

    def workflow_routing_map(self, org: str) -> dict:
        return {w.get("workflow_id"): {"owner": w.get("owner_unit"),
                                       "inputs": sorted(w.get("input_sources", []))}
                for w in ledger.org_workflows(org)}

    def identify_bottlenecks(self, org: str) -> list:
        """병목: 다른 워크플로가 많이 의존하는 워크플로(결정적)."""
        indeg: dict = {}
        for w in ledger.org_workflows(org):
            for d in w.get("depends_on", []):
                indeg[d] = indeg.get(d, 0) + 1
        return sorted(indeg.items(), key=lambda kv: (-kv[1], kv[0]))

    # ══════════════ snapshot_organization ══════════════
    def snapshot_organization(self, org: str, scope: str = "ALL", now: str = "",
                           *, commit: bool = False) -> SnapshotRecord:
        """조직 스냅샷(유닛·역할 분포, 결정적). **관찰·기록만.**"""
        self._require_org(org)
        units = ledger.org_units(org)
        roles = [r for r in ledger.read_roles() if r.get("org_id") == org]
        utype_dist: dict = {}
        for u in units:
            utype_dist[u.get("unit_type")] = utype_dist.get(u.get("unit_type"), 0) + 1
        role_dist: dict = {}
        for r in roles:
            role_dist[r.get("role")] = role_dist.get(r.get("role"), 0) + 1
        sid = _snapshot_id(org, scope, now)
        rec = SnapshotRecord(snapshot_id=sid, org_id=org, scope=scope,
                             org_state=self.current_state(org), unit_count=len(units),
                             role_count=len(roles),
                             unit_type_distribution=dict(sorted(utype_dist.items())),
                             role_distribution=dict(sorted(role_dist.items())), taken_at=now,
                             input_hash=input_digest(org, scope, now),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, org: str, scope: str = "ALL", now: str = "",
                      *, commit: bool = False) -> OrgReportRecord:
        """조직 리포트(유닛·팀·역할·책임·워크플로·정책·건강). **is_binding=False, 관찰·분석만.**"""
        self._require_org(org)
        units = ledger.org_units(org)
        teams = [t for t in ledger.read_teams() if t.get("org_id") == org]
        roles = [r for r in ledger.read_roles() if r.get("org_id") == org]
        health = self.evaluate_organization_state(org)
        rid = _report_id(org, scope, now)
        rec = OrgReportRecord(
            report_id=rid, org_id=org, scope=scope, unit_count=len(units), team_count=len(teams),
            role_count=len(roles), responsibility_count=len(ledger.org_responsibilities(org)),
            workflow_count=len(ledger.org_workflows(org)),
            policy_count=len(ledger.org_policies(org)),
            health={k: v for k, v in health.items()
                    if k in ("coordination_completeness", "ownership_coverage",
                             "dependency_clarity", "research_throughput", "unresolved_conflicts")},
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(org, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_ORG, org)
        self._artifact(ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", now,
                       commit=commit)
        return OrgReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_organization.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_organizations(self) -> list:
        return ledger.org_ids()

    def list_units(self, org: str = "") -> list:
        us = ledger.read_units()
        if org:
            us = [u for u in us if u.get("org_id") == org]
        return sorted(u.get("unit_id") for u in us)

    def organizations_in_state(self, state: str) -> list:
        return sorted(o for o in ledger.org_ids() if self.current_state(o) == state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> OrgSummary:
        return OrgSummary(
            timestamp=now, org_event_count=len(ledger.read_org_events()),
            unit_count=len(ledger.read_units()), team_count=len(ledger.read_teams()),
            role_count=len(ledger.read_roles()),
            responsibility_count=len(ledger.read_responsibilities()),
            workflow_count=len(ledger.read_workflows()), policy_count=len(ledger.read_policies()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
