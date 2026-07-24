"""Autonomous Research Evaluation Engine (P12.5) — 자율 연구 평가. **평가·기록 전용.**

연구 품질·재현성·증거 강도·효율·강건성·지식 기여를 측정한다. **점수는 승인이 아니고 배포 권한이 아니다.**
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. SCORE ≠ APPROVAL · SCORE ≠ DEPLOYMENT
PERMISSION · EVALUATION ≠ SELECTION. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.autonomous_research_evaluation import ledger
from jarvis.autonomous_research_evaluation.models import (
    ART_EVALUATION,
    ART_REPORT,
    E_ARCHIVED,
    E_CREATED,
    E_EVALUATING,
    E_REVIEWED,
    E_SCORED,
    EVAL_DIMENSIONS,
    GENESIS,
    ArtifactRecord,
    BenchmarkRecord,
    CriterionRecord,
    EvaluationEventRecord,
    EvaluationSummary,
    IllegalEvalTransition,
    ImmutableBenchmarkError,
    ImmutableCriterionError,
    ImmutableScoreError,
    InvalidDimension,
    QualityReportRecord,
    ScoreRecord,
    UnknownEvaluationError,
    artifact_id as _artifact_id,
    benchmark_id as _benchmark_id,
    can_transition,
    compare_direction,
    content_hash,
    criterion_id as _criterion_id,
    evaluation_event_id as _evaluation_event_id,
    evaluation_id as _evaluation_id,
    input_digest,
    report_id as _report_id,
    score_id as _score_id,
    weighted_score,
)

_DISCLAIMER = ("Autonomous Research Evaluation 데이터 — SCORE ≠ APPROVAL · SCORE ≠ DEPLOYMENT PERMISSION · "
               "EVALUATION ≠ SELECTION. 연구 평가·점수 기록 전용 — 승인·배포·전략 선택·자본 배분 없음. 점수는 "
               "분석 지표일 뿐이다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AutonomousResearchEvaluationEngine:
    """자율 연구 평가 엔진. 불변·append-only·이벤트 소싱·결정적. 승인/배포/선택 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.lineage_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ define_metric (Evaluation Criteria) ══════════════
    def define_metric(self, name: str, dimension: str, weight: float = 1.0, description: str = "",
                   now: str = "", *, commit: bool = False) -> CriterionRecord:
        """평가 기준 정의(불변). 차원은 6개 중 하나. **정의만.**"""
        if dimension not in EVAL_DIMENSIONS:
            raise InvalidDimension(f"미등록 차원 {dimension}")
        cid = _criterion_id(name)
        existing = ledger.get_criterion(cid)
        if existing is not None:
            if abs(float(existing.get("weight", 1.0)) - float(weight)) > 1e-9:
                raise ImmutableCriterionError(f"{cid} 기준 불변 — 변경 불가")
            return CriterionRecord(**{k: v for k, v in existing.items()
                                      if k in CriterionRecord.__dataclass_fields__})
        rec = CriterionRecord(criterion_id=cid, name=name, dimension=dimension,
                              weight=round(float(weight), 8), description=description, created_at=now,
                              input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.criterion_exists(cid):
            head = ledger.criteria_head()
            ledger.append_criterion(_seal(rec, head["record_hash"] if head else GENESIS))
        return CriterionRecord(**rec)

    # ══════════════ 평가 생애주기(event-sourced) ══════════════
    def _eval_event(self, evaluation: str, research_layer: str, research_ref: str,
                 overall_score: float, frm: str, to: str, note: str, now: str,
                 *, commit: bool) -> EvaluationEventRecord:
        seq = len(ledger.evaluation_events(evaluation))
        eid = _evaluation_event_id(evaluation, to, seq)
        rec = EvaluationEventRecord(
            evaluation_event_id=eid, evaluation_id=evaluation, research_layer=research_layer,
            research_ref=research_ref, overall_score=round(float(overall_score), 6), from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(evaluation, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evaluation_event_exists(eid):
            head = ledger.registry_head()
            ledger.append_evaluation_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return EvaluationEventRecord(**rec)

    def _meta(self, evaluation: str) -> dict:
        evs = ledger.evaluation_events(evaluation)
        if not evs:
            raise UnknownEvaluationError(f"미등록 평가 {evaluation}")
        g = evs[0]
        last = evs[-1]
        return {"evaluation_id": evaluation, "research_layer": g.get("research_layer"),
                "research_ref": g.get("research_ref"), "overall_score": last.get("overall_score"),
                "state": last.get("to_state")}

    def current_state(self, evaluation: str) -> str | None:
        evs = ledger.evaluation_events(evaluation)
        return evs[-1].get("to_state") if evs else None

    def overall_score(self, evaluation: str) -> float:
        evs = ledger.evaluation_events(evaluation)
        return float(evs[-1].get("overall_score", 0.0)) if evs else 0.0

    def _require_evaluation(self, evaluation: str) -> str:
        st = self.current_state(evaluation)
        if st is None:
            raise UnknownEvaluationError(f"미등록 평가 {evaluation}")
        return st

    def _transition(self, evaluation: str, to: str, overall: float, note: str, now: str,
                  *, commit: bool) -> EvaluationEventRecord:
        frm = self._require_evaluation(evaluation)
        if not can_transition(frm, to):
            raise IllegalEvalTransition(f"{evaluation} {frm}→{to} 불가")
        m = self._meta(evaluation)
        return self._eval_event(evaluation, m["research_layer"], m["research_ref"], overall, frm, to,
                                note, now, commit=commit)

    # ══════════════ evaluate_cycle (CREATED→EVALUATING) ══════════════
    def evaluate_cycle(self, research_layer: str, research_ref: str, now: str = "",
                    *, commit: bool = False) -> EvaluationEventRecord:
        """연구 사이클 평가 시작(genesis CREATED→EVALUATING). **평가 시작만.**"""
        ev = _evaluation_id(research_layer, research_ref)
        evs = ledger.evaluation_events(ev)
        if evs:
            return EvaluationEventRecord(**{k: v for k, v in evs[0].items()
                                            if k in EvaluationEventRecord.__dataclass_fields__})
        self._eval_event(ev, research_layer, research_ref, 0.0, GENESIS, E_CREATED, "created", now,
                         commit=commit)
        self._artifact(ART_EVALUATION, ev, "", now, commit=commit)
        return self._eval_event(ev, research_layer, research_ref, 0.0, E_CREATED, E_EVALUATING,
                                "evaluating", now, commit=commit)

    # ══════════════ score_quality (Research Scores) ══════════════
    def score_quality(self, evaluation: str, dimension: str, score: float, evidence_ref: str = "",
                   rationale: str = "", now: str = "", *, commit: bool = False) -> ScoreRecord:
        """차원 점수 기록(불변). **점수 기록만 — 승인 아님.**"""
        st = self._require_evaluation(evaluation)
        if dimension not in EVAL_DIMENSIONS:
            raise InvalidDimension(f"미등록 차원 {dimension}")
        if st not in (E_EVALUATING,):
            raise IllegalEvalTransition(f"{evaluation} EVALUATING 아님({st}) — 점수 기록 불가")
        sid = _score_id(evaluation, dimension)
        existing = ledger.get_score(sid)
        if existing is not None:
            if abs(float(existing.get("score", 0.0)) - float(score)) > 1e-9:
                raise ImmutableScoreError(f"{sid} 점수 불변 — 변경 불가")
            return ScoreRecord(**{k: v for k, v in existing.items()
                                  if k in ScoreRecord.__dataclass_fields__})
        rec = ScoreRecord(score_id=sid, evaluation_id=evaluation, dimension=dimension,
                          score=round(float(score), 6), evidence_ref=evidence_ref,
                          rationale=rationale, created_at=now,
                          input_hash=input_digest(evaluation, dimension),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.score_exists(sid):
            head = ledger.scores_head()
            ledger.append_score(_seal(rec, head["record_hash"] if head else GENESIS))
        return ScoreRecord(**rec)

    def finalize_scoring(self, evaluation: str, now: str = "",
                      *, commit: bool = False) -> EvaluationEventRecord:
        """점수 확정(EVALUATING→SCORED). 가중 종합 점수 계산(결정적). **점수 확정만 — 승인 아님.**"""
        scores = {s.get("dimension"): float(s.get("score", 0.0))
                  for s in ledger.evaluation_scores(evaluation)}
        overall = weighted_score(scores, ledger.dimension_weights())
        return self._transition(evaluation, E_SCORED, overall, "scored", now, commit=commit)

    def review_evaluation(self, evaluation: str, reviewer: str = "", now: str = "",
                       *, commit: bool = False) -> EvaluationEventRecord:
        """평가 리뷰 기록(SCORED→REVIEWED). **리뷰 기록만 — SCORE ≠ APPROVAL.**"""
        m = self._meta(evaluation)
        return self._transition(evaluation, E_REVIEWED, m["overall_score"],
                                f"reviewed:{reviewer}(SCORE≠APPROVAL)", now, commit=commit)

    def archive_evaluation(self, evaluation: str, now: str = "",
                        *, commit: bool = False) -> EvaluationEventRecord:
        m = self._meta(evaluation)
        return self._transition(evaluation, E_ARCHIVED, m["overall_score"], "archived", now,
                                commit=commit)

    def dimension_scores(self, evaluation: str) -> dict:
        return {s.get("dimension"): float(s.get("score", 0.0))
                for s in ledger.evaluation_scores(evaluation)}

    # ══════════════ compare_research (Benchmark Records) ══════════════
    def compare_research(self, eval_a: str, eval_b: str, metric: str = "overall", now: str = "",
                      *, commit: bool = False) -> BenchmarkRecord:
        """두 평가 비교(벤치마크, 결정적). **분석·기록만 — SCORE ≠ SELECTION.**"""
        self._require_evaluation(eval_a)
        self._require_evaluation(eval_b)
        if metric == "overall":
            va, vb = self.overall_score(eval_a), self.overall_score(eval_b)
        else:
            va = self.dimension_scores(eval_a).get(metric, 0.0)
            vb = self.dimension_scores(eval_b).get(metric, 0.0)
        winner, delta = compare_direction(va, vb)
        bid = _benchmark_id(eval_a, eval_b, metric)
        existing = ledger.get_benchmark(bid)
        if existing is not None:
            return BenchmarkRecord(**{k: v for k, v in existing.items()
                                      if k in BenchmarkRecord.__dataclass_fields__})
        rec = BenchmarkRecord(benchmark_id=bid, eval_a=eval_a, eval_b=eval_b, metric=metric,
                              value_a=round(float(va), 6), value_b=round(float(vb), 6),
                              winner=winner, delta=delta, compared_at=now,
                              input_hash=input_digest(eval_a, eval_b, metric),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.benchmark_exists(bid):
            head = ledger.benchmarks_head()
            ledger.append_benchmark(_seal(rec, head["record_hash"] if head else GENESIS))
        return BenchmarkRecord(**rec)

    # ══════════════ generate_quality_report ══════════════
    def generate_quality_report(self, scope_id: str = "ALL", scope: str = "ALL", now: str = "",
                             *, commit: bool = False) -> QualityReportRecord:
        """품질 리포트(평가·점수·차원 평균). **is_approval=False, is_binding=False, 관찰만.**"""
        evals = ledger.evaluation_ids()
        if scope == "EVALUATION":
            evals = [e for e in evals if e == scope_id]
        scored = sum(1 for e in evals if self.current_state(e) in (E_SCORED, E_REVIEWED, E_ARCHIVED))
        reviewed = sum(1 for e in evals if self.current_state(e) in (E_REVIEWED, E_ARCHIVED))
        dim_acc: dict = {}
        dim_cnt: dict = {}
        for e in evals:
            for dim, sc in self.dimension_scores(e).items():
                dim_acc[dim] = dim_acc.get(dim, 0.0) + sc
                dim_cnt[dim] = dim_cnt.get(dim, 0) + 1
        dim_avg = {d: round(dim_acc[d] / dim_cnt[d], 6) for d in sorted(dim_acc)}
        rid = _report_id(scope, scope_id, now)
        rec = QualityReportRecord(
            report_id=rid, scope=scope, scope_id=scope_id, evaluation_count=len(evals),
            scored_count=scored, reviewed_count=reviewed, dimension_averages=dim_avg,
            is_approval=False, is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, scope_id, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_REPORT, rid, "", now, commit=commit)
        return QualityReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.autonomous_research_evaluation.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_evaluations(self) -> list:
        return ledger.evaluation_ids()

    def evaluations_in_state(self, state: str) -> list:
        return sorted(e for e in ledger.evaluation_ids() if self.current_state(e) == state)

    def evaluation_meta(self, evaluation: str) -> dict:
        return self._meta(evaluation)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> EvaluationSummary:
        return EvaluationSummary(
            timestamp=now, evaluation_event_count=len(ledger.read_evaluation_events()),
            criterion_count=len(ledger.read_criteria()), score_count=len(ledger.read_scores()),
            benchmark_count=len(ledger.read_benchmarks()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
