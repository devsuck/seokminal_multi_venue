"""Research Observatory Engine (P10.10) — 전 연구 계층 관찰·집계·시각화. **관측·기록 전용.**

P10.2~P10.9 연구 계층을 READ ONLY 로 소비해 스냅샷·교차계층 지표·의존 그래프·타임라인·트렌드·
대시보드·리포트를 집계한다. **관측 계층이다.** execution/broker/portfolio mutation/risk mutation/
capital allocation/order/deploy/promote/permission/config/autonomy 변경 없음. OBSERVED ≠ APPROVED ·
OBSERVED ≠ DEPLOYED · OBSERVED ≠ EXECUTED. 상위 레이어 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_observatory import ledger
from jarvis.research_observatory.models import (
    ANALYZING,
    ARCHIVED,
    ART_DASHBOARD,
    ART_DEPENDENCY,
    ART_METRICS,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_TIMELINE,
    ART_TREND,
    COLLECTING,
    CREATED,
    DEPENDENCY_FLOW,
    GENESIS,
    REPORTING,
    Dashboard,
    DependencyEdge,
    IllegalTransition,
    ImmutableSnapshotError,
    ObservatoryArtifact,
    ObservatoryMetric,
    ObservatoryReport,
    ObservatorySummary,
    SnapshotEvent,
    TimelineEvent,
    TrendReport,
    UnknownSnapshot,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    dashboard_id as _dashboard_id,
    dependency_id as _dependency_id,
    detect_cycle,
    graph_density,
    input_digest,
    metric_id as _metric_id,
    ratio,
    report_id as _report_id,
    snapshot_event_id,
    snapshot_id as _snapshot_id,
    timeline_id as _timeline_id,
    trend_direction,
    trend_id as _trend_id,
)

_DISCLAIMER = ("관측·집계 데이터 — OBSERVED ≠ APPROVED · OBSERVED ≠ DEPLOYED · "
               "OBSERVED ≠ EXECUTED. 선택/승인/배포/실행 아님.")

# 타임라인 이벤트 유형 매핑(레이어 → 이벤트)
_TIMELINE_LAYERS = {
    "STRATEGY": "STRATEGY_CREATED",
    "SIGNAL": "SIGNAL_CREATED",
    "EXPERIMENT": "EXPERIMENT_STARTED",
    "PORTFOLIO": "PORTFOLIO_CREATED",
    "VALIDATION": "VALIDATION_COMPLETED",
    "SIMULATION": "SIMULATION_FINISHED",
    "DECISION": "DECISION_GENERATED",
}

# collect 대상 계층
_METRIC_LAYERS = ("STRATEGY", "SIGNAL", "FEATURE", "DATASET", "EXPERIMENT", "PORTFOLIO",
                  "VALIDATION", "DECISION", "SIMULATION", "AGENT")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchObservatoryEngine:
    """연구 관측·컨트롤 플레인 엔진. 불변·append-only·결정적. 선택/승인/배포/실행 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         snapshot_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = ObservatoryArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, snapshot_id=snapshot_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── 소스 카운트(READ ONLY) ──
    def _counts(self) -> dict:
        return {layer: ledger.count_source(layer) for layer in
                ("STRATEGY", "SIGNAL", "FEATURE", "DATASET", "EXPERIMENT", "PORTFOLIO",
                 "VALIDATION", "DECISION", "SIMULATION", "AGENT", "KG_ENTITY", "KG_RELATION")}

    def _replay_stats(self) -> tuple:
        rows = ledger.read_source("rv_replay_reports.jsonl")
        total = len(rows)
        ok = sum(1 for r in rows if r.get("result") == "REPRODUCIBLE")
        return ok, total

    def _score_grades(self) -> dict:
        rows = ledger.read_source("rv_scores.jsonl")
        dist: dict = {}
        for r in rows:
            g = r.get("grade", "")
            dist[g] = dist.get(g, 0) + 1
        return dist

    # ── Snapshot Registry (이벤트 소싱, 불변) ──
    def snapshot_state(self, snapshot_id: str) -> str:
        evs = ledger.snapshot_events_for(snapshot_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _snapshot_meta(self, snapshot_id: str) -> dict | None:
        evs = ledger.snapshot_events_for(snapshot_id)
        return evs[0] if evs else None

    def _emit_snapshot_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(observatory)")
        sid = meta["snapshot_id"]
        eid = snapshot_event_id(sid, frm, to)
        rec = SnapshotEvent(
            event_id=eid, snapshot_id=sid, name=meta["name"], epoch=meta["epoch"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(sid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_event_exists(eid):
            head = ledger.snapshots_head()
            ledger.append_snapshot_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_snapshot(self, name: str, epoch: str = "", now: str = "",
                        *, commit: bool = False) -> SnapshotEvent:
        """관측 스냅샷을 생성(CREATED). **관찰만 — 어떤 운영 상태도 바꾸지 않는다.**"""
        sid = _snapshot_id(name, epoch)
        existing = ledger.snapshot_events_for(sid)
        if existing:
            first = existing[0]
            if first.get("name") != name or first.get("epoch") != epoch:
                raise ImmutableSnapshotError(f"{sid} 스냅샷 불변 — 변경 불가")
            return SnapshotEvent(**existing[-1])
        meta = {"snapshot_id": sid, "name": name, "epoch": epoch}
        rec = self._emit_snapshot_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_SNAPSHOT, sid, "", sid, now, commit=commit)
        return SnapshotEvent(**rec)

    def transition_snapshot(self, snapshot_id: str, to: str, now: str = "", *,
                            commit: bool = False) -> dict:
        meta = self._snapshot_meta(snapshot_id)
        if meta is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        return self._emit_snapshot_event(meta, self.snapshot_state(snapshot_id), to, now,
                                         commit=commit)

    def _safe_advance(self, snapshot_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._snapshot_meta(snapshot_id)
        if meta is None:
            return
        cur = self.snapshot_state(snapshot_id)
        if cur != to and can_transition(cur, to):
            self._emit_snapshot_event(meta, cur, to, now, commit=commit)

    def archive(self, snapshot_id: str, now: str = "", *, commit: bool = False) -> dict:
        return self.transition_snapshot(snapshot_id, ARCHIVED, now, commit=commit)

    # ── Cross-layer Collection (READ ONLY) ──
    def _emit_metric(self, snapshot_id: str, layer: str, name: str, value: float, now: str,
                     *, commit: bool) -> dict:
        mid = _metric_id(snapshot_id, layer, name)
        rec = ObservatoryMetric(
            metric_id=mid, snapshot_id=snapshot_id, layer=layer, metric_name=name,
            value=round(float(value), 8), created_at=now,
            input_hash=input_digest(snapshot_id, layer, name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.metric_exists(mid):
            head = ledger.metrics_head()
            ledger.append_metric(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def collect(self, snapshot_id: str, now: str = "", *, commit: bool = False) -> list:
        """상위 레이어를 READ ONLY 로 스캔해 교차계층 지표를 수집. CREATED→COLLECTING 진행."""
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        counts = self._counts()
        out: list = []
        for layer in _METRIC_LAYERS:
            out.append(self._emit_metric(snapshot_id, layer, "count", counts.get(layer, 0), now,
                                         commit=commit))
        out.append(self._emit_metric(snapshot_id, "KNOWLEDGE_GRAPH", "entities",
                                     counts.get("KG_ENTITY", 0), now, commit=commit))
        out.append(self._emit_metric(snapshot_id, "KNOWLEDGE_GRAPH", "connections",
                                     counts.get("KG_RELATION", 0), now, commit=commit))
        ok, total = self._replay_stats()
        out.append(self._emit_metric(snapshot_id, "REPLAY", "success_rate", ratio(ok, total),
                                     now, commit=commit))
        self._record_artifact(ART_METRICS, snapshot_id,
                              _artifact_id(ART_SNAPSHOT, snapshot_id), snapshot_id, now,
                              commit=commit)
        self._safe_advance(snapshot_id, COLLECTING, now, commit=commit)
        return [ObservatoryMetric(**r) for r in out]

    # ── Dependency Graph ──
    def dependency_map(self, snapshot_id: str, now: str = "", *,
                       commit: bool = False) -> list:
        """계층 간 정방향 의존 흐름을 기록. broken dependency·cycle 탐지. **자동 수정 없음.**"""
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        counts = self._counts()
        out: list = []
        for frm, to in DEPENDENCY_FLOW:
            fc = counts.get(frm, 0)
            tc = counts.get(to, 0)
            broken = tc > 0 and fc == 0
            did = _dependency_id(snapshot_id, frm, to)
            rec = DependencyEdge(
                dependency_id=did, snapshot_id=snapshot_id, from_layer=frm, to_layer=to,
                from_count=fc, to_count=tc, broken=broken, created_at=now,
                input_hash=input_digest(snapshot_id, frm, to), previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.dependency_exists(did):
                head = ledger.dependencies_head()
                ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
            out.append(rec)
        self._record_artifact(ART_DEPENDENCY, snapshot_id,
                              _artifact_id(ART_SNAPSHOT, snapshot_id), snapshot_id, now,
                              commit=commit)
        return [DependencyEdge(**r) for r in out]

    def dependency_cycle(self, snapshot_id: str) -> list:
        edges = [(d.get("from_layer"), d.get("to_layer"))
                 for d in ledger.dependencies_for_snapshot(snapshot_id)]
        return detect_cycle(edges)

    # ── Timeline ──
    def _distinct_source_rows(self, layer: str) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field, created_field, _ev = spec
        seen: dict = {}
        for r in ledger.read_source(filename):
            rid = r.get(id_field)
            if rid is not None and rid not in seen:
                seen[rid] = r
        return list(seen.values())

    def build_timeline(self, snapshot_id: str, now: str = "", *,
                       commit: bool = False) -> list:
        """상위 레이어의 created_at 을 시간순으로 집계(READ ONLY). 읽기 전용 집계."""
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        events: list = []
        for layer, ev_type in _TIMELINE_LAYERS.items():
            spec = ledger.SOURCE_LEDGERS.get(layer)
            if not spec:
                continue
            id_field = spec[1]
            created_field = spec[2]
            for r in self._distinct_source_rows(layer):
                events.append((r.get(created_field, "") or "", layer, ev_type,
                               str(r.get(id_field))))
        events.sort(key=lambda e: (e[0], e[1], e[3]))
        out: list = []
        for ts, layer, ev_type, ref in events:
            tid = _timeline_id(snapshot_id, layer, ev_type, ref)
            rec = TimelineEvent(
                timeline_id=tid, snapshot_id=snapshot_id, layer=layer, event_type=ev_type,
                reference=ref, timestamp=ts, created_at=now,
                input_hash=input_digest(snapshot_id, layer, ev_type, ref),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.timeline_exists(tid):
                head = ledger.timelines_head()
                ledger.append_timeline(_seal(rec, head["record_hash"] if head else GENESIS))
            out.append(rec)
        self._record_artifact(ART_TIMELINE, snapshot_id,
                              _artifact_id(ART_SNAPSHOT, snapshot_id), snapshot_id, now,
                              commit=commit)
        return [TimelineEvent(**r) for r in out]

    # ── Trend Analytics ──
    def _previous_snapshot(self, snapshot_id: str) -> str | None:
        snaps = [s.get("snapshot_id") for s in ledger.distinct_snapshots()]
        if snapshot_id in snaps:
            idx = snaps.index(snapshot_id)
            return snaps[idx - 1] if idx > 0 else None
        return None

    def _prev_trend_value(self, snapshot_id: str, name: str) -> float | None:
        prev = self._previous_snapshot(snapshot_id)
        if prev is None:
            return None
        for t in ledger.read_trends():
            if t.get("snapshot_id") == prev and t.get("name") == name:
                return t.get("value")
        return None

    def trend_analysis(self, snapshot_id: str, now: str = "", *,
                       commit: bool = False) -> list:
        """트렌드 지표 계산·기록. **자동 의사결정 없음 — 서술 방향 라벨만.** COLLECTING→ANALYZING."""
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        c = self._counts()
        ok, total = self._replay_stats()
        scores = ledger.read_source("rv_scores.jsonl")
        val_ok = sum(1 for s in scores if float(s.get("overall_score", 0.0)) >= 0.7)
        trends = {
            "validation_success_rate": ratio(val_ok, len(scores)),
            "replay_success_rate": ratio(ok, total),
            "experiment_growth": float(c.get("EXPERIMENT", 0)),
            "dataset_reuse": ratio(c.get("FEATURE", 0), c.get("DATASET", 0)),
            "feature_reuse": ratio(c.get("SIGNAL", 0), c.get("FEATURE", 0)),
            "knowledge_graph_density": graph_density(c.get("KG_ENTITY", 0),
                                                     c.get("KG_RELATION", 0)),
            "simulation_volume": float(c.get("SIMULATION", 0)),
        }
        out: list = []
        for name, value in trends.items():
            prev = self._prev_trend_value(snapshot_id, name)
            direction = trend_direction(value, prev)
            tid = _trend_id(snapshot_id, name)
            rec = TrendReport(
                trend_id=tid, snapshot_id=snapshot_id, name=name, value=round(value, 8),
                previous_value=round(prev, 8) if prev is not None else 0.0,
                direction=direction, created_at=now, input_hash=input_digest(snapshot_id, name),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.trend_exists(tid):
                head = ledger.trends_head()
                ledger.append_trend(_seal(rec, head["record_hash"] if head else GENESIS))
            out.append(rec)
        self._record_artifact(ART_TREND, snapshot_id,
                              _artifact_id(ART_SNAPSHOT, snapshot_id), snapshot_id, now,
                              commit=commit)
        self._safe_advance(snapshot_id, COLLECTING, now, commit=commit)
        self._safe_advance(snapshot_id, ANALYZING, now, commit=commit)
        return [TrendReport(**r) for r in out]

    # ── Dashboard (관찰 정보만) ──
    def dashboard(self, snapshot_id: str, now: str = "", *, commit: bool = False) -> Dashboard:
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        c = self._counts()
        ok, total = self._replay_stats()
        broken = sum(1 for frm, to in DEPENDENCY_FLOW
                     if c.get(to, 0) > 0 and c.get(frm, 0) == 0)
        n_edges = len(DEPENDENCY_FLOW)
        metrics = {
            "total_strategies": c.get("STRATEGY", 0),
            "total_signals": c.get("SIGNAL", 0),
            "total_experiments": c.get("EXPERIMENT", 0),
            "total_simulations": c.get("SIMULATION", 0),
            "total_validations": c.get("VALIDATION", 0),
            "replay_success": ratio(ok, total),
            "lineage_integrity": ratio(n_edges - broken, n_edges),
            "validation_score_distribution": dict(sorted(self._score_grades().items())),
        }
        did = _dashboard_id(snapshot_id)
        rec = Dashboard(
            dashboard_id=did, snapshot_id=snapshot_id, metrics=metrics, created_at=now,
            input_hash=input_digest(snapshot_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.dashboard_exists(did):
            head = ledger.dashboards_head()
            ledger.append_dashboard(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_DASHBOARD, snapshot_id,
                              _artifact_id(ART_SNAPSHOT, snapshot_id), snapshot_id, now,
                              commit=commit)
        return Dashboard(**rec)

    # ── Observatory Report ──
    def generate_report(self, snapshot_id: str, now: str = "", *,
                        commit: bool = False) -> ObservatoryReport:
        if self._snapshot_meta(snapshot_id) is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        meta = self._snapshot_meta(snapshot_id)
        deps = ledger.dependencies_for_snapshot(snapshot_id)
        broken = sum(1 for d in deps if d.get("broken"))
        dash = self.dashboard(snapshot_id, now, commit=commit)
        rid = _report_id(snapshot_id)
        rec = ObservatoryReport(
            report_id=rid, snapshot_id=snapshot_id, name=meta.get("name", ""),
            metric_count=len(ledger.metrics_for_snapshot(snapshot_id)),
            dependency_count=len(deps), broken_dependency_count=broken,
            timeline_count=len(ledger.timelines_for_snapshot(snapshot_id)),
            trend_count=len([t for t in ledger.read_trends()
                             if t.get("snapshot_id") == snapshot_id]),
            dashboard_metrics=dash.metrics, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(snapshot_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, snapshot_id,
                              _artifact_id(ART_DASHBOARD, snapshot_id), snapshot_id, now,
                              commit=commit)
        self._safe_advance(snapshot_id, COLLECTING, now, commit=commit)
        self._safe_advance(snapshot_id, ANALYZING, now, commit=commit)
        self._safe_advance(snapshot_id, REPORTING, now, commit=commit)
        return ObservatoryReport(**rec)

    # ── Summary ──
    def summary(self, now: str = "") -> ObservatorySummary:
        snaps = ledger.distinct_snapshots()
        sstate: dict = {}
        for s in snaps:
            st = self.snapshot_state(s.get("snapshot_id"))
            sstate[st] = sstate.get(st, 0) + 1
        deps = ledger.read_dependencies()
        broken = sum(1 for d in deps if d.get("broken"))
        return ObservatorySummary(
            timestamp=now, snapshot_count=len(snaps),
            snapshot_state_distribution=dict(sorted(sstate.items())),
            metric_count=len(ledger.read_metrics()), dependency_count=len(deps),
            broken_dependency_count=broken, timeline_count=len(ledger.read_timelines()),
            trend_count=len(ledger.read_trends()), dashboard_count=len(ledger.read_dashboards()),
            report_count=len(ledger.read_reports()))
