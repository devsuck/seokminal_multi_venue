"""Research Reviewer Engine (P11.5) — 연구 품질 AI 비평/리뷰어. **평가·기록 전용.**

통계적 품질·강건성·재현성·리스크·신규성 5개 차원을 결정적으로 평가해 리뷰 리포트(PASS·WARNING·REJECT_RESEARCH)를
낸다. **연구 거부는 전략 삭제가 아니다. 자동 결정 없음.** 평결은 권고일 뿐 어떤 실행/승인/삭제도 하지 않는다.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. REVIEW ≠ DECISION · REJECT_RESEARCH ≠ DELETE_STRATEGY · VERDICT ≠ ACTION. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_reviewer import ledger
from jarvis.research_reviewer.models import (
    DIMENSIONS,
    EVIDENCE_TYPES,
    GENESIS,
    SEVERITIES,
    CritiqueRecord,
    EvidenceRecord,
    ImmutableCritiqueError,
    ImmutableEvidenceError,
    ImmutableReviewError,
    InvalidDimension,
    InvalidEvidenceType,
    InvalidSeverity,
    ReviewRecord,
    ReviewerReportRecord,
    ReviewerSummary,
    UnknownCritiqueError,
    UnknownReviewError,
    content_hash,
    critique_id as _critique_id,
    dimension_verdict,
    evidence_id as _evidence_id,
    input_digest,
    overall_score as _overall_score,
    overall_verdict as _overall_verdict,
    report_id as _report_id,
    review_id as _review_id,
    validate_scores,
)

_DISCLAIMER = ("Research Reviewer 데이터 — REVIEW ≠ DECISION · REJECT_RESEARCH ≠ DELETE_STRATEGY · VERDICT ≠ "
               "ACTION. 연구 품질 평가·권고 전용 — 자동 결정/승인/삭제 없음. 연구 거부는 전략 삭제가 아니다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchReviewerEngine:
    """연구 품질 AI 리뷰어. 불변·append-only·결정적. 결정/승인/삭제/실행 권한 없음(권고만)."""

    # ══════════════ create_review (결정적) ══════════════
    def create_review(self, subject: str, reviewer: str, dimension_scores: dict,
                    subject_type: str = "RESEARCH", now: str = "",
                    *, commit: bool = False) -> ReviewRecord:
        """5개 차원 점수로 결정적 리뷰 생성. 평결은 순수 함수 산출. **REVIEW ≠ DECISION — 자동 결정 없음.**"""
        validate_scores(dimension_scores)
        scores = {k: round(float(dimension_scores[k]), 8) for k in sorted(dimension_scores)}
        dim_verdicts = {k: dimension_verdict(v) for k, v in scores.items()}
        ov = _overall_score(scores)
        verdict = _overall_verdict(scores)
        rid = _review_id(subject, reviewer)
        existing = ledger.get_review(rid)
        if existing is not None:
            if dict(existing.get("dimension_scores", {})) != scores:
                raise ImmutableReviewError(f"{rid} 리뷰 불변 — 변경 불가")
            return ReviewRecord(**{k: v for k, v in existing.items()
                                   if k in ReviewRecord.__dataclass_fields__})
        rec = ReviewRecord(
            review_id=rid, subject=subject, subject_type=subject_type, reviewer=reviewer,
            dimension_scores=scores, dimension_verdicts=dim_verdicts, overall_score=ov,
            verdict=verdict, no_auto_decision=True, created_at=now,
            input_hash=input_digest(subject, reviewer), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.review_exists(rid):
            head = ledger.reviews_head()
            ledger.append_review(_seal(rec, head["record_hash"] if head else GENESIS))
        return ReviewRecord(**rec)

    def _require_review(self, rid: str) -> dict:
        rec = ledger.get_review(rid)
        if rec is None:
            raise UnknownReviewError(f"미등록 리뷰 {rid}")
        return rec

    # ══════════════ add_critique ══════════════
    def add_critique(self, review: str, dimension: str, severity: str, description: str,
                   now: str = "", *, commit: bool = False) -> CritiqueRecord:
        """리뷰 차원별 비평(발견) 기록(불변). **비평·기록만.**"""
        self._require_review(review)
        if dimension not in DIMENSIONS:
            raise InvalidDimension(f"미등록 차원 {dimension}")
        if severity not in SEVERITIES:
            raise InvalidSeverity(f"미등록 심각도 {severity}")
        cid = _critique_id(review, dimension, description)
        existing = ledger.get_critique(cid)
        if existing is not None:
            if existing.get("severity") != severity:
                raise ImmutableCritiqueError(f"{cid} 비평 불변 — 변경 불가")
            return CritiqueRecord(**{k: v for k, v in existing.items()
                                     if k in CritiqueRecord.__dataclass_fields__})
        rec = CritiqueRecord(critique_id=cid, review_id=review, dimension=dimension,
                             severity=severity, description=description, created_at=now,
                             input_hash=input_digest(review, dimension, description),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.critique_exists(cid):
            head = ledger.critiques_head()
            ledger.append_critique(_seal(rec, head["record_hash"] if head else GENESIS))
        return CritiqueRecord(**rec)

    # ══════════════ add_evidence (linkage) ══════════════
    def add_evidence(self, critique: str, evidence_type: str, reference: str, detail: str = "",
                   now: str = "", *, commit: bool = False) -> EvidenceRecord:
        """비평을 뒷받침하는 증거 기록·연결(불변). 참조는 READ ONLY. **증거 연결만.**"""
        if not ledger.critique_exists(critique):
            raise UnknownCritiqueError(f"미등록 비평 {critique}")
        if evidence_type not in EVIDENCE_TYPES:
            raise InvalidEvidenceType(f"미등록 증거 종류 {evidence_type}")
        eid = _evidence_id(critique, evidence_type, reference)
        existing = ledger.get_evidence(eid)
        if existing is not None:
            if existing.get("detail") != detail:
                raise ImmutableEvidenceError(f"{eid} 증거 불변 — 변경 불가")
            return EvidenceRecord(**{k: v for k, v in existing.items()
                                     if k in EvidenceRecord.__dataclass_fields__})
        rec = EvidenceRecord(evidence_id=eid, critique_id=critique, evidence_type=evidence_type,
                             reference=reference, detail=detail, created_at=now,
                             input_hash=input_digest(critique, evidence_type, reference),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidence_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        return EvidenceRecord(**rec)

    # ══════════════ 조회: 증거 연쇄 ══════════════
    def evidence_for_review(self, review: str) -> list:
        """리뷰 → 비평 → 증거 연쇄 조회(결정적). **조회 전용.**"""
        out: list = []
        for c in ledger.review_critiques(review):
            for ev in ledger.critique_evidence(c.get("critique_id")):
                out.append(ev.get("evidence_id"))
        return sorted(set(out))

    def critiques_by_dimension(self, review: str, dimension: str) -> list:
        return sorted(c.get("critique_id") for c in ledger.review_critiques(review)
                      if c.get("dimension") == dimension)

    # ══════════════ generate_report (immutable) ══════════════
    def generate_report(self, review: str, now: str = "", *, commit: bool = False) -> ReviewerReportRecord:
        """리뷰어 리포트(평결·차원 점수·비평/증거 집계). **권고 리포트 — is_decision=False.**"""
        rv = self._require_review(review)
        critiques = ledger.review_critiques(review)
        sev_dist: dict = {}
        ev_count = 0
        for c in critiques:
            sev_dist[c.get("severity")] = sev_dist.get(c.get("severity"), 0) + 1
            ev_count += len(ledger.critique_evidence(c.get("critique_id")))
        rid = _report_id(rv.get("subject"), review, now)
        rec = ReviewerReportRecord(
            report_id=rid, subject=rv.get("subject"), review_id=review, verdict=rv.get("verdict"),
            overall_score=rv.get("overall_score"), dimension_scores=rv.get("dimension_scores"),
            critique_count=len(critiques), evidence_count=ev_count,
            severity_distribution=dict(sorted(sev_dist.items())), is_decision=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(rv.get("subject"), review, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return ReviewerReportRecord(**rec)

    # ══════════════ 조회 편의 ══════════════
    def get_verdict(self, review: str) -> str:
        return self._require_review(review).get("verdict")

    def list_reviews(self, verdict: str = "") -> list:
        rvs = ledger.read_reviews()
        if verdict:
            rvs = [r for r in rvs if r.get("verdict") == verdict]
        return sorted(r.get("review_id") for r in rvs)

    def reviews_of_subject(self, subject: str) -> list:
        return sorted(r.get("review_id") for r in ledger.read_reviews()
                      if r.get("subject") == subject)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ReviewerSummary:
        reviews = ledger.read_reviews()
        v_dist: dict = {}
        for r in reviews:
            v_dist[r.get("verdict")] = v_dist.get(r.get("verdict"), 0) + 1
        return ReviewerSummary(
            timestamp=now, review_count=len(reviews),
            critique_count=len(ledger.read_critiques()), evidence_count=len(ledger.read_evidence()),
            report_count=len(ledger.read_reports()), verdict_distribution=dict(sorted(v_dist.items())))
