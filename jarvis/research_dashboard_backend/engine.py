"""Research Dashboard Backend Engine (P34) — 백엔드 집계. **UI 없음, 결정 권한 없음, 동작 없음.**

통계·타임라인·헬스·지식 요약·연구 진행·모니터링 집계를 제공한다. **UI 없음. 백엔드 전용. 결정 권한 없음.** execution/
broker/live_trading/portfolio_execution import·호출 없음. BACKEND ONLY · AGGREGATION ≠ DECISION · DASHBOARD ≠
AUTHORITY. 결정적·불변·append-only. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_dashboard_backend import ledger
from jarvis.research_dashboard_backend import models as M
from jarvis.research_dashboard_backend.models import (
    GENESIS,
    ArtifactRecord,
    DashboardReportRecord,
    DashboardSummary,
    PanelRecord,
    SnapshotRecord,
    UnknownEntityError,
    WidgetRecord,
    content_hash,
    input_digest,
    ratio,
    value_hash,
)

_DISCLAIMER = ("Research Dashboard Backend 데이터 — BACKEND ONLY · AGGREGATION ≠ DECISION · DASHBOARD ≠ "
               "AUTHORITY. 통계·타임라인·헬스·지식 요약·연구 진행·모니터링 집계 전용 — UI·결정·실행·거래·배포·승인·배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchDashboardBackendEngine:
    """연구 대시보드 백엔드 엔진. 불변·append-only·결정적. 결정/실행/거래/배포 권한 없음 — 집계만."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ register_panel ══════════════
    def register_panel(self, panel_type, name, description="", now="",
                       *, commit=False) -> PanelRecord:
        """대시보드 패널 등록(불변, is_readonly=True). **집계 정의만.**"""
        if panel_type not in M.PANEL_TYPES:
            raise ValueError(f"미지원 panel_type {panel_type}")
        pid = M.panel_id(panel_type, name)
        existing = next((p for p in ledger.read_panels() if p.get("panel_id") == pid), None)
        if existing:
            return PanelRecord(**{k: v for k, v in existing.items()
                                  if k in PanelRecord.__dataclass_fields__})
        rec = PanelRecord(panel_id=pid, panel_type=panel_type, name=name, description=description,
                          is_readonly=True, created_at=now, input_hash=input_digest(panel_type, name),
                          previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.panel_exists, ledger.panels_head, ledger.append_panel, pid, rec,
                         commit=commit)
        self._artifact(M.ART_PANEL, pid, "", now, commit=commit)
        return PanelRecord(**rec)

    # ══════════════ 집계(READ ONLY, 결정적) ══════════════
    def aggregate_statistics(self) -> dict:
        """전체 통계 집계(결정적, READ ONLY). **집계만 — 결정 없음.**"""
        counts = ledger.all_source_counts()
        return {"panel": "STATISTICS", "source_counts": counts, "total": sum(counts.values()),
                "layer_count": len(counts)}

    def build_timeline(self) -> dict:
        """타임라인 집계(계층별 이벤트 수, 결정적)."""
        counts = ledger.all_source_counts()
        return {"panel": "TIMELINE", "by_layer": counts,
                "active_layers": sorted(k for k, v in counts.items() if v > 0)}

    def aggregate_health(self) -> dict:
        """헬스 집계(모니터링 헬스/이상·신뢰성 장애, 결정적)."""
        health = ledger.source_count("monitoring_health")
        anomalies = ledger.source_count("monitoring_anomalies")
        incidents = ledger.source_count("reliability")
        return {"panel": "HEALTH", "health_checks": health, "anomalies": anomalies,
                "incidents": incidents,
                "status": "DEGRADED" if (anomalies + incidents) > 0 else "NOMINAL"}

    def knowledge_summary(self) -> dict:
        """지식 요약(KG·메모리·통찰, 결정적)."""
        return {"panel": "KNOWLEDGE_SUMMARY",
                "knowledge_graph": ledger.source_count("knowledge_graph"),
                "memories": ledger.source_count("memory_intelligence"),
                "insights": ledger.source_count("insight_intelligence")}

    def research_progress(self) -> dict:
        """연구 진행(사이클·후보·계획, 결정적)."""
        cycles = ledger.source_count("autonomous_research")
        candidates = ledger.source_count("strategy_generation")
        plans = ledger.source_count("orchestration")
        return {"panel": "RESEARCH_PROGRESS", "cycles": cycles, "candidates": candidates,
                "plans": plans, "total_activity": cycles + candidates + plans}

    def monitoring_summary(self) -> dict:
        """모니터링 요약(헬스·이상·자원, 결정적)."""
        return {"panel": "MONITORING", "health": ledger.source_count("monitoring_health"),
                "anomalies": ledger.source_count("monitoring_anomalies"),
                "resources": ledger.source_count("resource_manager")}

    def _panel_data(self, panel_type) -> dict:
        disp = {"STATISTICS": self.aggregate_statistics, "TIMELINE": self.build_timeline,
                "HEALTH": self.aggregate_health, "KNOWLEDGE_SUMMARY": self.knowledge_summary,
                "RESEARCH_PROGRESS": self.research_progress, "MONITORING": self.monitoring_summary}
        fn = disp.get(panel_type)
        if not fn:
            raise ValueError(f"미지원 panel_type {panel_type}")
        return fn()

    # ══════════════ create_snapshot (결정적 집계, 결정 아님) ══════════════
    def create_snapshot(self, panel_type, now="", *, commit=False) -> SnapshotRecord:
        """패널 집계 스냅샷(결정적, is_decision=False). **집계만 — 결정 권한 없음.**"""
        if panel_type not in M.PANEL_TYPES:
            raise ValueError(f"미지원 panel_type {panel_type}")
        data = self._panel_data(panel_type)
        sid = M.snapshot_id(panel_type, now)
        rec = SnapshotRecord(snapshot_id=sid, panel_type=panel_type, data=data,
                             data_hash=value_hash(data), is_decision=False, created_at=now,
                             input_hash=input_digest(panel_type, now),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.snapshot_exists, ledger.snapshots_head, ledger.append_snapshot, sid,
                         rec, commit=commit)
        self._artifact(M.ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ record_widget ══════════════
    def record_widget(self, panel_type, metric_name, value, unit="count", now="",
                      *, commit=False) -> WidgetRecord:
        """위젯/지표 기록(불변). **집계 표시만.**"""
        if panel_type not in M.PANEL_TYPES:
            raise ValueError(f"미지원 panel_type {panel_type}")
        seq = len([w for w in ledger.widgets_by_panel(panel_type)
                   if w.get("metric_name") == metric_name])
        wid = M.widget_id(panel_type, metric_name, seq)
        rec = WidgetRecord(widget_id=wid, panel_type=panel_type, metric_name=metric_name,
                           value=float(value), unit=unit, created_at=now,
                           input_hash=input_digest(panel_type, metric_name, seq),
                           previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.widget_exists, ledger.widgets_head, ledger.append_widget, wid, rec,
                         commit=commit)
        return WidgetRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> DashboardReportRecord:
        """대시보드 리포트(패널·스냅샷·위젯 집계 + 전체 통계). **is_binding=False, AGGREGATION ≠ DECISION.**"""
        panels = ledger.read_panels()
        pt_dist: dict = {}
        for p in panels:
            pt_dist[p.get("panel_type")] = pt_dist.get(p.get("panel_type"), 0) + 1
        rid = M.report_id(scope, now)
        rec = DashboardReportRecord(
            report_id=rid, scope=scope, panel_count=len(panels),
            snapshot_count=len(ledger.read_snapshots()), widget_count=len(ledger.read_widgets()),
            panel_type_distribution=dict(sorted(pt_dist.items())),
            aggregate_statistics=self.aggregate_statistics(), is_binding=False, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return DashboardReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_dashboard_backend.verify import verify_chain
        return verify_chain()

    def list_panels(self) -> list:
        return sorted(p.get("panel_id") for p in ledger.read_panels())

    def summary(self, now="") -> DashboardSummary:
        return DashboardSummary(
            timestamp=now, panel_count=len(ledger.read_panels()),
            snapshot_count=len(ledger.read_snapshots()), widget_count=len(ledger.read_widgets()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
