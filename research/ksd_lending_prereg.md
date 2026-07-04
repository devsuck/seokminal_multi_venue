# KSD 대차잔고 × 이벤트 상호작용 — 사전등록 (동결 2026-07-04)

> **동결 시점: 이벤트-대차 결합 데이터를 한 번도 보기 전.**
> KSD API 가용성/커버리지 프로브(삼성전자 + 소형주 5종 totalCount)만 수행, 수익률과 결합한 적 없음.
> 결과 본 뒤 기준 변경 금지. 변경하려면 v2로 재등록.

## 데이터

- 원천: data.go.kr `GetStocLendBorrInfoService_V2/getStItemLendAndBorrStatu_V2` (KSD 대차현황)
- 필드: `lnbRmanStckCnt`(대차잔여주식수 = 잔고), 커버리지 2008~현재, 종목별 전 히스토리
- 대차잔고비율 = lnbRmanStckCnt ÷ LIST_SHRS(KRX PIT 스냅샷, 같은 날짜)
- **PIT 규율: 공시일 D 기준 D−2 영업일 잔고 사용** (공개 지연 보수적 가정)

## 가설 (3개, 전부 사전등록)

### H1 — 스퀴즈 연료: buyback × 高대차
공시 전(D−2) 대차잔고비율 상위 1/3 buyback 이벤트가 하위 1/3보다 20일 드리프트 강함.
근거: 자사주 취득 = 유통공급↓, 기존 숏은 커버 압력 → 수요 충격 증폭.
- 예측(방향 고정): net(top tercile) − net(bottom tercile) > 0, top tercile이 매칭 random 이김(pct≥95, p<0.05).

### H2 — 공시 후 숏 반응이 지속을 예측
buyback 공시 후 D0..D+5 대차잔고 변화율 하위 1/3(커버링/감소)의 D+6..D+20 수익 > 상위 1/3(숏 증가).
근거: 숏이 물러나면 공급충격 순방향 지속, 숏이 맞서면 정보 있는 반대 베팅.
- 진입 D+6 시가 / 청산 D+20 종가 (관찰창과 보유창 분리 = lookahead 없음), 비용 40bps.
- 예측: net(Δ하위) − net(Δ상위) > 0.

### H3 — 처분 거울상: treasury_disposal × 高대차
자사주 처분(음드리프트, 2026-07-04 스캐너 확인 net −1.91%) 중 D−2 대차잔고비율 상위 1/3이 하위 1/3보다 더 음수.
근거: 숏 연료 있는 상태의 공급충격 = 하방 증폭.
- 예측: net(top tercile) − net(bottom tercile) < 0.

## 판정 기준 (동결)

- 하네스 동일: 익일시가 진입(H2만 D+6), HOLD 20(H2는 D+6..D+20), 비용 40bps base / 100bps stress, 매칭 random N=500, WF 전/후반.
- tercile당 **n ≥ 100** 미만 = UNDERPOWERED (판단 보류, 결과 봉인).
- 3개 primary 예측에 **BH-FDR α=0.1** (tercile 차이 p = 부트스트랩 1000회 단측).
- candidate 승격 = BH 생존 + 방향 일치 + WF 양쪽 방향 일치 + stress에서 부호 유지.
- **v1 불변.** 어떤 결과든 kr_dart_buyback_drift_v1 동결 config·arm_criteria_v1 안 건드림.
  통과 시 → 별도 v2 shadow 사전등록으로만 진행.

## 산출물

- 데이터: `research/data/ksd_lending.py` → `data/kr_lending/{code}.parquet`
- 러너: `research/run_buyback_x_lending.py` (H1·H2·H3 한 번에, BH-FDR 동시)
- 결과는 experiment_registry에 기록 (candidate/rejected/underpowered).
