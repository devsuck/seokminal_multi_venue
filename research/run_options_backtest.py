"""옵션 백테스트: 내부자 매수 공시 + ATM 콜 오버레이 vs 직접 주식 매수.

전략 A: 공시일 D+1 주식 직접 매수, 20일 보유 (Form 4 기준선)
전략 B: 같은 이벤트에서 ATM 콜 옵션 매수 (Black-Scholes 이론가 사용)

가정:
- ATM 콜: 행사가 = 진입일 종가, 만기 = 30일 (D+1+30)
- 이론가: Black-Scholes, 무위험이율 4.5%, IV = 역사적 20일 실현변동성
- 만기 시 콜 payoff = max(0, S_T - K)
- 콜 레버리지 효과와 프리미엄 소멸 리스크 비교

결과: 동일 자본 $1 투자 기준 기대 수익 비교

CLI: PYTHONPATH=. python3 research/run_options_backtest.py
"""
from __future__ import annotations

import bisect
import math
import statistics as _st

HOLD_DAYS = 20
OPTION_EXPIRY_DAYS = 30
COST_BPS_STOCK = 5
COST_BPS_OPTION = 20   # 옵션 거래 비용 (bid-ask spread 등)
RISK_FREE = 0.045      # 연 4.5%
HV_WINDOW = 20         # 역사적 변동성 계산 윈도우


# ── Black-Scholes ──────────────────────────────────────────────────────────
def _bs_call(S: float, K: float, T: float, r: float, sigma: float) -> float:
    """BS ATM 콜 이론가. T = 연환산 만기."""
    if sigma <= 0 or T <= 0:
        return max(0.0, S - K)
    d1 = (math.log(S / K) + (r + 0.5 * sigma**2) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    return S * _Phi(d1) - K * math.exp(-r * T) * _Phi(d2)


def _Phi(x: float) -> float:
    return 0.5 * math.erfc(-x / math.sqrt(2))


# ── 가격 시리즈 유틸 ───────────────────────────────────────────────────────
def _price_series(ticker: str) -> dict | None:
    try:
        import yfinance as yf
        df = yf.download(ticker, start="2020-01-01", auto_adjust=True, progress=False)
        if df.empty or len(df) < 40:
            return None
        cols = df.columns
        if hasattr(cols, "levels"):
            opens = df[("Open", ticker)].values
            closes = df[("Close", ticker)].values
        else:
            opens = df["Open"].values
            closes = df["Close"].values
        return {
            "dates": [d.strftime("%Y-%m-%d") for d in df.index],
            "open": [float(x) for x in opens],
            "close": [float(x) for x in closes],
        }
    except Exception:
        return None


def _hv(bars: dict, idx: int, window: int = HV_WINDOW) -> float:
    """idx 기준 과거 window일 일간 로그수익률 실현변동성 (연환산)."""
    start = max(0, idx - window - 1)
    closes = bars["close"][start:idx + 1]
    if len(closes) < 5:
        return 0.25  # 기본값 25%
    log_rets = [math.log(closes[i] / closes[i - 1]) for i in range(1, len(closes))]
    try:
        sigma_daily = _st.stdev(log_rets)
    except Exception:
        return 0.25
    return sigma_daily * math.sqrt(252)


# ── 전략 수익 계산 ─────────────────────────────────────────────────────────
def _stock_ret(bars: dict, event_date: str) -> float | None:
    """전략 A: 직접 주식 매수 수익."""
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None
    entry = bars["open"][i]
    xi = min(i + HOLD_DAYS, len(bars["dates"]) - 1)
    if entry <= 0 or xi < i + HOLD_DAYS:
        return None
    raw = bars["close"][xi] / entry - 1
    return raw - COST_BPS_STOCK / 10_000.0


def _option_ret(bars: dict, event_date: str) -> float | None:
    """전략 B: ATM 콜 매수 수익 ($1 자본 기준).
    - 콜 1계약 가격 = BS 이론가
    - 만기(+30일) 시 payoff = max(0, S_T - K)
    - 수익 = (payoff - premium) / premium — 자본 $1 대비 정규화
    """
    j0 = bisect.bisect_right(bars["dates"], event_date) - 1
    i = j0 + 1
    if j0 < 0 or i >= len(bars["dates"]):
        return None

    S = bars["open"][i]   # 진입일 시가 = strike
    K = S
    if S <= 0:
        return None

    sigma = _hv(bars, j0)
    T = OPTION_EXPIRY_DAYS / 365.0
    premium = _bs_call(S, K, T, RISK_FREE, sigma)
    if premium <= 0:
        return None

    xi = min(i + OPTION_EXPIRY_DAYS, len(bars["dates"]) - 1)
    if xi < i + OPTION_EXPIRY_DAYS:
        return None

    S_T = bars["close"][xi]
    payoff = max(0.0, S_T - K)
    cost = COST_BPS_OPTION / 10_000.0 * premium
    # $1 투자 기준: $1 / premium * payoff - 1
    return (payoff - premium - cost) / premium


def main():
    print("=" * 65)
    print("옵션 vs 직접 주식 — 내부자 매수 이벤트 백테스트")
    print("=" * 65)
    print(f"전략A: 주식 D+1 진입, {HOLD_DAYS}일 보유, {COST_BPS_STOCK}bps 비용")
    print(f"전략B: ATM 콜 D+1 매수, {OPTION_EXPIRY_DAYS}일 만기, {COST_BPS_OPTION}bps 비용")
    print(f"  콜 이론가: Black-Scholes, IV=과거{HV_WINDOW}일 실현변동성, r={RISK_FREE:.1%}")

    from research.data.openinsider import load_events
    events = load_events(min_date="2022-01-01")
    print(f"\n이벤트 로드: {len(events)}건")

    _cache: dict[str, dict | None] = {}
    for e in events:
        t = e["ticker"]
        if t not in _cache:
            _cache[t] = _price_series(t)

    a_rets: list[float] = []
    b_rets: list[float] = []
    matched: list[tuple[float, float]] = []  # (a, b) paired

    for e in events:
        bars = _cache.get(e["ticker"])
        if bars is None:
            continue
        ra = _stock_ret(bars, e["disclosure_date"])
        rb = _option_ret(bars, e["disclosure_date"])
        if ra is not None:
            a_rets.append(ra)
        if rb is not None:
            b_rets.append(rb)
        if ra is not None and rb is not None:
            matched.append((ra, rb))

    print(f"\n[전략 A — 직접 주식 매수]")
    if a_rets:
        print(f"  n={len(a_rets)}  median={_st.median(a_rets):+.4f} ({_st.median(a_rets)*100:+.2f}%)")
        print(f"  mean={_st.mean(a_rets):+.4f}  win={sum(1 for x in a_rets if x>0)/len(a_rets):.3f}")
    else:
        print("  데이터 없음")

    print(f"\n[전략 B — ATM 콜 매수 ($1 자본 기준)]")
    if b_rets:
        print(f"  n={len(b_rets)}  median={_st.median(b_rets):+.4f} ({_st.median(b_rets)*100:+.2f}%)")
        print(f"  mean={_st.mean(b_rets):+.4f}  win={sum(1 for x in b_rets if x>0)/len(b_rets):.3f}")
        loss_pct = sum(1 for x in b_rets if x <= -0.99) / len(b_rets)
        print(f"  전액손실(>99% 손) 비율: {loss_pct:.3f}")
    else:
        print("  데이터 없음")

    if matched:
        matched_a = [x[0] for x in matched]
        matched_b = [x[1] for x in matched]
        print(f"\n[동일 이벤트 비교 n={len(matched)}]")
        a_better = sum(1 for a, b in matched if a > b)
        b_better = sum(1 for a, b in matched if b > a)
        print(f"  A > B: {a_better/len(matched):.2%}  B > A: {b_better/len(matched):.2%}")

    print(f"\n[결론]")
    if b_rets and a_rets:
        b_med = _st.median(b_rets)
        a_med = _st.median(a_rets)
        if b_med > a_med + 0.10:
            print("  콜 옵션이 직접 주식보다 레버리지 효과로 유의미하게 우위")
            print("  단: 높은 변동성 + 프리미엄 소멸 리스크 내포")
        elif b_med < 0:
            print("  콜 옵션 median 음수 — 프리미엄 소멸이 레버리지 이익 압도")
            print("  직접 주식 매수 우위 (또는 longer-term 내부자 signal과 단기 옵션 만기 미스매치)")
        else:
            print("  콜 옵션 vs 주식: 비슷한 기대 수익. 변동성 크게 다름.")
    print("  주의: BS 이론가 사용, 실제 bid-ask spread/유동성 미반영")
    print("=" * 65)


if __name__ == "__main__":
    main()
