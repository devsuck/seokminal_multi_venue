"""Execution Simulation 자료형 (P7.5) — 가상 체결 기록. **집행 아님.**

READY ExecutionDecision → SimulatedOrder → SimulatedFill → ExecutionSimulationReport.
**SimulatedOrder는 주문이 아니다 — 가상(hypothetical) 체결 레코드일 뿐.**
결정적·읽기전용·재현가능. 브로커 없음·게이트웨이 없음·실자본 없음·포지션 변경 없음.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field

# 시뮬 결과 상태(집행 상태 아님)
SIMULATED = "SIMULATED"
REJECTED = "REJECTED"      # READY 아님 / 잘못된 수량
BLOCKED = "BLOCKED"        # 가격 없음

_EPS = 1e-9
_BPS = 10_000.0


@dataclass(frozen=True)
class SimulatedOrder:
    simulation_id: str
    intent_id: str
    symbol: str
    side: str                  # BUY | SELL | HOLD
    quantity: float
    reference_price: float
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class SimulatedFill:
    simulation_id: str
    fill_price: float
    filled_quantity: float
    slippage: float            # 단위당 가격 임팩트(fill − reference), 부호 포함
    fees: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ExecutionSimulationReport:
    simulation_id: str
    status: str                # SIMULATED | REJECTED | BLOCKED
    order: dict | None = None
    fill: dict | None = None
    assumptions: dict = field(default_factory=dict)
    hash: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def simulation_id(intent_id: str, created_at: str) -> str:
    return "SIM:" + hashlib.sha1(f"{intent_id}|{created_at}".encode()).hexdigest()[:12]


def apply_slippage(reference_price: float, side: str, slippage_bps: float) -> float:
    """BUY는 불리하게(비싸게), SELL은 불리하게(싸게). ideal fill = slippage 0."""
    factor = slippage_bps / _BPS
    if side == "BUY":
        return round(reference_price * (1.0 + factor), 8)
    if side == "SELL":
        return round(reference_price * (1.0 - factor), 8)
    return round(reference_price, 8)


def compute_fees(fill_price: float, quantity: float, fee_bps: float) -> float:
    """명목(체결가×수량)에 대한 수수료(bps)."""
    return round(abs(fill_price * quantity) * fee_bps / _BPS, 8)


def report_hash(simulation_id_: str, status: str, order: dict | None,
                fill: dict | None, assumptions: dict) -> str:
    payload = {"simulation_id": simulation_id_, "status": status,
               "order": order, "fill": fill, "assumptions": assumptions}
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str)
    return "sha256:" + hashlib.sha256(blob.encode()).hexdigest()[:16]
