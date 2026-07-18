"""Exact conditional simulation of Point processes: Application to pathwise market impact estimation (arXiv:2607.03239v1)
베끼기(counterfactual) 시뮬레이션 프레임워크: 주문북 이벤트(지정가/취소/시장가 주문)를 Hawkes 과정과 큐-반응(queue-reactive) 강도로 모델링하고, Poisson random measure thinning 표현을 이용해 관측된 이벤트 경로에 조건부인 잠재 노이즈의 분포를 정확히 특정한다. 이를 통해 동일한 시장 랜덤성 하에서 개입(수동/공격적 메타오더 실행) 유무에 따른 반사실적(counterfactual) 큐·가격 경로를 이벤트 기반으로 정확히 재구성하고, 실현 시장 환경에 조건부인 시장충격(market impact) 분포(평균/분산/분위수)를 계산한다. 트레이딩 매수/매도 시그널이 아니라 사후적 거래비용/시장충격 추정 및 실행전략 평가를 위한 조건부 시뮬레이션 방법론이다.
"""
NAME = "hawkes_qr_revert"
DESCRIPTION = "Hawkes 자기여기 강도로 임팩트 이벤트 감쇠 국면 탐지 후 VWAP 하방이탈 반전 매수"

def signal_fn(ohlc, feat, aux, params):
    import math
    c, vwap, mso, atr = ohlc["close"], feat["vwap"], feat["mso"], feat["atr_abs"]
    beta = params.get("decay_beta", 0.35)
    event_k = params.get("event_k", 1.2)
    dev_k = params.get("dev_k", 0.003)
    min_intensity = params.get("min_intensity", 0.5)
    orm = params.get("or_minutes", 30)

    n = len(c); entry = [False] * n; elig = []
    lam = 0.0
    prev_lam = 0.0
    for i in range(n):
        r = c[i] - c[i - 1] if i > 0 else 0.0
        lam *= math.exp(-beta)
        if atr[i] and abs(r) > event_k * atr[i]:
            lam += 1.0

        if not (mso[i] is not None and mso[i] >= orm and vwap[i] and atr[i]):
            prev_lam = lam
            continue
        elig.append(i)

        decaying = lam < prev_lam and lam >= min_intensity
        if decaying:
            dev = (c[i] - vwap[i]) / vwap[i]
            if dev < -dev_k:
                entry[i] = True

        prev_lam = lam

    return {"entry": entry, "eligible": elig}