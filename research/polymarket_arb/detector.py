"""합가격 차익거래 판정 — 순수함수, I/O 없음. collector.py가 오더북에서
best ask를 뽑아 여기 넘긴다."""
from __future__ import annotations


def evaluate_snapshot(yes_ask: float, no_ask: float, fee_buffer: float = 0.01) -> dict:
    """YES ask + NO ask 합가격 계산 후 차익기회 여부 판정.

    fee_buffer: 수수료/가스비 감안 버퍼(기본 1%) — sum_ask가 (1 - fee_buffer)
    미만이어야 기회로 카운트한다.
    """
    sum_ask = round(yes_ask + no_ask, 4)
    return {"sum_ask": sum_ask, "is_opportunity": sum_ask < (1.0 - fee_buffer)}
