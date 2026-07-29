"""Post-Trade Analytics 자료형 (P8.7) — 완료된 집행의 사후 분석(TCA)만. **분석 전용.**

Lifecycle(P8.2)+Reconciliation(P8.3)+Cost(P8.4)+Audit(P8.6) → TCA/품질/벤치마크 리포트 +
PortfolioExecutionSummary. **거래를 승인하지 않는다.** 읽기전용·결정적·재현가능·해시체인.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

PASS = "PASS"
WARNING = "WARNING"
FAILED = "FAILED"

GENESIS = "GENESIS"

_ORDER = {PASS: 0, WARNING: 1, FAILED: 2}


@dataclass(frozen=True)
class ExecutionData:
    """분석 입력(완료된 집행). 읽기전용 스냅샷."""
    request_id: str
    symbol: str = ""
    side: str = ""                     # BUY | SELL
    order_quantity: float = 0.0
    fills: list = field(default_factory=list)   # [{quantity, fill_price, fee, timestamp}]
    arrival_price: float | None = None          # 필수 벤치마크
    decision_price: float | None = None
    close_price: float | None = None
    mid_price: float | None = None
    future_mid_price: float | None = None
    market_volume: float | None = None
    cost_components: dict = field(default_factory=dict)
    start_time: str = ""
    end_time: str = ""
    broker: str = ""
    strategy: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PostTradeReport:
    report_id: str
    request_id: str
    timestamp: str
    report_type: str                   # TCA | QUALITY | BENCHMARK
    overall_status: str                # PASS | WARNING | FAILED
    overall_score: float = 0.0
    benchmarks: dict = field(default_factory=dict)
    metrics: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)
    errors: list = field(default_factory=list)
    input_hash: str = ""
    report_hash: str = ""
    previous_hash: str = GENESIS

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PortfolioExecutionSummary:
    summary_id: str
    period: str                        # daily | weekly | monthly
    timestamp: str
    n_trades: int = 0
    average_cost_bps: float = 0.0
    median_cost_bps: float = 0.0
    worst_trade: dict = field(default_factory=dict)
    best_trade: dict = field(default_factory=dict)
    average_slippage_bps: float = 0.0
    average_fill_quality: float = 0.0
    execution_success_rate: float = 0.0
    cost_by_broker: dict = field(default_factory=dict)
    cost_by_symbol: dict = field(default_factory=dict)
    cost_by_strategy: dict = field(default_factory=dict)
    input_hash: str = ""
    report_hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


# 명명된 리포트 타입(사양 API) — 공통 PostTradeReport 사용
TransactionCostAnalysisReport = PostTradeReport
ExecutionQualityReport = PostTradeReport
ExecutionBenchmarkReport = PostTradeReport


def overall_status(statuses: list) -> str:
    """any FAILED → FAILED, else any WARNING → WARNING, else PASS."""
    worst = PASS
    for s in statuses:
        if _ORDER.get(s, 0) > _ORDER[worst]:
            worst = s
    return worst


def report_id(request_id: str, report_type: str, input_hash_: str) -> str:
    return "PTA:" + hashlib.sha1(
        f"{request_id}|{report_type}|{input_hash_}".encode()).hexdigest()[:12]


def summary_id(period: str, input_hash_: str) -> str:
    return "PES:" + hashlib.sha1(f"{period}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(payload: dict) -> str:
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_hash(report_id_: str, request_id: str, report_type: str, status: str,
                score: float, benchmarks: dict, metrics: dict, input_hash_: str) -> str:
    payload = {"report_id": report_id_, "request_id": request_id, "report_type": report_type,
               "overall_status": status, "overall_score": score,
               "benchmarks": benchmarks, "metrics": metrics, "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
