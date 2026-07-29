"""Research Optimization Engine (P12.6) — 연구 생태계 최적화 기회 분석. **분석·제안 전용.**

전체 연구 생태계를 분석해 최적화 기회를 식별한다(병목 탐지·워크플로 최적화·자원 효율·처리량 분석). **자동으로
최적화하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. ANALYZE ≠
OPTIMIZE · PROPOSAL ≠ MODIFICATION · IDENTIFIED ≠ EXECUTION. 최적화 제안은 코드·설정·권한·전략을 변경할 수 없다.
결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_optimization_engine import ledger
from jarvis.research_optimization_engine.models import (
    GENESIS,
    O_ANALYZED,
    O_ARCHIVED,
    O_IDENTIFIED,
    O_OBSERVED,
    O_PROPOSED,
    O_REVIEWED,
    SEVERITIES,
    BottleneckRecord,
    ComparisonRecord,
    EfficiencyRecord,
    ForbiddenOptimizationError,
    IllegalStudyTransition,
    ImmutableBottleneckError,
    ImmutableComparisonError,
    ImmutableEfficiencyError,
    ImmutableProposalError,
    ImmutableStudyError,
    IncompleteProposalError,
    InvalidSeverity,
    OptimizationReportRecord,
    OptimizationSummary,
    ProposalRecord,
    StudyEventRecord,
    UnknownStudyError,
    bottleneck_id as _bottleneck_id,
    can_transition,
    comparison_id as _comparison_id,
    compare_direction,
    content_hash,
    efficiency_id as _efficiency_id,
    input_digest,
    is_forbidden_verb,
    proposal_id as _proposal_id,
    rank_bottlenecks,
    report_id as _report_id,
    severity_rank,
    study_event_id as _study_event_id,
    study_id as _study_id,
)

_DISCLAIMER = ("Research Optimization Engine 데이터 — ANALYZE ≠ OPTIMIZE · PROPOSAL ≠ MODIFICATION · IDENTIFIED "
               "≠ EXECUTION. 최적화 기회 분석·제안 기록 전용 — 자동 최적화·코드/설정/권한/전략 변경·배포·실행 "
               "없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOptimizationEngine:
    """연구 최적화 엔진. 불변·append-only·이벤트 소싱·결정적. 자동 최적화/수정/배포/실행 권한 없음."""

    # ══════════════ 연구 생애주기(event-sourced) ══════════════
    def _study_event(self, study: str, name: str, scope: str, frm: str, to: str, note: str,
                  now: str, *, commit: bool) -> StudyEventRecord:
        seq = len(ledger.study_events(study))
        eid = _study_event_id(study, to, seq)
        rec = StudyEventRecord(study_event_id=eid, study_id=study, name=name, scope=scope,
                               from_state=frm, to_state=to, note=note, occurred_at=now,
                               input_hash=input_digest(study, to, seq),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.study_event_exists(eid):
            head = ledger.studies_head()
            ledger.append_study_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return StudyEventRecord(**rec)

    def _meta(self, study: str) -> dict:
        evs = ledger.study_events(study)
        if not evs:
            raise UnknownStudyError(f"미등록 연구 {study}")
        g = evs[0]
        return {"study_id": study, "name": g.get("name"), "scope": g.get("scope"),
                "state": evs[-1].get("to_state")}

    def current_state(self, study: str) -> str | None:
        evs = ledger.study_events(study)
        return evs[-1].get("to_state") if evs else None

    def _require_study(self, study: str) -> str:
        st = self.current_state(study)
        if st is None:
            raise UnknownStudyError(f"미등록 연구 {study}")
        return st

    def _transition(self, study: str, to: str, note: str, now: str,
                  *, commit: bool) -> StudyEventRecord:
        frm = self._require_study(study)
        if not can_transition(frm, to):
            raise IllegalStudyTransition(f"{study} {frm}→{to} 불가")
        m = self._meta(study)
        return self._study_event(study, m["name"], m["scope"], frm, to, note, now, commit=commit)

    # ══════════════ create_optimization_study (Optimization Studies) ══════════════
    def create_optimization_study(self, name: str, scope: str = "ECOSYSTEM", now: str = "",
                               *, commit: bool = False) -> StudyEventRecord:
        """최적화 연구 생성(genesis OBSERVED). **연구 시작만.**"""
        sid = _study_id(name)
        evs = ledger.study_events(sid)
        if evs:
            g = evs[0]
            if g.get("scope") != scope:
                raise ImmutableStudyError(f"{sid} 연구 불변 — 변경 불가")
            return StudyEventRecord(**{k: v for k, v in g.items()
                                       if k in StudyEventRecord.__dataclass_fields__})
        return self._study_event(sid, name, scope, GENESIS, O_OBSERVED, "observed", now,
                                 commit=commit)

    # ══════════════ analyze_pipeline (OBSERVED→ANALYZED, Efficiency Analysis) ══════════════
    def analyze_pipeline(self, study: str, subject: str, metric_name: str, value: float,
                      throughput: float = 0.0, note: str = "", now: str = "",
                      *, commit: bool = False) -> EfficiencyRecord:
        """파이프라인/자원 효율 분석(불변) + OBSERVED→ANALYZED. **분석·기록만.**"""
        st = self._require_study(study)
        if st == O_OBSERVED:
            self._transition(study, O_ANALYZED, "analyzed", now, commit=commit)
        eid = _efficiency_id(study, subject, metric_name)
        existing = ledger.get_efficiency(eid)
        if existing is not None:
            if abs(float(existing.get("value", 0.0)) - float(value)) > 1e-9:
                raise ImmutableEfficiencyError(f"{eid} 효율 분석 불변 — 변경 불가")
            return EfficiencyRecord(**{k: v for k, v in existing.items()
                                       if k in EfficiencyRecord.__dataclass_fields__})
        rec = EfficiencyRecord(efficiency_id=eid, study_id=study, subject=subject,
                               metric_name=metric_name, value=round(float(value), 8),
                               throughput=round(float(throughput), 8), note=note, recorded_at=now,
                               input_hash=input_digest(study, subject, metric_name),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.efficiency_exists(eid):
            head = ledger.efficiency_head()
            ledger.append_efficiency(_seal(rec, head["record_hash"] if head else GENESIS))
        return EfficiencyRecord(**rec)

    # ══════════════ detect_bottleneck (ANALYZED→IDENTIFIED, Bottleneck Reports) ══════════════
    def detect_bottleneck(self, study: str, target: str, severity: str, load: float = 0.0,
                       description: str = "", evidence_ref: str = "", now: str = "",
                       *, commit: bool = False) -> BottleneckRecord:
        """병목 탐지·기록(불변) + ANALYZED→IDENTIFIED. **탐지·기록만.**"""
        st = self._require_study(study)
        if severity not in SEVERITIES:
            raise InvalidSeverity(f"미등록 심각도 {severity}")
        if st == O_ANALYZED:
            self._transition(study, O_IDENTIFIED, "identified", now, commit=commit)
        elif st != O_IDENTIFIED:
            raise IllegalStudyTransition(f"{study} 분석 전({st}) — 병목 탐지 불가")
        bid = _bottleneck_id(study, target)
        existing = ledger.get_bottleneck(bid)
        if existing is not None:
            if existing.get("severity") != severity:
                raise ImmutableBottleneckError(f"{bid} 병목 불변 — 변경 불가")
            return BottleneckRecord(**{k: v for k, v in existing.items()
                                       if k in BottleneckRecord.__dataclass_fields__})
        rec = BottleneckRecord(bottleneck_id=bid, study_id=study, target=target, severity=severity,
                               load=round(float(load), 8), description=description,
                               evidence_ref=evidence_ref, detected_at=now,
                               input_hash=input_digest(study, target),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.bottleneck_exists(bid):
            head = ledger.bottlenecks_head()
            ledger.append_bottleneck(_seal(rec, head["record_hash"] if head else GENESIS))
        return BottleneckRecord(**rec)

    def ranked_bottlenecks(self, study: str) -> list:
        """병목 심각도·부하 기준 결정적 랭킹."""
        items = [(b.get("target"), severity_rank(b.get("severity")), float(b.get("load", 0.0)))
                 for b in ledger.study_bottlenecks(study)]
        return rank_bottlenecks(items)

    # ══════════════ compare_efficiency (Historical Comparisons) ══════════════
    def compare_efficiency(self, study: str, subject_a: str, subject_b: str, metric_name: str,
                        value_a: float, value_b: float, higher_is_better: bool = True, now: str = "",
                        *, commit: bool = False) -> ComparisonRecord:
        """역사 비교(불변, 결정적). **분석·기록만.**"""
        self._require_study(study)
        direction, delta = compare_direction(value_a, value_b, higher_is_better)
        cid = _comparison_id(study, subject_a, subject_b, metric_name)
        existing = ledger.get_comparison(cid)
        if existing is not None:
            return ComparisonRecord(**{k: v for k, v in existing.items()
                                       if k in ComparisonRecord.__dataclass_fields__})
        rec = ComparisonRecord(comparison_id=cid, study_id=study, subject_a=subject_a,
                               subject_b=subject_b, metric_name=metric_name,
                               value_a=round(float(value_a), 8), value_b=round(float(value_b), 8),
                               delta=delta, direction=direction, compared_at=now,
                               input_hash=input_digest(study, subject_a, subject_b, metric_name),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.comparison_exists(cid):
            head = ledger.comparisons_head()
            ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
        return ComparisonRecord(**rec)

    # ══════════════ record_proposal (IDENTIFIED→PROPOSED, Optimization Proposals) ══════════════
    def record_proposal(self, study: str, title: str, problem: str, evidence: str,
                     expected_impact: str, risk: str, reviewer: str, proposed_change: str = "",
                     now: str = "", *, commit: bool = False) -> ProposalRecord:
        """최적화 제안 기록(불변). 필수 필드·리뷰어 검증·금지 변경 차단 + IDENTIFIED→PROPOSED. **제안·기록만.**"""
        st = self._require_study(study)
        if not (problem and evidence and expected_impact and risk and reviewer):
            raise IncompleteProposalError(
                f"{study} 제안 필수 필드 누락(problem/evidence/impact/risk/reviewer)")
        if is_forbidden_verb(proposed_change):
            raise ForbiddenOptimizationError(f"금지 변경 시도 {proposed_change} — 거부")
        pid = _proposal_id(study, title)
        existing = ledger.get_proposal(pid)
        if existing is not None:
            if existing.get("problem") != problem:
                raise ImmutableProposalError(f"{pid} 제안 불변 — 변경 불가")
            return ProposalRecord(**{k: v for k, v in existing.items()
                                     if k in ProposalRecord.__dataclass_fields__})
        if st == O_IDENTIFIED:
            self._transition(study, O_PROPOSED, "proposed", now, commit=commit)
        elif st != O_PROPOSED:
            raise IllegalStudyTransition(f"{study} IDENTIFIED 아님({st}) — 제안 불가")
        rec = ProposalRecord(proposal_id=pid, study_id=study, title=title, problem=problem,
                             evidence=evidence, expected_impact=expected_impact, risk=risk,
                             reviewer=reviewer, proposed_change=proposed_change, created_at=now,
                             input_hash=input_digest(study, title),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.proposal_exists(pid):
            head = ledger.proposals_head()
            ledger.append_proposal(_seal(rec, head["record_hash"] if head else GENESIS))
        return ProposalRecord(**rec)

    def review_study(self, study: str, now: str = "", *, commit: bool = False) -> StudyEventRecord:
        """제안 리뷰(PROPOSED→REVIEWED). **상태 기록만.**"""
        return self._transition(study, O_REVIEWED, "reviewed", now, commit=commit)

    def archive_study(self, study: str, now: str = "", *, commit: bool = False) -> StudyEventRecord:
        return self._transition(study, O_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ generate_report ══════════════
    def generate_report(self, study: str, scope: str = "STUDY", now: str = "",
                     *, commit: bool = False) -> OptimizationReportRecord:
        """최적화 리포트(병목·효율·제안·비교·심각도 분포). **is_binding=False, 분석만.**"""
        self._require_study(study)
        bns = ledger.study_bottlenecks(study)
        sev_dist: dict = {}
        for b in bns:
            sev_dist[b.get("severity")] = sev_dist.get(b.get("severity"), 0) + 1
        rid = _report_id(study, scope, now)
        rec = OptimizationReportRecord(
            report_id=rid, study_id=study, scope=scope, bottleneck_count=len(bns),
            efficiency_count=len(ledger.study_efficiency(study)),
            proposal_count=len(ledger.study_proposals(study)),
            comparison_count=len(ledger.study_comparisons(study)),
            severity_distribution=dict(sorted(sev_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(study, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return OptimizationReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_optimization_engine.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_studies(self) -> list:
        return ledger.study_ids()

    def studies_in_state(self, state: str) -> list:
        return sorted(s for s in ledger.study_ids() if self.current_state(s) == state)

    def study_meta(self, study: str) -> dict:
        return self._meta(study)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> OptimizationSummary:
        return OptimizationSummary(
            timestamp=now, study_event_count=len(ledger.read_study_events()),
            bottleneck_count=len(ledger.read_bottlenecks()),
            efficiency_count=len(ledger.read_efficiency()),
            proposal_count=len(ledger.read_proposals()),
            comparison_count=len(ledger.read_comparisons()),
            report_count=len(ledger.read_reports()))
