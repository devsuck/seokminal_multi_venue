"""Research Control Plane Engine (P10.28) — Research OS 중앙 관측·조율 평면. **관측 전용.**

전 계층(P9.8~P10.27)을 READ ONLY 로 참조(파일 기반, import 없음)해 컴포넌트 등록·계층 상태 수집·시스템 맵
구성·헬스 점수 계산·의존성 이슈 탐지·컨트롤 리포트 생성·상태 검증을 수행한다. **실행 컨트롤러가 아니다 —
관측·집계·시각화·리포트만.** execute/trade/order/allocation/deployment/permission·config 변경 없음.
OBSERVE ≠ EXECUTE · STATUS ≠ CONTROL · HEALTH ≠ ACTION · REPORT ≠ DEPLOYMENT. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_control_plane import ledger
from jarvis.research_control_plane.models import (
    CATEGORIES,
    GENESIS,
    REL_READS,
    STATE_ACTIVE,
    STATE_EMPTY,
    STATE_MISSING,
    TL_COMPONENT_REGISTERED,
    TL_DEPENDENCY_MAPPED,
    TL_HEALTH_COMPUTED,
    TL_OVERVIEW_BUILT,
    TL_REPORT_GENERATED,
    TL_STATUS_COLLECTED,
    ComponentRecord,
    ControlPlaneSummary,
    ControlReportRecord,
    DependencyRecord,
    GovernanceDashboardRecord,
    HealthMetricRecord,
    ImmutableComponentError,
    ImmutableDashboardError,
    ImmutableDependencyError,
    ImmutableHealthError,
    ImmutableOverviewError,
    ImmutableReportError,
    ImmutableStatusError,
    InvalidComponentCategory,
    LayerStatusRecord,
    SystemOverviewRecord,
    TimelineEventRecord,
    UnknownComponentError,
    component_id as _component_id,
    content_hash,
    dashboard_id as _dashboard_id,
    dependency_id as _dependency_id,
    dependency_issues,
    health_id as _health_id,
    health_level,
    health_score,
    input_digest,
    overview_id as _overview_id,
    report_id as _report_id,
    status_id as _status_id,
    timeline_id as _timeline_id,
)

_DISCLAIMER = ("Research Control Plane 데이터 — OBSERVE ≠ EXECUTE · STATUS ≠ CONTROL · HEALTH ≠ ACTION · "
               "REPORT ≠ DEPLOYMENT. 중앙 관측·집계·리포트 전용 — 실행/배포/할당/권한·설정 변경 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchControlPlaneEngine:
    """중앙 관측·조율 엔진. 불변·append-only·결정적. 실행/배포/변경 권한 없음."""

    # ── 타임라인(내부 기록) ──
    def _record_timeline(self, kind: str, reference: str, detail: str, now: str,
                         *, commit: bool) -> dict:
        eid = _timeline_id(kind, reference, now)
        rec = TimelineEventRecord(
            event_id=eid, kind=kind, reference=reference, detail=detail, occurred_at=now,
            input_hash=input_digest(kind, reference, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.timeline_exists(eid):
            head = ledger.timeline_head()
            ledger.append_timeline(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── register_component ──
    def register_component(self, name: str, layer: str = "", phase: str = "", category: str = "OTHER",
                          ledger_file: str = "", id_field: str = "", now: str = "",
                          *, commit: bool = False) -> ComponentRecord:
        """컴포넌트(계층/서브시스템)를 관측 대상으로 등록. **관측 등록만 — 실행 권한 부여 아님.**"""
        if category not in CATEGORIES:
            raise InvalidComponentCategory(f"미등록 카테고리 {category}")
        cid = _component_id(name)
        existing = ledger.get_component(cid)
        if existing is not None:
            if existing.get("layer") != layer or existing.get("phase") != phase or \
                    existing.get("category") != category:
                raise ImmutableComponentError(f"{cid} 컴포넌트 불변 — 변경 불가")
            return ComponentRecord(**{k: v for k, v in existing.items()
                                      if k in ComponentRecord.__dataclass_fields__})
        rec = ComponentRecord(
            component_id=cid, name=name, layer=layer or name, phase=phase, category=category,
            ledger_file=ledger_file, id_field=id_field, registered_at=now,
            input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.component_exists(cid):
            head = ledger.components_head()
            ledger.append_component(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_timeline(TL_COMPONENT_REGISTERED, cid, name, now, commit=commit)
        return ComponentRecord(**rec)

    def discover_components(self, now: str = "", *, commit: bool = False) -> list:
        """상위 소스 카탈로그(P9.8~P10.27)에서 컴포넌트를 발견·등록. **READ ONLY 발견.**"""
        out: list = []
        for name in sorted(ledger.SOURCE_LEDGERS):
            filename, id_field, phase, category = ledger.SOURCE_LEDGERS[name]
            out.append(self.register_component(name, name, phase, category, filename, id_field,
                                               now, commit=commit))
        return out

    # ── collect_status ──
    def collect_status(self, component: str, now: str = "", *, commit: bool = False) -> LayerStatusRecord:
        """등록 컴포넌트의 상위 원장을 READ ONLY 로 읽어 계층 상태(레코드 수·활동) 스냅샷. **읽기만.**"""
        cid = _component_id(component)
        comp = ledger.get_component(cid)
        spec = ledger.SOURCE_LEDGERS.get(component)
        filename = (comp.get("ledger_file") if comp else "") or (spec[0] if spec else "")
        if not filename:
            raise UnknownComponentError(f"미등록/미지정 컴포넌트 {component}")
        present = ledger.source_exists(filename)
        records = ledger.read_source(filename) if present else []
        count = len(records)
        if not present:
            state = STATE_MISSING
        elif count == 0:
            state = STATE_EMPTY
        else:
            state = STATE_ACTIVE
        last = ledger.source_last_activity(records)
        sid = _status_id(component, now)
        existing = ledger.get_status(sid)
        if existing is not None:
            if existing.get("record_count") != count or existing.get("state") != state:
                raise ImmutableStatusError(f"{sid} 계층 상태 불변 — 변경 불가")
            return LayerStatusRecord(**{k: v for k, v in existing.items()
                                        if k in LayerStatusRecord.__dataclass_fields__})
        rec = LayerStatusRecord(
            status_id=sid, component=component, state=state, record_count=count, present=present,
            last_activity=last, observed_at=now, input_hash=input_digest(component, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.status_exists(sid):
            head = ledger.status_head()
            ledger.append_status(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_timeline(TL_STATUS_COLLECTED, sid, f"{component}:{state}:{count}", now,
                              commit=commit)
        return LayerStatusRecord(**rec)

    def collect_all_status(self, now: str = "", *, commit: bool = False) -> list:
        """등록된 모든 컴포넌트 상태 수집(이름순, 결정적). **읽기만.**"""
        names = sorted({c.get("name") for c in ledger.read_components() if c.get("name")})
        return [self.collect_status(n, now, commit=commit) for n in names]

    # ── build_system_map ──
    def build_system_map(self, edges: list, now: str = "", *, commit: bool = False) -> list:
        """의존성 간선 [(source,target)] 을 의존성 상태로 기록해 시스템 맵 구성. **관측 맵 — 실행 순서 아님.**"""
        out: list = []
        for src, tgt in edges:
            did = _dependency_id(src, tgt)
            existing = ledger.get_dependency(did)
            if existing is not None:
                out.append(DependencyRecord(**{k: v for k, v in existing.items()
                                               if k in DependencyRecord.__dataclass_fields__}))
                continue
            rec = DependencyRecord(
                dependency_id=did, source=src, target=tgt, relation=REL_READS, created_at=now,
                input_hash=input_digest(src, tgt), previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.dependency_exists(did):
                head = ledger.dependencies_head()
                ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
            self._record_timeline(TL_DEPENDENCY_MAPPED, did, f"{src}->{tgt}", now, commit=commit)
            out.append(DependencyRecord(**rec))
        return out

    def system_map(self) -> dict:
        """현재 시스템 맵(노드=컴포넌트 이름, 간선=의존성). **조회 전용.**"""
        nodes = sorted({c.get("name") for c in ledger.read_components() if c.get("name")})
        edges = sorted({(d.get("source"), d.get("target")) for d in ledger.read_dependencies()})
        return {"nodes": nodes, "edges": [list(e) for e in edges],
                "node_count": len(nodes), "edge_count": len(edges)}

    # ── detect_dependency_issue ──
    def detect_dependency_issue(self) -> dict:
        """의존성 이슈(self·dangling·missing source·cycle) 탐지. **탐지·보고만 — 수정 없음.**"""
        m = self.system_map()
        edges = [(e[0], e[1]) for e in m["edges"]]
        issues = dependency_issues(edges, m["nodes"])
        return {"ok": not issues, "issues": issues, "issue_count": len(issues),
                "node_count": m["node_count"], "edge_count": m["edge_count"]}

    # ── calculate_health_score ──
    def calculate_health_score(self, scope: str = "GLOBAL", now: str = "",
                              *, commit: bool = False) -> HealthMetricRecord:
        """컴포넌트 활성 비율·의존성 무결성으로 헬스 점수·등급 산출·기록. **HEALTH ≠ ACTION.**"""
        components = ledger.read_components()
        total = len(components)
        active = self._active_component_count()
        dep = self.detect_dependency_issue()
        dep_count = dep["edge_count"]
        issue_count = dep["issue_count"]
        score = health_score(active, total, issue_count, dep_count)
        comp_h = round((float(active) / total) if total > 0 else 0.0, 8)
        dep_h = round(max(0.0, min(1.0, (1.0 - float(issue_count) / dep_count) if dep_count > 0
                                   else 1.0)), 8)
        level = health_level(score, total)
        hid = _health_id(scope, now)
        existing = ledger.get_health(hid)
        if existing is not None:
            if abs(float(existing.get("overall_score", -1)) - score) > 1e-9:
                raise ImmutableHealthError(f"{hid} 헬스 지표 불변 — 변경 불가")
            return HealthMetricRecord(**{k: v for k, v in existing.items()
                                         if k in HealthMetricRecord.__dataclass_fields__})
        rec = HealthMetricRecord(
            health_id=hid, scope=scope, component_count=total, active_component_count=active,
            dependency_count=dep_count, dependency_issue_count=issue_count,
            component_health=comp_h, dependency_health=dep_h, overall_score=score, level=level,
            computed_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.health_exists(hid):
            head = ledger.health_head()
            ledger.append_health(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_timeline(TL_HEALTH_COMPUTED, hid, f"{scope}:{level}:{score}", now,
                              commit=commit)
        return HealthMetricRecord(**rec)

    def _active_component_count(self) -> int:
        """최신 상태가 ACTIVE 인 컴포넌트 수(컴포넌트별 마지막 상태 기준)."""
        last: dict = {}
        for s in ledger.read_status():
            last[s.get("component")] = s.get("state")
        return sum(1 for st in last.values() if st == STATE_ACTIVE)

    # ── System Overview ──
    def build_system_overview(self, scope: str = "GLOBAL", now: str = "",
                             *, commit: bool = False) -> SystemOverviewRecord:
        """시스템 개요 스냅샷(컴포넌트·활성·의존성·헬스·phase/category 분포). **결정적 스냅샷.**"""
        components = ledger.read_components()
        total = len(components)
        active = self._active_component_count()
        dep = self.detect_dependency_issue()
        score = health_score(active, total, dep["issue_count"], dep["edge_count"])
        level = health_level(score, total)
        phase_dist: dict = {}
        cat_dist: dict = {}
        for c in components:
            phase_dist[c.get("phase")] = phase_dist.get(c.get("phase"), 0) + 1
            cat_dist[c.get("category")] = cat_dist.get(c.get("category"), 0) + 1
        oid = _overview_id(scope, now)
        existing = ledger.get_overview(oid)
        if existing is not None:
            if existing.get("component_count") != total or existing.get("health_level") != level:
                raise ImmutableOverviewError(f"{oid} 시스템 개요 불변 — 변경 불가")
            return SystemOverviewRecord(**{k: v for k, v in existing.items()
                                           if k in SystemOverviewRecord.__dataclass_fields__})
        rec = SystemOverviewRecord(
            overview_id=oid, scope=scope, component_count=total, active_component_count=active,
            dependency_count=dep["edge_count"], dependency_issue_count=dep["issue_count"],
            overall_score=score, health_level=level,
            phase_distribution=dict(sorted(phase_dist.items())),
            category_distribution=dict(sorted(cat_dist.items())), disclaimer=_DISCLAIMER,
            snapshot_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.overview_exists(oid):
            head = ledger.overview_head()
            ledger.append_overview(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_timeline(TL_OVERVIEW_BUILT, oid, f"{scope}:{level}", now, commit=commit)
        return SystemOverviewRecord(**rec)

    # ── Governance Dashboard Data ──
    def build_dashboard(self, scope: str = "GLOBAL", now: str = "",
                       *, commit: bool = False) -> GovernanceDashboardRecord:
        """거버넌스 대시보드 데이터(카테고리별 컴포넌트·상태 패널) 집계. **읽기·집계만.**"""
        components = ledger.read_components()
        total = len(components)
        active = self._active_component_count()
        dep = self.detect_dependency_issue()
        score = health_score(active, total, dep["issue_count"], dep["edge_count"])
        level = health_level(score, total)
        by_cat: dict = {}
        for c in components:
            by_cat.setdefault(c.get("category"), 0)
            by_cat[c.get("category")] += 1
        last_state: dict = {}
        for s in ledger.read_status():
            last_state[s.get("component")] = s.get("state")
        state_dist: dict = {}
        for st in last_state.values():
            state_dist[st] = state_dist.get(st, 0) + 1
        panels = {
            "by_category": dict(sorted(by_cat.items())),
            "by_state": dict(sorted(state_dist.items())),
            "dependency_issue_count": dep["issue_count"],
            "timeline_event_count": len(ledger.read_timeline()),
        }
        bid = _dashboard_id(scope, now)
        existing = ledger.get_dashboard(bid)
        if existing is not None:
            if existing.get("panels") != panels:
                raise ImmutableDashboardError(f"{bid} 대시보드 불변 — 변경 불가")
            return GovernanceDashboardRecord(**{k: v for k, v in existing.items()
                                                if k in GovernanceDashboardRecord.__dataclass_fields__})
        rec = GovernanceDashboardRecord(
            dashboard_id=bid, scope=scope, component_count=total, active_component_count=active,
            health_level=level, overall_score=score, panels=panels, disclaimer=_DISCLAIMER,
            generated_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dashboard_exists(bid):
            head = ledger.dashboard_head()
            ledger.append_dashboard(_seal(rec, head["record_hash"] if head else GENESIS))
        return GovernanceDashboardRecord(**rec)

    # ── generate_control_report ──
    def generate_control_report(self, scope: str = "GLOBAL", metrics: dict | None = None,
                               now: str = "", *, commit: bool = False) -> ControlReportRecord:
        """컨트롤 리포트(개요+헬스+의존성 이슈+분포) 생성. **관측 리포트 — 실행 지시 아님.**"""
        m = dict(metrics or {})
        components = ledger.read_components()
        total = len(components)
        active = self._active_component_count()
        dep = self.detect_dependency_issue()
        score = health_score(active, total, dep["issue_count"], dep["edge_count"])
        level = health_level(score, total)
        phase_dist: dict = {}
        cat_dist: dict = {}
        for c in components:
            phase_dist[c.get("phase")] = phase_dist.get(c.get("phase"), 0) + 1
            cat_dist[c.get("category")] = cat_dist.get(c.get("category"), 0) + 1
        rid = _report_id(scope, now)
        rec = ControlReportRecord(
            report_id=rid, scope=scope, component_count=total, active_component_count=active,
            dependency_count=dep["edge_count"], dependency_issue_count=dep["issue_count"],
            overall_score=score, health_level=level,
            phase_distribution=dict(sorted(phase_dist.items())),
            category_distribution=dict(sorted(cat_dist.items())), issues=dep["issues"], metrics=m,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_timeline(TL_REPORT_GENERATED, rid, f"{scope}:{level}", now, commit=commit)
        return ControlReportRecord(**rec)

    # ── verify_state ──
    def verify_state(self) -> dict:
        """전체 상태 검증: 원장 체인·의존성 그래프 무결성. **읽기 전용 — 변경 없음.**"""
        from jarvis.research_control_plane.verify import verify_chain
        return verify_chain()

    # ── 조회 편의 ──
    def latest_status(self, component: str) -> dict | None:
        found = None
        for s in ledger.read_status():
            if s.get("component") == component:
                found = s
        return found

    def latest_health(self, scope: str = "GLOBAL") -> dict | None:
        found = None
        for h in ledger.read_health():
            if h.get("scope") == scope:
                found = h
        return found

    def list_components(self, category: str = "") -> list:
        comps = ledger.read_components()
        if category:
            comps = [c for c in comps if c.get("category") == category]
        return sorted(c.get("name") for c in comps if c.get("name"))

    # ── Summary ──
    def summary(self, now: str = "") -> ControlPlaneSummary:
        return ControlPlaneSummary(
            timestamp=now, component_count=len(ledger.read_components()),
            status_count=len(ledger.read_status()),
            dependency_count=len(ledger.read_dependencies()),
            overview_count=len(ledger.read_overview()),
            dashboard_count=len(ledger.read_dashboard()),
            timeline_count=len(ledger.read_timeline()),
            health_count=len(ledger.read_health()), report_count=len(ledger.read_reports()))
