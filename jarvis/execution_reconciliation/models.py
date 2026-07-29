"""Execution Reconciliation 자료형 (P7.6) — 집행 '결과' 검증만. **집행 아님.**

ExecutionIntent + ExecutionSimulationReport → [수량·가격·수수료·슬리피지·타이밍] →
ExecutionValidationReport(PASS/WARNING/FAILED).
**주문/체결을 생성하지 않는다 — 이미 있는 (가상) 결과가 의도와 맞는지 검증만.**
결정적·읽기전용·재현가능. 브로커 없음·게이트웨이 없음·포지션 변경 없음.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field

PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

_ORDER = {PASS: 0, WARNING: 1, FAILED: 2}
_BPS = 10_000.0
_EPS = 1e-12


@dataclass(frozen=True)
class ExecutionExpectation:
    intent_id: str
    symbol: str
    side: str
    expected_quantity: float
    expected_price: float
    expected_fee: float
    timestamp: str            # 의도 시각(타이밍 기준)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ValidationThresholds:
    quantity_tolerance: float = 1e-6      # 수량 절대 허용오차(WARNING 경계)
    price_tolerance_bps: float = 10.0     # 가격/슬리피지 허용(bps)
    fee_tolerance_bps: float = 5.0        # 수수료 허용(명목 대비 bps)
    timing_seconds: float = 60.0          # 타이밍 허용(초)
    fail_multiplier: float = 3.0          # 허용×배수 초과 → FAILED


@dataclass(frozen=True)
class ExecutionValidationReport:
    validation_id: str
    intent_id: str
    status: str               # PASS | WARNING | FAILED
    checks: list = field(default_factory=list)
    deviations: dict = field(default_factory=dict)
    timestamp: str = ""
    input_hash: str = ""
    hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def max_status(statuses: list) -> str:
    worst = PASS
    for s in statuses:
        if _ORDER.get(s, 0) > _ORDER[worst]:
            worst = s
    return worst


def grade(deviation: float, tolerance: float, fail_multiplier: float) -> str:
    """편차→등급. ≤허용 PASS, ≤허용×배수 WARNING, 초과 FAILED."""
    if deviation <= tolerance + _EPS:
        return PASS
    if deviation <= tolerance * fail_multiplier + _EPS:
        return WARNING
    return FAILED


def validation_id(intent_id: str, input_hash_: str) -> str:
    return "VR:" + hashlib.sha1(f"{intent_id}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(expectation: dict, actual: dict) -> str:
    blob = json.dumps({"expectation": expectation, "actual": actual},
                      sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def validation_hash(validation_id_: str, intent_id_: str, status: str,
                    checks: list, deviations: dict, input_hash_: str) -> str:
    payload = {"validation_id": validation_id_, "intent_id": intent_id_, "status": status,
               "checks": [(c["name"], c["status"]) for c in checks],
               "deviations": deviations, "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def _parse(ts: str):
    try:
        return _dt.datetime.fromisoformat((ts or "").replace("Z", "+00:00"))
    except ValueError:
        return None


def seconds_between(a: str, b: str) -> float | None:
    da, db = _parse(a), _parse(b)
    if da is None or db is None:
        return None
    return abs((db - da).total_seconds())
