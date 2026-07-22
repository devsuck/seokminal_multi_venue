"""Execution Risk 정책·컨텍스트 (P8.5) — 임계값 + 읽기전용 입력. 순수·결정적.

ExecutionRiskPolicy: 한도(포지션·노셔널·집중도·손실·드로다운·레버리지·회전율·연속실패).
RiskContext: 평가 시점의 읽기전용 관측값(주입 가능). 상태 게이트(kill/halt/emergency).
**어떤 상태도 변경하지 않음.**
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

from jarvis.execution_risk.models import FAILED, PASS, WARNING

_EPS = 1e-12


@dataclass(frozen=True)
class ExecutionRiskPolicy:
    max_position_size: float = 1_000_000.0
    max_notional: float = 10_000_000.0
    max_concentration: float = 0.35        # 단일 심볼 비중 상한(0..1)
    daily_loss_limit: float = 500_000.0    # 일 실현손실 한도(양수 크기)
    max_drawdown: float = 0.20             # 일 드로다운 한도(0..1)
    max_leverage: float = 1.0              # gross 레버리지 상한
    max_turnover: float = 5.0              # 일 회전율 상한
    max_consecutive_failures: int = 3      # 연속 집행 실패 상한
    warn_ratio: float = 0.8                # 한도×비율 초과 → WARNING

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RiskContext:
    """평가 시점 읽기전용 관측값. None이면 안전측(보수) 처리."""
    position_size: float | None = None
    notional: float | None = None
    concentration: float | None = None
    daily_realized_loss: float = 0.0       # 양수 = 손실 크기
    drawdown: float = 0.0                  # 0..1
    leverage: float = 0.0
    turnover: float = 0.0
    consecutive_failures: int = 0
    broker_healthy: bool = False           # 기본 미구성 → 불건전(honest CLOSED)
    market_fresh: bool = False             # 기본 미구성 → 스테일
    trading_halted: bool = False
    kill_switch: bool = False
    emergency_stop: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def grade_max(value: float, limit: float, warn_ratio: float) -> str:
    """상한 초과 → FAILED, 상한×비율 초과 → WARNING, 그 외 PASS."""
    if value > limit + _EPS:
        return FAILED
    if value > limit * warn_ratio + _EPS:
        return WARNING
    return PASS


def grade_gate(bad: bool) -> str:
    """이진 게이트: 위험상태(True) → FAILED, 아니면 PASS."""
    return FAILED if bad else PASS
