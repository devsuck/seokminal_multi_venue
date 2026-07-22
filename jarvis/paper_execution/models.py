"""Paper Execution 자료형 (P6.2) — 시뮬레이션 체결만. 실주문/브로커 없음.

APPROVED+ALLOW 프로덕션 제안 → 시뮬 order/fill/position/PnL. 결정적·감사가능.
집행 게이트웨이 무호출. 라이브 아님.
"""
from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field

PAPER_CAPITAL = 10_000_000.0   # 페이퍼 포트폴리오 명목(고정). weight → 수량 환산 기준.
_EPS = 1e-9


@dataclass(frozen=True)
class PaperOrder:
    order_id: str
    proposal_id: str
    strategy_id: str
    side: str                  # BUY | SELL | HOLD
    target_weight: float
    quantity: float
    created_at: str
    status: str = "SIMULATED"  # 실행성 상태 없음(paper only)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PaperFill:
    fill_id: str
    order_id: str
    simulated_price: float
    quantity: float
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PaperPosition:
    strategy_id: str
    quantity: float
    average_price: float
    market_value: float
    unrealized_pnl: float
    realized_pnl: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class PaperExecutionReport:
    execution_id: str
    proposal_id: str
    orders_created: int
    fills_created: int
    positions_after: list
    portfolio_value: float
    pnl_summary: dict
    timestamp: str
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def zero_position(strategy_id: str) -> PaperPosition:
    return PaperPosition(strategy_id, 0.0, 0.0, 0.0, 0.0, 0.0)


def execution_id(proposal_id: str) -> str:
    return "PE:" + hashlib.sha1(proposal_id.encode()).hexdigest()[:12]


def order_id(proposal_id: str, strategy_id: str) -> str:
    return "PO:" + hashlib.sha1(f"{proposal_id}|{strategy_id}".encode()).hexdigest()[:12]


def fill_id(oid: str) -> str:
    return "PF:" + hashlib.sha1(oid.encode()).hexdigest()[:12]


def side_for(delta: float) -> str:
    if delta > _EPS:
        return "BUY"
    if delta < -_EPS:
        return "SELL"
    return "HOLD"


def target_weight_of(proposal: dict) -> float:
    """proposal.allocation에서 해당 전략 목표비중 추출."""
    alloc = proposal.get("allocation") or {}
    if not isinstance(alloc, dict):
        return 0.0
    strat = proposal.get("strategy")
    if strat in alloc:
        return float(alloc[strat])
    for k in ("target_weight", "weight"):
        if k in alloc:
            return float(alloc[k])
    return 0.0


def apply_fill(cur: PaperPosition, side: str, qty: float, price: float) -> PaperPosition:
    """결정적 포지션 회계. BUY=평단 갱신, SELL=실현손익, unrealized=체결가 기준."""
    q, avg, rpnl = cur.quantity, cur.average_price, cur.realized_pnl
    if side == "BUY":
        nq = q + qty
        navg = (q * avg + qty * price) / nq if nq > _EPS else 0.0
        nr = rpnl
    elif side == "SELL":
        sell = min(qty, q)
        nr = rpnl + sell * (price - avg)
        nq = q - sell
        navg = avg if nq > _EPS else 0.0
    else:
        nq, navg, nr = q, avg, rpnl
    return PaperPosition(
        strategy_id=cur.strategy_id, quantity=round(nq, 8), average_price=round(navg, 8),
        market_value=round(nq * price, 4), unrealized_pnl=round(nq * (price - navg), 4),
        realized_pnl=round(nr, 4))
