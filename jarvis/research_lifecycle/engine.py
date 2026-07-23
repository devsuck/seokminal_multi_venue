"""Research Lifecycle Engine (P10.26) — 전 모듈 연구 생명주기 추적. **관찰·기록 전용.**

P10.2~P10.25 를 READ ONLY 로 참조(파일 기반, import 없음)해 연구 프로젝트 생명주기(IDEA→HYPOTHESIS→
EXPERIMENT→BACKTEST→VALIDATION→DECISION→ARCHIVE)를 이벤트 소싱으로 추적하고 스테이지 전이·생명주기 이벤트·
병목·리포트를 남긴다. **실행·배포·승인·거래 없음.** execution/broker/order/portfolio execution/capital
allocation/live trading/permission/risk controller import·호출 없음. LIFECYCLE TRACKING ≠ EXECUTION ·
TRANSITION ≠ APPROVAL · STAGE ≠ DEPLOYMENT · RECORD ≠ DECISION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_lifecycle import ledger
from jarvis.research_lifecycle.models import (
    ARCHIVE,
    ART_BOTTLENECK,
    ART_EVENT,
    ART_LAYER,
    ART_PROJECT,
    ART_REPORT,
    ART_TRANSITION,
    BOTTLENECK_CATEGORIES,
    DECISION,
    EVENT_TYPES,
    GENESIS,
    IDEA,
    STAGES,
    BottleneckRecord,
    IllegalTransition,
    ImmutableBottleneckError,
    ImmutableEventError,
    InvalidBottleneckCategory,
    InvalidEventType,
    InvalidStage,
    LifecycleArtifact,
    LifecycleEvent,
    LifecycleReport,
    LifecycleSummary,
    ProjectEvent,
    StageTransition,
    UnknownProject,
    artifact_id as _artifact_id,
    bottleneck_id as _bottleneck_id,
    can_transition_stage,
    completion_ratio,
    content_hash,
    detect_cycle,
    event_id as _event_id,
    input_digest,
    missing_stages as _missing_stages,
    project_event_id,
    project_id as _project_id,
    report_id as _report_id,
    transition_id as _transition_id,
)

_DISCLAIMER = ("연구 생명주기 추적 데이터 — LIFECYCLE TRACKING ≠ EXECUTION · TRANSITION ≠ APPROVAL · "
               "STAGE ≠ DEPLOYMENT · RECORD ≠ DECISION. 실행/배포/승인/거래 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchLifecycleEngine:
    """연구 생명주기 추적 엔진. 불변·append-only·결정적. 실행/배포/승인/거래 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = LifecycleArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_layer_artifact(self, source_layer: str, now: str, *, commit: bool) -> str:
        return self._record_artifact(ART_LAYER, source_layer, "", now,
                                     commit=commit)["artifact_id"]

    # ── Research Project (이벤트 소싱, 생명주기 상태기계) ──
    def project_stage(self, project_id: str) -> str:
        evs = ledger.project_events_for(project_id)
        return evs[-1].get("to_stage", "") if evs else ""

    def entered_stages(self, project_id: str) -> list:
        """프로젝트가 진입한 스테이지 목록(순서대로)."""
        return [e.get("to_stage") for e in ledger.project_events_for(project_id)]

    def _project_meta(self, project_id: str) -> dict | None:
        evs = ledger.project_events_for(project_id)
        return evs[0] if evs else None

    def _emit_project_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_stage(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(생명주기 스테이지)")
        pid = meta["project_id"]
        eid = project_event_id(pid, frm, to)
        rec = ProjectEvent(
            event_id=eid, project_id=pid, name=meta["name"], source_layer=meta["source_layer"],
            source_reference=meta["source_reference"], from_stage=frm, to_stage=to, stage=to,
            created_at=now, input_hash=input_digest(pid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.project_event_exists(eid):
            head = ledger.projects_head()
            ledger.append_project_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_project(self, name: str, source_layer: str = "", source_reference: str = "",
                       now: str = "", *, commit: bool = False) -> ProjectEvent:
        """연구 프로젝트를 생명주기 시작(IDEA)으로 등록. **추적 시작 — 결정/승인 없음.**"""
        pid = _project_id(name)
        existing = ledger.project_events_for(pid)
        if existing:
            return ProjectEvent(**existing[-1])
        if source_layer:
            self._ensure_layer_artifact(source_layer, now, commit=commit)
        meta = {"project_id": pid, "name": name, "source_layer": source_layer,
                "source_reference": source_reference}
        rec = self._emit_project_event(meta, "", IDEA, now, commit=commit)
        parent = _artifact_id(ART_LAYER, source_layer) if source_layer and \
            ledger.artifact_exists(_artifact_id(ART_LAYER, source_layer)) else ""
        self._record_artifact(ART_PROJECT, pid, parent, now, commit=commit)
        self._record_transition(pid, "", IDEA, "registered", now, commit=commit)
        return ProjectEvent(**rec)

    def advance_stage(self, project_ref: str, to_stage: str, note: str = "", now: str = "",
                    *, commit: bool = False) -> dict:
        """프로젝트를 다음 스테이지로 전이(검증)하고 전이 기록을 남긴다. **전이 ≠ 승인.**"""
        if to_stage not in STAGES:
            raise InvalidStage(f"미등록 스테이지 {to_stage}")
        meta = self._project_meta(project_ref)
        if meta is None:
            raise UnknownProject(f"미존재 프로젝트 {project_ref}")
        frm = self.project_stage(project_ref)
        self._emit_project_event(meta, frm, to_stage, now, commit=commit)
        self._record_transition(project_ref, frm, to_stage, note, now, commit=commit)
        return {"project_id": project_ref, "from_stage": frm, "to_stage": to_stage,
                "stage": self.project_stage(project_ref)}

    def transition_project(self, project_ref: str, to_stage: str, now: str = "",
                         *, commit: bool = False) -> dict:
        return self.advance_stage(project_ref, to_stage, "", now, commit=commit)

    # ── Stage Transition 기록(불변) ──
    def _record_transition(self, project_id: str, frm: str, to: str, note: str, now: str,
                          *, commit: bool) -> dict:
        tid = _transition_id(project_id, frm, to)
        rec = StageTransition(
            transition_id=tid, project_id=project_id, from_stage=frm, to_stage=to, note=note,
            created_at=now, input_hash=input_digest(project_id, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.transition_exists(tid):
            head = ledger.transitions_head()
            ledger.append_transition(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_PROJECT, project_id) if ledger.artifact_exists(
            _artifact_id(ART_PROJECT, project_id)) else ""
        self._record_artifact(ART_TRANSITION, tid, parent, now, commit=commit)
        return rec

    # ── Lifecycle Event (불변) ──
    def record_event(self, project_ref: str, event_type: str, reference: str, detail: str = "",
                   now: str = "", *, commit: bool = False) -> LifecycleEvent:
        """프로젝트에 생명주기 이벤트를 기록(현재 스테이지 스탬프). **관찰·기록만.**"""
        if event_type not in EVENT_TYPES:
            raise InvalidEventType(f"미등록 이벤트 유형 {event_type}")
        eid = _event_id(project_ref, event_type, reference)
        existing = next((e for e in ledger.read_events() if e.get("event_id") == eid), None)
        if existing is not None:
            if existing.get("detail") != detail:
                raise ImmutableEventError(f"{eid} 생명주기 이벤트 불변 — 변경 불가")
            return LifecycleEvent(**{k: v for k, v in existing.items()
                                     if k in LifecycleEvent.__dataclass_fields__})
        stage = self.project_stage(project_ref)
        rec = LifecycleEvent(
            event_id=eid, project_id=project_ref, event_type=event_type, reference=reference,
            detail=detail, stage=stage, timestamp=now, created_at=now,
            input_hash=input_digest(project_ref, event_type, reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_PROJECT, project_ref) if ledger.artifact_exists(
            _artifact_id(ART_PROJECT, project_ref)) else ""
        self._record_artifact(ART_EVENT, eid, parent, now, commit=commit)
        return LifecycleEvent(**rec)

    # ── Bottleneck (불변) ──
    def record_bottleneck(self, project_ref: str, stage: str, category: str,
                        severity: str = "MEDIUM", detail: str = "", evidence: list | None = None,
                        now: str = "", *, commit: bool = False) -> BottleneckRecord:
        """생명주기 병목을 기록. category 검증. **탐지·기록만 — 자동 조치 없음.**"""
        if category not in BOTTLENECK_CATEGORIES:
            raise InvalidBottleneckCategory(f"미등록 병목 범주 {category}")
        bid = _bottleneck_id(project_ref, stage, category)
        existing = ledger.get_bottleneck(bid)
        if existing is not None:
            return BottleneckRecord(**{k: v for k, v in existing.items()
                                       if k in BottleneckRecord.__dataclass_fields__})
        rec = BottleneckRecord(
            bottleneck_id=bid, project_id=project_ref, stage=stage, category=category,
            severity=severity, detail=detail, evidence=list(evidence or []), created_at=now,
            input_hash=input_digest(project_ref, stage, category),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.bottleneck_exists(bid):
            head = ledger.bottlenecks_head()
            ledger.append_bottleneck(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_PROJECT, project_ref) if ledger.artifact_exists(
            _artifact_id(ART_PROJECT, project_ref)) else ""
        self._record_artifact(ART_BOTTLENECK, bid, parent, now, commit=commit)
        return BottleneckRecord(**rec)

    # ── 누락 스테이지 탐지 ──
    def detect_missing_stages(self, project_ref: str) -> list:
        """프로젝트 생명주기에서 누락된 정규 스테이지 목록(ARCHIVE 제외). **정보용 — 조치 없음.**"""
        if self._project_meta(project_ref) is None:
            raise UnknownProject(f"미존재 프로젝트 {project_ref}")
        return _missing_stages(self.entered_stages(project_ref))

    def completion(self, project_ref: str) -> float:
        return completion_ratio(self.entered_stages(project_ref))

    def stalled_projects(self, blocking_stages: tuple = (IDEA,)) -> list:
        """지정 스테이지에 머문(진행 안 된) 프로젝트. **정보용 — 개입 없음.**"""
        out: list = []
        for p in ledger.distinct_projects():
            st = self.project_stage(p.get("project_id"))
            if st in blocking_stages:
                out.append(p.get("project_id"))
        return sorted(out)

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """생명주기 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
        issues: list = []
        arts = ledger.read_artifacts()
        ids = {a.get("artifact_id") for a in arts}
        edges: list = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
        by_id = {a.get("artifact_id"): a for a in ledger.read_artifacts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(artifact_ref)
        while cur:
            parent = cur.get("parent_artifact")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ── Lifecycle Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                      *, commit: bool = False) -> LifecycleReport:
        m = dict(metrics or {})
        projects = ledger.distinct_projects()
        stage_dist: dict = {}
        archived = 0
        decision_reached = 0
        completions: list = []
        missing_summary: dict = {}
        for p in projects:
            pid = p.get("project_id")
            st = self.project_stage(pid)
            stage_dist[st] = stage_dist.get(st, 0) + 1
            entered = self.entered_stages(pid)
            if ARCHIVE in entered:
                archived += 1
            if DECISION in entered:
                decision_reached += 1
            completions.append(completion_ratio(entered))
            for ms in _missing_stages(entered):
                missing_summary[ms] = missing_summary.get(ms, 0) + 1
        events = ledger.read_events()
        et_dist: dict = {}
        for e in events:
            et_dist[e.get("event_type")] = et_dist.get(e.get("event_type"), 0) + 1
        bns = ledger.read_bottlenecks()
        bc_dist: dict = {}
        for b in bns:
            bc_dist[b.get("category")] = bc_dist.get(b.get("category"), 0) + 1
        avg = round(sum(completions) / len(completions), 8) if completions else 0.0
        rid = _report_id(scope)
        rec = LifecycleReport(
            report_id=rid, scope=scope, project_count=len(projects),
            stage_distribution=dict(sorted(stage_dist.items())),
            transition_count=len(ledger.read_transitions()), event_count=len(events),
            event_type_distribution=dict(sorted(et_dist.items())), bottleneck_count=len(bns),
            bottleneck_category_distribution=dict(sorted(bc_dist.items())), archived_count=archived,
            completed_decision_count=decision_reached, average_completion=avg,
            missing_stage_summary=dict(sorted(missing_summary.items())), metrics=m,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return LifecycleReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        seen: set = set()
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref and ref not in seen:
                seen.add(ref)
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Summary ──
    def summary(self, now: str = "") -> LifecycleSummary:
        projects = ledger.distinct_projects()
        stage_dist: dict = {}
        for p in projects:
            st = self.project_stage(p.get("project_id"))
            stage_dist[st] = stage_dist.get(st, 0) + 1
        return LifecycleSummary(
            timestamp=now, project_count=len(projects),
            stage_distribution=dict(sorted(stage_dist.items())),
            transition_count=len(ledger.read_transitions()), event_count=len(ledger.read_events()),
            bottleneck_count=len(ledger.read_bottlenecks()),
            report_count=len(ledger.read_reports()))
