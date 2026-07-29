"""Fill Reconciliation 자료형 (P8.3) — 브로커 체결 vs 내부 주문 생애주기 대조.

**집행 아님·주문 없음·브로커 write 없음.** 브로커가 '보고한' 체결과 내부 기대를 비교만.
BrokerFill · InternalExecutionRecord · FillReconciliationReport(MATCHED/WARNING/FAILED).
결정적·읽기전용·재현가능·해시체인 append-only.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
from dataclasses import asdict, dataclass, field

MATCHED = "MATCHED"
WARNING = "WARNING"
FAILED = "FAILED"

GENESIS = "GENESIS"

_ORDER = {MATCHED: 0, WARNING: 1, FAILED: 2}
_BPS = 10_000.0
_EPS = 1e-12


@dataclass(frozen=True)
class BrokerFill:
    fill_id: str
    broker_order_id: str
    symbol: str
    side: str                  # BUY | SELL
    quantity: float
    fill_price: float
    fee: float
    timestamp: str
    source: str = "broker"     # 보고 출처(ib|kis|mock|broker)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class InternalExecutionRecord:
    order_id: str
    request_id: str
    expected_quantity: float
    expected_price: float
    expected_side: str
    submitted_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class FillThresholds:
    quantity_tolerance: float = 1e-6      # 수량 절대 허용(WARNING 경계)
    price_tolerance_bps: float = 10.0     # 가격 허용(bps)
    fee_tolerance: float = 0.01           # 수수료 절대 허용
    timing_seconds: float = 60.0          # 타이밍 허용(초)
    fail_multiplier: float = 3.0          # 허용×배수 초과 → FAILED


@dataclass(frozen=True)
class FillReconciliationReport:
    report_id: str
    order_id: str
    broker_order_id: str
    status: str               # MATCHED | WARNING | FAILED
    checks: dict = field(default_factory=dict)
    aggregate: dict = field(default_factory=dict)
    reason: str = ""
    input_hash: str = ""
    report_hash: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def max_status(statuses: list) -> str:
    worst = MATCHED
    for s in statuses:
        if _ORDER.get(s, 0) > _ORDER[worst]:
            worst = s
    return worst


def grade(deviation: float, tolerance: float, fail_multiplier: float) -> str:
    """편차→등급. ≤허용 MATCHED, ≤허용×배수 WARNING, 초과 FAILED."""
    if deviation <= tolerance + _EPS:
        return MATCHED
    if deviation <= tolerance * fail_multiplier + _EPS:
        return WARNING
    return FAILED


def report_id(order_id: str, broker_order_id: str, input_hash_: str) -> str:
    return "FRR:" + hashlib.sha1(
        f"{order_id}|{broker_order_id}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(record: dict | None, aggregate: dict) -> str:
    blob = json.dumps({"record": record, "aggregate": aggregate},
                      sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_hash(report_id_: str, order_id: str, status: str, checks: dict,
                aggregate: dict, input_hash_: str) -> str:
    payload = {"report_id": report_id_, "order_id": order_id, "status": status,
               "checks": checks, "aggregate": aggregate, "input_hash": input_hash_}
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
