"""AI Research Reviewer 자료형 (P11.5) — 연구 품질 AI 비평/리뷰어. **평가·기록 전용.**

통계적 품질·강건성·재현성·리스크·신규성 5개 차원을 평가해 리뷰 리포트(PASS·WARNING·REJECT_RESEARCH)를 낸다.
**연구 거부는 전략 삭제가 아니다. 자동 결정 없음.** 평결은 권고일 뿐 어떤 실행/승인/삭제도 하지 않는다.
REVIEW ≠ DECISION · REJECT_RESEARCH ≠ DELETE_STRATEGY · VERDICT ≠ ACTION. 불변·append-only·해시체인.
물리 원장은 rvw_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

GENESIS = "GENESIS"

# ── 평가 차원(5) ──
DIM_STATISTICAL = "STATISTICAL"
DIM_ROBUSTNESS = "ROBUSTNESS"
DIM_REPRODUCIBILITY = "REPRODUCIBILITY"
DIM_RISK = "RISK"
DIM_NOVELTY = "NOVELTY"
DIMENSIONS = (DIM_STATISTICAL, DIM_ROBUSTNESS, DIM_REPRODUCIBILITY, DIM_RISK, DIM_NOVELTY)

# ── 평결 ──
V_PASS = "PASS"
V_WARNING = "WARNING"
V_REJECT_RESEARCH = "REJECT_RESEARCH"
VERDICTS = (V_PASS, V_WARNING, V_REJECT_RESEARCH)

# ── 비평 심각도 ──
SEV_INFO = "INFO"
SEV_MINOR = "MINOR"
SEV_MAJOR = "MAJOR"
SEV_CRITICAL = "CRITICAL"
SEVERITIES = (SEV_INFO, SEV_MINOR, SEV_MAJOR, SEV_CRITICAL)

# ── 증거 종류 ──
EV_METRIC = "METRIC"
EV_PLOT = "PLOT"
EV_CITATION = "CITATION"
EV_DATA = "DATA"
EV_REPLAY = "REPLAY"
EV_EXTERNAL = "EXTERNAL"
EVIDENCE_TYPES = (EV_METRIC, EV_PLOT, EV_CITATION, EV_DATA, EV_REPLAY, EV_EXTERNAL)

# ── 자동 결정 금지 동사(탐지용) ──
FORBIDDEN_VERBS = frozenset({
    "APPROVE", "AUTO_APPROVE", "DEPLOY", "DELETE", "DELETE_STRATEGY", "REMOVE_STRATEGY",
    "EXECUTE", "TRADE", "ALLOCATE", "ACTIVATE", "PROMOTE", "DECIDE",
})

# ── 평결 임계 ──
_TH_REJECT_MIN = 0.3
_TH_REJECT_OVERALL = 0.4
_TH_WARN_MIN = 0.5
_TH_WARN_OVERALL = 0.7


class ImmutableReviewError(Exception):
    """불변 리뷰 위반."""


class ImmutableCritiqueError(Exception):
    """불변 비평 위반."""


class ImmutableEvidenceError(Exception):
    """불변 증거 위반."""


class ImmutableReportError(Exception):
    """불변 리포트 위반."""


class InvalidDimension(Exception):
    """미등록 평가 차원."""


class MissingDimensions(Exception):
    """평가 차원 누락(5개 모두 필요)."""


class InvalidScore(Exception):
    """점수 범위 위반(0~1)."""


class InvalidSeverity(Exception):
    """미등록 심각도."""


class InvalidEvidenceType(Exception):
    """미등록 증거 종류."""


class UnknownReviewError(Exception):
    """미등록 리뷰 참조."""


class UnknownCritiqueError(Exception):
    """미등록 비평 참조."""


# ── 해시 ──
def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash", "report_hash")}
    return _digest(core)


# ── 결정적 ID ──
def review_id(subject: str, reviewer: str) -> str:
    return "RVW:" + hashlib.sha1(input_digest(subject, reviewer).encode()).hexdigest()[:12]


def critique_id(review: str, dimension: str, description: str) -> str:
    return "RVC:" + hashlib.sha1(
        input_digest(review, dimension, description).encode()).hexdigest()[:12]


def evidence_id(critique: str, evidence_type: str, reference: str) -> str:
    return "RVE:" + hashlib.sha1(
        input_digest(critique, evidence_type, reference).encode()).hexdigest()[:12]


def report_id(subject: str, review: str, generated_at: str) -> str:
    return "RVR:" + hashlib.sha1(
        input_digest(subject, review, generated_at).encode()).hexdigest()[:12]


# ── 결정적 평가 함수 ──
def is_forbidden_verb(word: str) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def dimension_verdict(score: float) -> str:
    """단일 차원 평결(결정적)."""
    if score < _TH_REJECT_MIN:
        return V_REJECT_RESEARCH
    if score < _TH_WARN_MIN:
        return V_WARNING
    return V_PASS


def overall_score(scores: dict) -> float:
    """차원 점수 평균(결정적, 8자리)."""
    vals = [float(scores[k]) for k in sorted(scores)]
    return round(sum(vals) / len(vals), 8) if vals else 0.0


def overall_verdict(scores: dict) -> str:
    """전체 평결(결정적): 최저 차원·평균 기준. **권고일 뿐 — VERDICT ≠ ACTION.**"""
    if not scores:
        return V_WARNING
    vals = [float(v) for v in scores.values()]
    lo = min(vals)
    ov = overall_score(scores)
    if lo < _TH_REJECT_MIN or ov < _TH_REJECT_OVERALL:
        return V_REJECT_RESEARCH
    if lo < _TH_WARN_MIN or ov < _TH_WARN_OVERALL:
        return V_WARNING
    return V_PASS


def validate_scores(scores: dict) -> None:
    """차원 점수 검증: 5개 모두·0~1 범위·미등록 차원 없음."""
    for k in scores:
        if k not in DIMENSIONS:
            raise InvalidDimension(f"미등록 차원 {k}")
    for k in DIMENSIONS:
        if k not in scores:
            raise MissingDimensions(f"차원 누락 {k}")
        v = float(scores[k])
        if v < 0.0 or v > 1.0:
            raise InvalidScore(f"{k} 점수 범위 위반 {v}")


# ── 레코드 자료형 ──
@dataclass(frozen=True)
class ReviewRecord:
    review_id: str
    subject: str
    subject_type: str
    reviewer: str
    dimension_scores: dict
    dimension_verdicts: dict
    overall_score: float
    verdict: str
    no_auto_decision: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CritiqueRecord:
    critique_id: str
    review_id: str
    dimension: str
    severity: str
    description: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class EvidenceRecord:
    evidence_id: str
    critique_id: str
    evidence_type: str
    reference: str
    detail: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerReportRecord:
    report_id: str
    subject: str
    review_id: str
    verdict: str
    overall_score: float
    dimension_scores: dict
    critique_count: int
    evidence_count: int
    severity_distribution: dict
    is_decision: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ReviewerSummary:
    timestamp: str
    review_count: int
    critique_count: int
    evidence_count: int
    report_count: int
    verdict_distribution: dict

    def to_dict(self) -> dict:
        return asdict(self)
