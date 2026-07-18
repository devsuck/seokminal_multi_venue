"""Existence and convergence of discrete-time Kyle models with multiple insiders (arXiv:2607.15057v1)
Kyle형 다중 내부자 순차경매 모형. 각 내부자 i는 종목 최종가치 v(=Σa_i)에 대한 사적신호 a_i를 보유하고, 과거 체결가격(p_1,...,p_{n-1})으로부터 시장추정치(칼만필터 tˆ_{n-1})를 갱신하며, 매 라운드 주문량 Δθ_{i,n}=β_n(a_i - tˆ_{n-1})을 제출. 마켓메이커는 총주문흐름(내부자+노이즈트레이더)을 관측해 p_n=E[v|y_1,...,y_n]로 선형 가격설정(Δp_n=λ_nΔy_n). 시그널 자체는 '사적신호 - 시장합의추정치' 갭이며, β_n·λ_n·ζ_n 계수는 분산재귀식(Σ_n)의 해로 결정되고 거래라운드 수 N→∞ 시 연속시간 ODE(Back-Cao-Willard)로 수렴. 실전 적용 시 대리 시그널은 '누적 순주문흐름(order imbalance)이 시사하는 내부자 사적정보'와 실제가격의 괴리로 근사 가능.
"""
NAME = "kyle_multi_insider"
DESCRIPTION = "세션 누적 순매수 주문흐름과 VWAP-ATR 가격괴리 갭으로 미반영 사적정보 추정, 갭 양수시 롱 진입"

def signal_fn(ohlc, feat, aux, params):
    c, v = ohlc["close"], ohlc["volume"]
    sids, mso, vwap, atr = feat["sids"], feat["mso"], feat["vwap"], feat["atr_abs"]
    min_mso = params.get("min_mso", 15)
    imb_min = params.get("imb_min", 0.15)
    gap_min = params.get("gap_min", 0.3)
    imb_k = params.get("imb_k", 1.5)
    n = len(c)
    entry = [False] * n
    elig = []
    cum_flow = 0.0
    cum_vol = 0.0
    prev_sid = None
    prev_c = None
    for i in range(n):
        sid = sids[i]
        if sid != prev_sid:
            cum_flow = 0.0
            cum_vol = 0.0
            prev_c = None
            prev_sid = sid
        if prev_c is not None and v[i]:
            if c[i] > prev_c:
                sign = 1.0
            elif c[i] < prev_c:
                sign = -1.0
            else:
                sign = 0.0
            cum_flow += sign * v[i]
            cum_vol += v[i]
        prev_c = c[i]
        if not (sid is not None and mso[i] is not None and mso[i] >= min_mso and vwap[i] and atr[i] and cum_vol > 0):
            continue
        elig.append(i)
        order_imbalance = cum_flow / cum_vol
        price_gap = (c[i] - vwap[i]) / atr[i]
        signal = order_imbalance - price_gap / imb_k
        if order_imbalance > imb_min and signal > gap_min:
            entry[i] = True
    return {"entry": entry, "eligible": elig}