"""A Limit Order Market with Uncertain Informed Trading Participation (arXiv:2607.04221v1)
이론적 마켓 마이크로스트럭처 모델. informed trader 수가 확률적(랜덤)이라 유동성 공급자가 존재 여부/강도를 모르는 상황에서, 균형 한계비용함수 F(주문크기별 marginal price)가 fixed-point 적분방정식으로 결정됨. 대량주문 극한에서 가격충격은 자산가치 tail 분포와 informed trader 수 분포에 동시에 의존하는 지수를 갖는 power law(자산가치가 bounded+power-law endpoint일 때) 또는 log형태(light-tail일 때)를 따름. 트레이딩 적용: 실측 LOB depth/주문크기별 체결가격 곡선을 관측해 그 tail 지수를 추정하면, 시장이 내재적으로 가정하는 informed trading 강도·불확실성 수준을 역산할 수 있고, 이를 바탕으로 대량주문 실행비용(마켓임팩트) 예측 및 주문분할(execution) 최적화 시그널로 활용 가능. 직접적 매수/매도 알파 시그널이 아니라 가격충격/유동성 구조 추정 모델.
"""
NAME = "tail_impact_revert"
DESCRIPTION = "세션내 impact/volume 힐추정 tail exponent 급강 + VWAP하방괴리 시 반등매수"

import math

def signal_fn(ohlc, feat, aux, params):
    c, v = ohlc["close"], ohlc["volume"]
    vwap, mso, atr, sids = feat["vwap"], feat["mso"], feat["atr_abs"], feat["sids"]
    win = params.get("window", 30)
    k = params.get("hill_k", 8)
    alpha_max = params.get("alpha_max", 2.5)
    z_min = params.get("z_min", 2.0)
    dev_k = params.get("dev_k", 0.002)

    n = len(c)
    entry = [False] * n
    elig = []

    impact = [None] * n
    for i in range(1, n):
        if c[i] is None or c[i - 1] is None or v[i] is None:
            continue
        vol = v[i]
        if vol <= 0:
            continue
        impact[i] = abs(c[i] - c[i - 1]) / vol

    for i in range(n):
        if not (mso[i] is not None and mso[i] >= 30 and vwap[i] and atr[i]):
            continue
        if i < win or impact[i] is None:
            continue
        window_vals = [impact[j] for j in range(i - win, i) if impact[j] is not None and sids[j] == sids[i]]
        if len(window_vals) < k + 1:
            continue
        elig.append(i)

        sorted_vals = sorted(window_vals, reverse=True)
        xk1 = sorted_vals[k]
        if xk1 <= 0:
            continue
        top = sorted_vals[:k]
        s = sum(math.log(x / xk1) for x in top)
        if s <= 0:
            continue
        alpha_hat = k / s

        mean_w = sum(window_vals) / len(window_vals)
        if mean_w <= 0:
            continue
        z = impact[i] / mean_w
        dev = (c[i] - vwap[i]) / vwap[i]

        if alpha_hat < alpha_max and z >= z_min and dev < -dev_k:
            entry[i] = True

    return {"entry": entry, "eligible": elig}