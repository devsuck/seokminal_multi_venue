# v2 Shadow Hypotheses — 사전등록 개선 방향 (v1 동결)

> **원칙:** 공식 paper_candidate v1은 절대 건드리지 않는다. 모든 개선은 v2 shadow hypothesis로만
> 별도 사전등록·검증. 목표 = win rate 아니라 **expectancy · drawdown · capacity · forward stability**.

---

## TSMOM v1 (동결) → TSMOM v2 (shadow)

**v1 동결:** 32시장, 12개월 모멘텀, vol targeting, 월 리밸런스. `research/hypotheses/tsmom.py` DEFAULTS. paper forward-test 중.

**v2 목표:** 승률 개선 ❌ → **Sharpe / drawdown 개선** ⭕

**v2 우선순위 (사전정의):**
1. **장기 데이터 확보** — 현재 IB ContFuture 2.5~5년(캡). Norgate 등 20년+ = 진짜 검정.
2. **universe breadth 40~60 시장** — 13→32에서 엣지 안정화됨. 가장 정당한 개선 = 무상관 시장 추가(FX IDEALPRO, 더 많은 원자재/금리/국제지수). 사전정의 확장.
3. **레짐 스케일링 = 지금 넣지 말 것.** paper forward 관찰 후 별도 v2로만 테스트(과적합 위험).

**금지:** v1 파라미터 변경, 결과 보고 튜닝.

---

## KR Buyback v1 (동결, yellow) → Buyback v2 (shadow)

**v1 동결:** next_open 진입, HOLD 20d, cost 40bps. `research/paper/buyback_config.py`. status=paper_candidate_yellow.

**핵심 성질:** median edge 약함, **right-tail 의존.** → 승률 억지로 올리지 않는다.

**v2 목표:** win rate ❌ → **execution + risk control** ⭕ (expectancy·drawdown·capacity)

**v2 우선순위 (사전정의):**
1. **next_open 체결 인프라** — 다음날 시가 즉시 진입 실현 가능성(핵심 리스크=타이밍 민감, delayed_open p0.156 소멸).
2. **공시 timestamp 정확도** — rcept_dt 날짜만 → 장중/장후 구분, 진입 현실성.
3. **동시 보유 분산 · issuer 중복 제한** — 팻테일 의존이라 분산 필수, 한 종목/발행사 몰빵 금지.
4. **위험종목 제거** — 관리종목·정리매매·거래정지 제외 강화.

**금지 v2:** size/purpose 필터 — clean gradient 없음(분해 결과 median 0근처). 만들지 않는다.

### ✅ v2 신규 사전등록: 레짐 필터 (2026-07-03, `kr_buyback_v2_regime_shadow`)
**경제가설(사전):** 경영진이 하락장(공포)에 자사주 매입 = 저평가 신호 신뢰성↑. 상승장 매입 = 현금관리(무의미).
**검증 결과 (in-sample, 확인):** 상승장 제외 시 net +1.72%→+2.52%, 승률 50.9%→54.8%, vs random p=0.032→**0.01**, WF 전0.92%/후4.11%(강화), stress50 +1.92%. 제외된 상승장 = +0.12%·승률43%(죽은 이벤트).
**규칙:** 이벤트일 시장 60일 수익 상위 1/3(상승장) 제외 → 하락+중립만 진입. 레짐신호 = KOSPI/KOSDAQ 지수 60일수익(실시간 가능).
**상태:** shadow. **v1 동결 유지. forward 검증 전 live·paper_candidate 승격 금지.** size/purpose 아님(경제 gradient 있음) → 허용.
**주의:** in-sample tercile 선택 여지 있음 → forward/holdout에서 재현돼야 신뢰. `research/run_buyback_v2.py`.

---

## 공통
- v1 성과 나빠도 v1 건드리지 않는다. v2는 별도 hypothesis_id로 사전등록 후 forward/holdout 검증.
- 목표 지표: expectancy(평균 기대값) · max drawdown · capacity(자본 수용력) · forward stability. NOT win rate.
