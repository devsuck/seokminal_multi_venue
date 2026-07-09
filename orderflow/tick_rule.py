"""Lee-Ready 근사 체결 방향 분류. IBKR는 체결에 방향 필드가 없어 이걸로 판정한다.
Hyperliquid는 trades 페이로드에 buyer/seller가 있어 이 함수를 타지 않는다."""
from typing import Literal


def classify(price: float, bid: float, ask: float) -> Literal["buy", "sell"]:
    if price >= ask:
        return "buy"
    if price <= bid:
        return "sell"
    mid = (bid + ask) / 2
    return "buy" if price >= mid else "sell"
