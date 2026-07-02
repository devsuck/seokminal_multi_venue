"""거래비용 모델 — 체결당 유효 bps.

기존 백테스트는 cost_bps 하나만 받음. 리서치에선 슬리피지·스프레드를 명시 분리해
effective_cost_bps로 합산 → 왕복 진입+청산 2회 차감(_simulate 계열과 동일 규약)."""
from __future__ import annotations


def effective_cost_bps(
    cost_bps: float = 0.0,
    slippage_bps: float = 0.0,
    spread_bps: float = 0.0,
) -> float:
    """체결 1회당 총 비용(bps) = 수수료 + 슬리피지 + 스프레드/2 왕복 근사.

    스프레드는 진입 시 절반, 청산 시 절반 부담 → 체결당 spread_bps/2.
    수수료·슬리피지는 체결당 그대로."""
    return float(cost_bps) + float(slippage_bps) + float(spread_bps) / 2.0
