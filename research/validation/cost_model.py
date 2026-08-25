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


# ── Hyperliquid perps 전용 ──────────────────────────────────────────────────
# 기본 티어: taker 0.045%=4.5bps, maker 0.015%=1.5bps. 주식(5bps)보다 높음.
HL_TAKER_BPS = 4.5
HL_MAKER_BPS = 1.5

# 유동성 버킷별 슬리피지·스프레드(bps) — 알트일수록 보수적.
HL_SLIPPAGE_BUCKET = {"major": 1.0, "mid": 3.0, "alt": 8.0}
HL_SPREAD_BUCKET = {"major": 1.0, "mid": 4.0, "alt": 10.0}


def hl_effective_cost_bps(
    liquidity: str = "major",
    taker: bool = True,
) -> float:
    """HL 체결 1회당 유효 비용(bps). funding cashflow는 별도(여기 미포함).

    ⚠️ trading cost(진입/청산) ≠ funding(보유 중 수취/지급). 절대 섞지 말 것."""
    fee = HL_TAKER_BPS if taker else HL_MAKER_BPS
    slip = HL_SLIPPAGE_BUCKET.get(liquidity, HL_SLIPPAGE_BUCKET["alt"])
    spread = HL_SPREAD_BUCKET.get(liquidity, HL_SPREAD_BUCKET["alt"])
    return fee + slip + spread / 2.0


# ── IB CME futures 전용 ──────────────────────────────────────────────────
# ⚠️ 미검증 근사치 — IB 실제 요금표(계약당 왕복 커미션) 대조 안 됨.
# 페이퍼 단계 진입 전 반드시 IB 계정 실요율로 재확인할 것.
IB_FUTURES_COMMISSION_USD = {"NQ": 2.25, "MNQ": 0.55, "GC": 2.25}  # 계약당 왕복 근사
IB_FUTURES_TICK_VALUE_USD = {"NQ": 5.0, "MNQ": 0.5, "GC": 10.0}    # NQ/MNQ: CME 0.25pt당, GC: COMEX 0.10pt당(100oz)
IB_FUTURES_SLIPPAGE_TICKS = {"NQ": 0.5, "MNQ": 1.0, "GC": 0.5}     # MNQ 유동성 낮아 더 보수적


def ib_futures_effective_cost_bps(symbol: str, notional: float) -> float:
    """IB 선물 체결 1회당 유효 비용(bps) = (커미션 + 슬리피지) / notional * 10000.

    notional은 호출부에서 계약가치(price * multiplier)로 넘겨야 한다.
    ⚠️ 커미션/슬리피지 상수는 미검증 근사치."""
    commission = IB_FUTURES_COMMISSION_USD[symbol]
    slippage = IB_FUTURES_SLIPPAGE_TICKS[symbol] * IB_FUTURES_TICK_VALUE_USD[symbol]
    return round((commission + slippage) / notional * 10_000.0, 6)
