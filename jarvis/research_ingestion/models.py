"""Research Ingestion 자료형 (P53) — 백테스트 결과 → 연구 메모리. **통합 오케스트레이터, 실행 없음.**

완료된 백테스트를 기존 실험 원장(expt_)·실패 메모리(rmi_)로 흘려보낸다. **새 실험/실패 저장소를 만들지 않는다 —
기존 엔진 API로 기록만.** 결정적 결과 판정 + 9종 실패 자동분류(research_assistant 분류체계 재사용). 거래·집행·배포 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass

from jarvis.research_assistant.models import classify_failure  # 9종 분류체계 재사용(통합)

GENESIS = "GENESIS"

# ── 결과 판정 ──
OUT_SUCCESS = "SUCCESS"
OUT_FAILURE = "FAILURE"
OUT_PARTIAL = "PARTIAL"
OUT_INCOMPLETE = "INCOMPLETE"
OUTCOMES = (OUT_SUCCESS, OUT_FAILURE, OUT_PARTIAL, OUT_INCOMPLETE)

# ── 필수 검증 지표(문서 §7) — 없으면 INCOMPLETE ──
REQUIRED_VALIDATIONS = (
    "return", "sharpe", "max_drawdown", "volatility", "walk_forward", "out_of_sample",
    "cost_impact", "parameter_stability", "random_baseline",
)

# 판정 임계(모듈 상수 — 결정적)
_SHARPE_SUCCESS = 0.5
_OOS_MIN = 0.3
_MDD_FLOOR = -0.35

# 실패 분류 재사용 카테고리(문자열)
FAIL_OVERFITTING = "OVERFITTING"
FAIL_COST = "COST_SENSITIVITY"
FAIL_PARAM = "PARAMETER_INSTABILITY"
FAIL_POOR = "POOR_HYPOTHESIS"
FAIL_REGIME = "REGIME_CHANGE"
FAIL_UNCLASSIFIED = "UNCLASSIFIED"

FORBIDDEN_VERBS = frozenset({
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
})


class SchemaError(Exception):
    """백테스트 입력 스키마 위반."""


def _digest(payload) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def input_digest(*parts) -> str:
    return _digest(list(parts))


def content_hash(record: dict) -> str:
    core = {k: v for k, v in record.items() if k not in ("previous_hash", "record_hash")}
    return _digest(core)


def backtest_hash(backtest: dict) -> str:
    """백테스트 입력 전체의 내용 해시(중복 탐지·검증용)."""
    return _digest(backtest or {})


def _id(tag, *parts) -> str:
    return f"{tag}:" + hashlib.sha1(input_digest(*parts).encode()).hexdigest()[:12]


def ingestion_id(strategy_name, bt_hash) -> str:
    return _id("RING", strategy_name, bt_hash)


def is_forbidden_verb(word) -> bool:
    return (word or "").strip().upper() in FORBIDDEN_VERBS


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def validate_backtest(backtest: dict) -> dict:
    """백테스트 입력 스키마 검증. 필수 필드·필수 검증지표 존재 확인. (거부하지 않고 상태만 반환.)"""
    bt = backtest or {}
    missing_fields = [f for f in ("strategy_name",) if not str(bt.get(f, "")).strip()]
    metrics = bt.get("metrics") or {}
    missing_validations = [m for m in REQUIRED_VALIDATIONS if m not in metrics]
    return {"ok": not missing_fields, "missing_fields": missing_fields,
            "missing_validations": missing_validations,
            "validation_complete": not missing_validations}


def classify_outcome(metrics: dict, explicit: str = "", validation_complete: bool = True) -> str:
    """결과 판정(결정적). 명시 outcome 우선, 없으면 지표로 판정. 검증 미완이면 INCOMPLETE."""
    if explicit:
        e = explicit.strip().upper()
        if e in OUTCOMES:
            return e
    m = metrics or {}
    sharpe = _num(m.get("sharpe"))
    if sharpe is None:
        return OUT_INCOMPLETE
    oos = _num(m.get("out_of_sample"))
    mdd = _num(m.get("max_drawdown"))
    if not validation_complete:
        # 지표는 있으나 필수 검증 세트가 불완전 → 부분/미완
        return OUT_INCOMPLETE
    ok_oos = oos is None or oos >= _OOS_MIN
    ok_mdd = mdd is None or mdd >= _MDD_FLOOR
    if sharpe >= _SHARPE_SUCCESS and ok_oos and ok_mdd:
        return OUT_SUCCESS
    if 0.0 <= sharpe < _SHARPE_SUCCESS:
        return OUT_PARTIAL
    return OUT_FAILURE


def auto_classify_failure(metrics: dict, reason: str = "") -> str:
    """실패를 9종 분류체계로 자동 분류. 명시 사유가 있으면 그 텍스트로, 없으면 지표 휴리스틱(결정적)."""
    if (reason or "").strip():
        cat = classify_failure(reason)
        if cat != "UNCLASSIFIED":
            return cat
    m = metrics or {}
    sharpe, oos = _num(m.get("sharpe")), _num(m.get("out_of_sample"))
    cost = _num(m.get("cost_impact"))
    pstab = _num(m.get("parameter_stability"))
    rbase = _num(m.get("random_baseline"))
    # 순서 = 결정적 우선순위
    if sharpe is not None and oos is not None and (sharpe - oos) >= 0.5:
        return FAIL_OVERFITTING
    if cost is not None and cost >= 0.3:
        return FAIL_COST
    if pstab is not None and pstab <= 0.3:
        return FAIL_PARAM
    if rbase is not None and sharpe is not None and sharpe <= rbase:
        return FAIL_POOR
    if m.get("regime_dependent") is True:
        return FAIL_REGIME
    if (reason or "").strip():
        return classify_failure(reason)   # UNCLASSIFIED 라도 일관 반환
    return FAIL_UNCLASSIFIED


@dataclass(frozen=True)
class IngestionRecord:
    ingestion_id: str
    backtest_hash: str
    strategy_name: str
    strategy_version: str
    experiment_id: str
    run_id: str
    outcome: str
    failure_category: str
    validation_complete: bool
    metric_count: int
    source: str
    created_at: str
    source_type: str = ""       # "" | "historical_import" (provenance — 해시 미포함)
    source_file: str = ""       # 원본 파일 경로(추적성) — backtest_hash 에 미포함
    input_hash: str = ""
    record_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IngestionResult:
    ingestion_id: str
    experiment_id: str
    run_id: str
    outcome: str
    failure_category: str
    validation_complete: bool
    missing_validations: list
    parameters_written: int
    results_written: int
    memory_written: str        # failure | success | none
    deduplicated: bool
    is_advisory: bool = True
    is_decision: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class IngestionSummary:
    timestamp: str
    ingestion_count: int
    by_outcome: dict
    by_failure_category: dict
    by_source_type: dict = None  # {"": n, "historical_import": m} — 이력/실시간 구분

    def to_dict(self) -> dict:
        d = asdict(self)
        if d.get("by_source_type") is None:
            d["by_source_type"] = {}
        return d
