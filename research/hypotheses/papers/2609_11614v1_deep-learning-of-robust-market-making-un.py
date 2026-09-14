"""Deep Learning of Robust Market Making under Regime-Switching Order Flow (arXiv:2609.11614v1)
GLFT 벤치마크 및 이를 능가하는 분산형 Deep Q-Network(C51, Rainbow-DQN) 기반 마켓메이킹 정책. 상태는 스프레드, 매수/매도 호가별 큐 depth(offset 0~K), 부호 있는 재고(inventory), 라이브 주문 지표로 구성. 정상 상태에서는 여기까지만 사용하고, 레짐 전환 국면에서는 두 보조 시그널을 추가: (1) 시장가 주문 흐름의 방향성 편향에 대한 베이지안 온라인 체인지포인트 필터(posterior 매수확률 기반 flow bias ι, 기대 run length), (2) 자기 호가의 큐 위치 기반 노출 불균형(quote-exposure imbalance, 매수/매도 호가 각각 살아있는지와 앞선 큐 수량으로 계산). 1초 throttle마다 6개 이산 행동(틱 단위 매수/매도 오퍼셋 조합, 예: (0,0),(-1,0),(0,-1) 등) 중 하나를 선택해 best bid/ask 대비 오퍼셋으로 지정가를 재게시하며, 재고가 상한에 닿으면 해당 방향 주문을 자동 차단(inventory gating)한다. 보상은 체결 PnL에서 재고 제곱 페널티와 소프트 재고벽(inventory-wall) 페널티를 차감한 값. 레짐 강건성은 저수익 시나리오를 업웨이트하는 scenario-bandit 파인튜닝으로 추가 개선.
"""
NAME = "flowbias_vwap_meanrev"
DESCRIPTION = "VWAP 하방이탈 + 단기 모멘텀 반전(체인지포인트 근사 flow bias) 매수"

def signal_fn(ohlc, feat, aux, params):
    c = ohlc["close"]
    vwap, mso, atr = feat["vwap"], feat["mso"], feat["atr_abs"]
    dev_k = 0.003
    short_w = 5
    long_w = 20
    n = len(c)
    entry = [False] * n
    elig = []
    for i in range(n):
        if i < long_w:
            continue
        if not (mso[i] is not None and mso[i] >= 15 and vwap[i] and atr[i]):
            continue
        elig.append(i)
        dev = (c[i] - vwap[i]) / vwap[i]
        short_ret = c[i] - c[i - short_w]
        long_ret = c[i] - c[i - long_w]
        flow_bias = 1 if (short_ret > 0 and long_ret < 0) else (-1 if (short_ret < 0 and long_ret > 0) else 0)
        if dev < -dev_k and flow_bias >= 0:
            entry[i] = True
    return {"entry": entry, "eligible": elig}