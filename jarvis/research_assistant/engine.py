"""Personal Research Assistant Engine (P44) — 개인 연구 어시스턴트. **분석만, 결정·승인·집행 없음.**

기존 원장을 READ ONLY 로 읽어 일일 요약·실험 요약·실패 분석·지식 리캡·진행 요약·잠재 연구 영역을 만든다.
**투자 결정·전략 승인·행동 실행을 하지 않는다.** ASSISTANT ANALYZES · DOES NOT DECIDE / APPROVE / EXECUTE.
execution/broker/live_trading import·호출 없음. 엔진은 execute()/trade()/deploy()/allocate()/approve()/decide() 를
노출하지 않는다. 결정적. 리더 주입 가능(테스트·통합). 산출 스냅샷은 자체 ras_ 원장에만 append.
"""
from __future__ import annotations

from jarvis.research_assistant import ledger
from jarvis.research_assistant import models as M
from jarvis.research_assistant.models import (
    GENESIS,
    AdvisoryNoteRecord,
    AssistantReportRecord,
    AssistantSummary,
    DailySummary,
    ExperimentSummary,
    FailureAnalysis,
    KnowledgeRecap,
    PotentialAreas,
    ProgressSummary,
    content_hash,
    input_digest,
)

# 실패 클러스터가 잠재 영역 제안으로 승격되는 최소 근거 수
_AREA_MIN_EVIDENCE = 2
_RECENT = 5


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchAssistantEngine:
    """개인 연구 어시스턴트. 기존 원장 READ ONLY 분석·요약. 결정/승인/집행 권한 없음.

    reader(source_name)->list[dict] 주입 가능(테스트 격리·통합). 기본은 ras_ 리더로 실제 원장 파일 읽기.
    """

    def __init__(self, reader=None) -> None:
        self._reader = reader or ledger.read_source

    def _read(self, name) -> list:
        try:
            return list(self._reader(name) or [])
        except Exception:  # noqa: BLE001
            return []

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 일일 요약 ══════════════
    def daily_summary(self) -> DailySummary:
        counts = {name: len(self._read(name)) for name in sorted(M.SOURCES)}
        total = sum(counts.values())
        active = sum(1 for v in counts.values() if v > 0)
        headline = (f"총 {total}개 기록 · 활성 소스 {active}/{len(counts)}"
                    if total else "아직 기록이 없습니다(신규 로컬 환경).")
        return DailySummary(total_records=total, active_sources=active, source_counts=counts,
                            headline=headline)

    # ══════════════ 최근 실험 요약 ══════════════
    def experiment_summary(self, limit: int = 20) -> ExperimentSummary:
        runs = self._read("experiment_runs")
        results = self._read("experiment_results")
        by_metric: dict = {}
        for r in results:
            metric = M.first_field(r, ("metric", "name", "kind")) or "unknown"
            by_metric.setdefault(metric, []).append(M.first_field(r, ("value", "score")))
        metric_stats = {m: M.numeric_stats(vals) for m, vals in sorted(by_metric.items())}
        headline = (f"실험 실행 {len(runs)}건 · 결과 {len(results)}건 · 지표 {len(metric_stats)}종"
                    if runs or results else "최근 실험 기록이 없습니다.")
        return ExperimentSummary(run_count=len(runs), result_count=len(results),
                                 metric_stats=metric_stats, headline=headline)

    # ══════════════ 실패 분석 ══════════════
    def failure_analysis(self) -> FailureAnalysis:
        failures = list(self._read("failures"))
        for inc in self._read("incidents"):
            failures.append(inc)
        # 실험 결과 중 실패 신호가 있는 것도 포함
        for r in self._read("experiment_results"):
            status = M.first_field(r, ("status", "outcome", "passed"))
            if status and (M.is_failure_signal(status) or str(status).lower() == "false"):
                failures.append(r)
        clusters: dict = {}
        for f in failures:
            reason = (M.first_field(f, ("reason", "category", "pattern", "type", "metric"))
                      or "unknown")
            clusters[reason] = clusters.get(reason, 0) + 1
        clusters = dict(sorted(clusters.items(), key=lambda kv: (-kv[1], kv[0])))
        findings = [f"'{reason}' 관련 {n}건" for reason, n in clusters.items()]
        suggested = [f"'{reason}' 원인 검토 권장(근거 {n}건)"
                     for reason, n in clusters.items() if n >= _AREA_MIN_EVIDENCE]
        return FailureAnalysis(failure_count=len(failures), clusters=clusters, findings=findings,
                               suggested_reviews=suggested)

    # ══════════════ 지식 리캡 ══════════════
    def knowledge_recap(self) -> KnowledgeRecap:
        memories = self._read("memories")
        lessons = self._read("lessons")
        patterns = self._read("patterns")
        topics = []
        for rec in (memories + lessons + patterns):
            t = M.first_field(rec, ("topic", "title", "summary", "name", "key"))
            if t:
                topics.append(t)
        recent_topics = sorted(set(topics))[:_RECENT]
        headline = (f"지식 {len(memories)} · 교훈 {len(lessons)} · 패턴 {len(patterns)}"
                    if (memories or lessons or patterns) else "축적된 지식 기록이 없습니다.")
        return KnowledgeRecap(memory_count=len(memories), lesson_count=len(lessons),
                              pattern_count=len(patterns), recent_topics=recent_topics,
                              headline=headline)

    # ══════════════ 연구 진행 요약 ══════════════
    def progress_summary(self) -> ProgressSummary:
        stage_counts = {
            "experiments": len(self._read("experiments")),
            "experiment_runs": len(self._read("experiment_runs")),
            "knowledge": len(self._read("memories")) + len(self._read("lessons")),
            "models": len(self._read("models")),
            "validations": len(self._read("validations")),
            "successes": len(self._read("successes")),
            "failures": len(self._read("failures")),
        }
        notes = []
        if stage_counts["experiment_runs"]:
            notes.append(f"실험 파이프라인 활동 {stage_counts['experiment_runs']}건")
        if stage_counts["knowledge"]:
            notes.append(f"지식 자산 {stage_counts['knowledge']}건 축적")
        if stage_counts["validations"]:
            notes.append(f"모델 검증 {stage_counts['validations']}건")
        if not notes:
            notes.append("초기 단계 — 아직 축적된 연구 활동이 적습니다.")
        return ProgressSummary(stage_counts=dict(sorted(stage_counts.items())), progress_notes=notes)

    # ══════════════ 잠재 연구 영역 ══════════════
    def potential_areas(self) -> PotentialAreas:
        """실패 클러스터·지표 변동성에서 결정적으로 '가능한 다음 검토'를 제안. **결정 아님 — 사람 검토용.**"""
        areas = []
        fa = self.failure_analysis()
        for reason, n in fa.clusters.items():
            if n >= _AREA_MIN_EVIDENCE and reason != "unknown":
                areas.append({"area": f"Investigate {reason}",
                              "rationale": f"실패/이슈 {n}건이 '{reason}' 에 집중",
                              "evidence": n})
        # 지표 변동성(범위 큼) → 안정성 검토 제안
        es = self.experiment_summary()
        for metric, st in es.metric_stats.items():
            if st["count"] >= _AREA_MIN_EVIDENCE and (st["max"] - st["min"]) > 0:
                spread = round(st["max"] - st["min"], 6)
                areas.append({"area": f"Review stability of {metric}",
                              "rationale": f"'{metric}' 범위 {spread}(min {st['min']}~max {st['max']})",
                              "evidence": st["count"]})
        areas.sort(key=lambda a: (-a["evidence"], a["area"]))
        return PotentialAreas(areas=areas)

    # ══════════════ 번들 리포트 + 기록 ══════════════
    def build_bundle(self) -> dict:
        return {
            "daily": self.daily_summary().to_dict(),
            "experiments": self.experiment_summary().to_dict(),
            "failures": self.failure_analysis().to_dict(),
            "knowledge": self.knowledge_recap().to_dict(),
            "progress": self.progress_summary().to_dict(),
            "potential_areas": self.potential_areas().to_dict(),
        }

    def generate_report(self, scope="DAILY", now="", *, commit=False) -> AssistantReportRecord:
        """모든 요약을 묶은 리포트 스냅샷(결정적 digest). **is_advisory=True·is_decision=False.**"""
        bundle = self.build_bundle()
        daily = self.daily_summary()
        rid = M.report_id(scope, now)
        rec = AssistantReportRecord(
            report_id=rid, scope=scope, total_records=daily.total_records,
            experiment_run_count=bundle["experiments"]["run_count"],
            failure_count=bundle["failures"]["failure_count"],
            knowledge_count=(bundle["knowledge"]["memory_count"]
                             + bundle["knowledge"]["lesson_count"]
                             + bundle["knowledge"]["pattern_count"]),
            potential_area_count=len(bundle["potential_areas"]["areas"]),
            bundle_digest=M.content_digest(bundle), is_advisory=True, is_decision=False,
            requires_human_review=True, disclaimer=M.DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        return AssistantReportRecord(**rec)

    def record_advisory(self, area, rationale="", evidence_count=0, now="",
                        *, commit=False) -> AdvisoryNoteRecord:
        """자문 노트 기록(비구속). **is_binding=False — 결정/승인 아님.**"""
        seq = len(ledger.read_notes())
        nid = M.note_id(area, seq)
        rec = AdvisoryNoteRecord(
            note_id=nid, area=area, rationale=rationale, evidence_count=int(evidence_count),
            is_binding=False, requires_human_review=True, created_at=now,
            input_hash=input_digest(area, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.note_exists, ledger.notes_head, ledger.append_note, nid, rec,
                         commit=commit)
        return AdvisoryNoteRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_assistant.verify import verify_chain
        return verify_chain()

    def summary(self, now="") -> AssistantSummary:
        return AssistantSummary(timestamp=now, report_count=len(ledger.read_reports()),
                                note_count=len(ledger.read_notes()))
