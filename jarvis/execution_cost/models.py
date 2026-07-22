"""Execution Cost 자료형 (P8.4) — 집행 '비용' 회계만. **집행 아님.**

ExecutionExpectation + BrokerFill/ReconciledFill → CostAccountingEngine →
ExecutionCostReport(EXPECTED/WARNING/FAILED). 체결 후 실제 집행비용 측정.
**주문 없음·브로커 호출 없음·포지션 변경 없음.** 결정적·읽기전용·재현가능·해시체인.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

EXPECTED = "EXPECTED"
WARNING = "WARNING"
FAILED = "FAILED"

GENESIS = "GENESIS"

_BPS = 10_000.0
_EPS = 1e-12


@dataclass(frozen=True)
class ExecutionCostInput:
    order_id: str
    symbol: str
    side: str                  # BUY | SELL
    quantity: float
    expected_price: float
    fill_price: float          # 다중체결 시 수량가중평균가
    gross_value: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class CostRates:
    commission_rate: float = 0.0      # gross 대비 비율
    exchange_fee_rate: float = 0.0    # gross 대비 비율
    fx_rate_cost: float = 0.0         # gross 대비 비율
    market_impact_rate: float = 0.0   # gross 대비 비율(있으면)


@dataclass(frozen=True)
class CostThresholds:
    expected_cost_bps: float = 10.0   # 기대 집행비용(bps)
    warning_multiplier: float = 1.5   # 기대×배수 이하 = EXPECTED
    failure_multiplier: float = 3.0   # 기대×배수 초과 = FAILED


@dataclass(frozen=True)
class CostComponents:
    commission: float
    exchange_fee: float
    spread_cost: float
    slippage_cost: float
    market_impact_cost: float
    fx_cost: float
    total_cost: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionCostReport:
    report_id: str
    order_id: str
    gross_value: float
    cost_components: dict = field(default_factory=dict)
    total_cost: float = 0.0
    cost_bps: float = 0.0
    expected_cost_bps: float = 0.0
    variance_bps: float = 0.0
    status: str = EXPECTED
    input_hash: str = ""
    report_hash: str = ""
    timestamp: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def report_id(order_id: str, input_hash_: str) -> str:
    return "ECR:" + hashlib.sha1(f"{order_id}|{input_hash_}".encode()).hexdigest()[:12]


def input_hash(inp: dict, rates: dict, mid_price: float, thresholds: dict) -> str:
    blob = json.dumps({"input": inp, "rates": rates, "mid_price": mid_price,
                       "thresholds": thresholds}, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]


def report_hash(report_id_: str, order_id: str, cost_components: dict, total_cost: float,
                cost_bps: float, expected_cost_bps: float, variance_bps: float,
                status: str, input_hash_: str) -> str:
    payload = {"report_id": report_id_, "order_id": order_id,
               "cost_components": cost_components, "total_cost": total_cost,
               "cost_bps": cost_bps, "expected_cost_bps": expected_cost_bps,
               "variance_bps": variance_bps, "status": status, "input_hash": input_hash_}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
