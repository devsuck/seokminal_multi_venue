"""Personal Research Assistant 자료형 (P44) — 개인 연구 어시스턴트. **분석만, 결정·승인·집행 없음.**

한 명의 연구자가 Jarvis 산출물을 이해하도록 돕는다: 일일 요약·최근 실험 요약·실패 분석·지식 리캡·연구 진행 요약·
잠재 연구 영역. **기존 원장을 READ ONLY 로 읽어 분석만 한다 — 투자 결정·전략 승인·행동 실행을 하지 않는다.**
ASSISTANT ANALYZES · DOES NOT DECIDE / APPROVE / EXECUTE. 산출은 is_advisory=True·is_decision=False. 결정적·불변·
append-only·SHA256 해시체인. 물리 원장 ras_ 접두사.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

GENESIS = "GENESIS"

# ── 읽어들이는 기존 원장(READ ONLY 소스) — import 결합 없음, 파일명만 매핑 ──
SOURCES = {
    "experiment_runs": "expt_runs.jsonl",          # 실험 실행
    "experiment_results": "expt_results.jsonl",     # 실험 결과(metric/value)
    "experiments": "expt_experiments.jsonl",         # 실험 정의
    "memories": "rmi_memories.jsonl",                 # 지식/기억
    "lessons": "rmi_lessons.jsonl",                    # 교훈
    "patterns": "rmi_patterns.jsonl",                   # 패턴
    "failures": "rmi_failures.jsonl",                    # 실패 기록
    "successes": "rmi_successes.jsonl",                   # 성공 기록
    "incidents": "rel_incidents.jsonl",                    # 신뢰성 인시던트
    "models": "mdl_models.jsonl",                           # 모델
    "validations": "mdl_validations.jsonl",                  # 모델 검증
}

# 실패 신호로 볼 상태 문자열(대문자 비교)
_FAILURE_TOKENS = ("FAIL", "ERROR", "INCIDENT", "REGRESS", "BROKEN", "UNSTABLE")

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "APPROVE_FOR_TRADING", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "DECIDE",
    "SELECT_STRATEGY", "MAKE_DECISION",
})

DISCLAIMER = ("Personal Research Assistant — ASSISTANT ANALYZES · DOES NOT DECIDE / APPROVE / "
              "EXECUTE. 기존 원장 READ ONLY 분석 요약일 뿐, 투자 결정·전략 승인·행동 실행이 아니다. "
              "잠재 영역은 '가능한 다음 검토' 제안일 뿐 사람 검토 필요.")


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_digest(payload) -> str:
    return _digest(payload)


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items()
            if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def report_id(scope, created_at) -> str:
    return _id("PRASR", scope, created_at)


def note_id(area, seq) -> str:
    return _id("PRASN", area, seq)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def is_failure_signal(value) -> bool:
    """상태/사유 문자열이 실패 신호를 담는가(대소문자 무시)."""
    s = str(value or "").upper()
    return any(tok in s for tok in _FAILURE_TOKENS)


def first_field(record: dict, fields) -> str:
    """레코드에서 후보 필드 중 처음 존재하는 값(문자열). 없으면 ''."""
    for f in fields:
        if f in record and record[f] not in (None, ""):
            return str(record[f])
    return ""


# ── 연구 실패 분류체계(Failure Intelligence) — Agentic Research Evolution 문서 9종 + 미분류 ──
FAIL_OVERFITTING = "OVERFITTING"
FAIL_DATA_LEAKAGE = "DATA_LEAKAGE"
FAIL_REGIME_CHANGE = "REGIME_CHANGE"
FAIL_COST_SENSITIVITY = "COST_SENSITIVITY"
FAIL_LIQUIDITY = "LIQUIDITY"
FAIL_POOR_HYPOTHESIS = "POOR_HYPOTHESIS"
FAIL_TIMING = "TIMING"
FAIL_RISK_CONCENTRATION = "RISK_CONCENTRATION"
FAIL_PARAMETER_INSTABILITY = "PARAMETER_INSTABILITY"
FAIL_UNCLASSIFIED = "UNCLASSIFIED"
FAILURE_TAXONOMY = (
    FAIL_OVERFITTING, FAIL_DATA_LEAKAGE, FAIL_REGIME_CHANGE, FAIL_COST_SENSITIVITY, FAIL_LIQUIDITY,
    FAIL_POOR_HYPOTHESIS, FAIL_TIMING, FAIL_RISK_CONCENTRATION, FAIL_PARAMETER_INSTABILITY,
    FAIL_UNCLASSIFIED,
)
# 분류 키워드(우선순위 순서대로 첫 일치; 영/한). 결정적.
_FAILURE_RULES = (
    (FAIL_DATA_LEAKAGE, ("leak", "lookahead", "look-ahead", "look ahead", "future data", "누설", "룩어헤드", "미래데이터")),
    (FAIL_OVERFITTING, ("overfit", "over-fit", "over fit", "curve fit", "curve-fit", "in-sample", "in sample", "과적합")),
    (FAIL_REGIME_CHANGE, ("regime", "structural break", "regime change", "레짐", "국면")),
    (FAIL_COST_SENSITIVITY, ("cost sensitiv", "transaction cost", "slippage", "fee", "turnover", "비용", "수수료", "슬리피지")),
    (FAIL_LIQUIDITY, ("liquidity", "illiquid", "thin volume", "low volume", "유동성")),
    (FAIL_PARAMETER_INSTABILITY, ("parameter instab", "unstable param", "param sensit", "parameter sensit", "instability", "파라미터", "불안정")),
    (FAIL_RISK_CONCENTRATION, ("concentration", "concentrated", "over-exposed", "overexposed", "correlated risk", "집중", "편중")),
    (FAIL_TIMING, ("timing", "latency", "delay", "late entry", "타이밍", "지연")),
    (FAIL_POOR_HYPOTHESIS, ("poor hypothesis", "weak signal", "no edge", "spurious", "insignificant", "가설 약", "약한 가설")),
)


def classify_failure(text) -> str:
    """실패 텍스트 → 분류체계 카테고리(결정적, 첫 일치 우선). 매칭 없으면 UNCLASSIFIED."""
    t = str(text or "").lower()
    for cat, kws in _FAILURE_RULES:
        if any(k in t for k in kws):
            return cat
    return FAIL_UNCLASSIFIED


# 검색 텍스트에서 제외할 메타 키(해시/인풋해시 등 — 노이즈·오탐 방지)
_META_KEYS = ("previous_hash", "record_hash", "report_hash", "input_hash", "content_hash",
              "bundle_digest", "result_digest")


# 질문에서 주제어를 뽑을 때 버릴 불용어(영/한 — 질문어·조사)
_STOPWORDS = frozenset({
    "have", "we", "i", "tried", "try", "did", "does", "do", "is", "are", "was", "the", "a", "an",
    "this", "that", "idea", "already", "before", "why", "what", "when", "how", "should", "review",
    "next", "learn", "learned", "about", "from", "research", "week", "recent", "recently", "changed",
    "on", "in", "of", "to", "for", "our", "us", "me", "you", "it", "any", "some",
    "예전에", "해봤어", "해봤", "했어", "했나", "왜", "실패", "실패했어", "이번", "주에", "최근", "다음",
    "뭘", "봐야", "볼까", "우리", "이거", "이번주", "무슨", "일이", "있었어", "배운", "지식", "관련",
    "perspective", "perspectives", "opinion", "opinions", "critique", "view", "views", "give",
    "관점", "비평", "다각도", "시각", "give me", "mistake", "mistakes",
})


def extract_topic(question: str) -> str:
    """질문에서 주제어(가장 긴 비불용어 토큰)를 결정적으로 추출. 없으면 ''."""
    import re
    toks = re.findall(r"[0-9A-Za-z가-힣_]+", question or "")
    cand = [t for t in toks if t.lower() not in _STOPWORDS and len(t) >= 2]
    if not cand:
        return ""
    # 가장 긴 토큰(동률이면 첫 등장) — 결정적
    return max(cand, key=lambda t: (len(t), -toks.index(t)))


def record_text(record: dict) -> str:
    """레코드의 검색 가능한 문자열/숫자 값을 이어붙인다(해시/메타 제외). recall 검색용."""
    parts = []
    for k, v in record.items():
        if k in _META_KEYS:
            continue
        if isinstance(v, str):
            parts.append(v)
        elif isinstance(v, (int, float, bool)):
            parts.append(str(v))
    return " ".join(parts)


def numeric_stats(values) -> dict:
    """숫자 목록 통계(count/min/max/mean, 결정적 반올림). 빈 목록이면 0."""
    nums = []
    for v in values:
        try:
            nums.append(float(v))
        except (TypeError, ValueError):
            continue
    if not nums:
        return {"count": 0, "min": 0.0, "max": 0.0, "mean": 0.0}
    return {"count": len(nums), "min": round(min(nums), 6), "max": round(max(nums), 6),
            "mean": round(sum(nums) / len(nums), 6)}


# ── 분석 결과 자료형(순수, 해시 없음) ──
@dataclass(frozen=True)
class DailySummary:
    total_records: int
    active_sources: int
    source_counts: dict
    headline: str
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExperimentSummary:
    run_count: int
    result_count: int
    metric_stats: dict
    headline: str
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureAnalysis:
    failure_count: int
    clusters: dict           # {reason: count}
    findings: list
    suggested_reviews: list
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class KnowledgeRecap:
    memory_count: int
    lesson_count: int
    pattern_count: int
    recent_topics: list
    headline: str
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProgressSummary:
    stage_counts: dict
    progress_notes: list
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PotentialAreas:
    areas: list              # [{area, rationale, evidence}]
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


# ── 원장 레코드(해시체인) ──
@dataclass(frozen=True)
class AssistantReportRecord:
    report_id: str
    scope: str
    total_records: int
    experiment_run_count: int
    failure_count: int
    knowledge_count: int
    potential_area_count: int
    bundle_digest: str
    is_advisory: bool
    is_decision: bool
    requires_human_review: bool
    disclaimer: str
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AdvisoryNoteRecord:
    note_id: str
    area: str
    rationale: str
    evidence_count: int
    is_binding: bool
    requires_human_review: bool
    created_at: str
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RecallResult:
    """메모리 등뼈(C2) — 흩어진 지식 원장 통합 검색 결과. '예전에 해봤어?'의 답. 분석만."""
    topic: str
    total_hits: int
    tried_before: bool
    source_hits: dict        # {source: [{ref, text}]}
    sources_hit: list
    headline: str
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FailureIntelligenceResult:
    """Failure Intelligence — 실패를 분류체계로 구조화. '왜 실패했나' + '이전에 같은 실수 했나'. 분석만."""
    total_failures: int
    by_category: dict          # {category: count}
    records: list              # [{ref, category, text, source}]
    top_category: str
    lessons: list              # 카테고리별 교훈 문장
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class AssistantSummary:
    timestamp: str
    report_count: int
    note_count: int

    def to_dict(self) -> dict:
        return asdict(self)
