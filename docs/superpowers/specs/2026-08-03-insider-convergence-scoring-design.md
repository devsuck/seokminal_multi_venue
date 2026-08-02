# 내부자거래 컨버전스 스코어링 — 설계

## 배경

`/insider`는 DART(KR 공시), SEC Form4, 의회매매, 정부계약, 옵션 UOA(Alpaca) 다섯 개 소스를
탭으로 나열만 하는 "모니터"였다. 유저 피드백: "리스트만 보여주면 내가 어캐암. 정보 조합해서
나한테 정보를 집어넣어줘야지." — 같은 티커에 여러 독립 신호가 겹치는지 자동으로 잡아서
대시보드에 노출하고 알림까지 주는 컨버전스 스코어링 레이어를 얹는다.

참고 조사: `github.com/ShinMegamiBoson/OpenPlanter`(OSINT 지식그래프 툴, MIT)를 검토했으나
컨버전스/스코어링 로직 자체는 없어 재사용 불가 — 유일하게 건진 건 클릭 시 근거 원문을 보여주는
"소스 드로어" UI 패턴, 대시보드 설계에 반영.

## 목표 / 비목표

**목표**
- 같은 티커에 서로 다른 leg가 같은 방향(매수성/매도성)으로 겹치면 감지해 스코어 매기기
- 대시보드에 랭킹 노출 + 기존 토스트 알림 파이프라인으로 통지
- 새 외부 API 호출/수집기 없이 기존 leg 데이터만 재사용(순수 집계 레이어)

**비목표 (이번 스펙 범위 아님)**
- paper/live 자동매매 — 컨버전스 스코어가 실제 엣지 있는지 백테스트로 검증된 **다음에** 별도
  스펙으로 진행
- 가중치 튜닝 — v1은 leg 개수 카운트만, 임의 가중치 부여 안 함(과최적화 회피)
- 크로스마켓(KR↔US) 매칭 — 유니버스가 달라 스코프 밖
- gov-contracts를 스코어링 leg로 포함 — 티커 필드가 없어 정량 매칭 불가, 컨텍스트 배지로만 곁들임

## 방향 태깅

각 leg의 기존 `trade_type`/`type` 필드를 그대로 재사용, 새 필드 추가 없음.

| Leg | 값 | 방향 |
|---|---|---|
| DART 임원·주요주주(`get_executive_stock_changes`) | BUY | BULLISH |
| " | SELL | BEARISH |
| " | CANCELLATION(소각) | BULLISH |
| " | HOLD_REPORT, RIGHTS_ISSUE(무상증자) | 제외(중립) |
| DART 기업행위(`get_recent_kr_corporate_actions`) | BUYBACK | BULLISH |
| " | PAID_IN(유상증자), DISPOSAL(자사주처분) | BEARISH |
| " | RIGHTS_ISSUE | 제외 |
| SEC Form4(edgar_client) | BUY | BULLISH |
| " | SELL | BEARISH |
| 의회매매(congress_client) | BUY | BULLISH |
| " | SELL | BEARISH |
| " | OTHER | 제외 |
| Finnhub | BUY | BULLISH |
| " | SELL | BEARISH |
| 옵션 UOA | call | BULLISH |
| " | put | BEARISH |

## 스코어링 알고리즘

```
compute_convergence(market: "kr" | "us", days: int = 30) -> list[ConvergenceSignal]

1. market별 해당 leg 함수 전부 호출 (이미 각 탭이 쓰는 함수 그대로)
2. 각 row를 위 표로 방향 태깅, 제외 항목은 드롭
3. (ticker, direction) 키로 그룹핑
4. 그룹 안에서 leg 종류(서로 다른 함수 출처) 개수 = score
5. score < 2 인 그룹은 버림 (컨버전스 아님 — 단일 신호는 각 leg 탭에서 이미 보임)
6. score desc 정렬해서 반환
```

`ConvergenceSignal`:
```python
{
  "ticker": str,
  "market": "kr" | "us",
  "direction": "BULLISH" | "BEARISH",
  "score": int,               # 겹친 leg 개수
  "legs": [                   # 기여한 원본 이벤트들
    {"source": str, "trade_date": str, "detail": str, "url": str | None}
  ],
}
```

동일 (ticker, direction)에 leg가 여러 건(예: Form4 3건) 있어도 score는 **leg 종류 수**로 카운트
(같은 소스 반복은 컨버전스 강도 아님) — `legs` 배열엔 전부 나열해서 드로어에서 보여줌.

## API

`GET /insider/convergence?market=kr|us&days=30` — `list[ConvergenceSignal]` 반환.
새 엔드포인트 하나만 추가, 기존 leg 엔드포인트는 무변경.

## 알림 연동

새 폴링루프/봇 프로세스 안 만듦 — 기존 `/alerts/triggered`(`AlertPoller.tsx`가 이미 30초
간격으로 폴링 중) 응답에 컨버전스 이벤트를 합성 엔트리로 추가.

- `get_triggered_alerts()`가 `compute_convergence("kr")` + `compute_convergence("us")`를 호출해
  score≥2 신호를 기존 `TriggeredAlertsResponse` 형태로 변환해 합침
- `rule_id` = `f"insider-convergence:{market}:{ticker}:{direction}"` (AlertPoller의
  `seenIds` dedup이 이 키로 동작 — 같은 컨버전스가 반복 알림 안 뜸)
- `bot_id` 프리픽스 `"insider-convergence"` 신규 → `AlertPoller.tsx`의 `linkFor()`에 한 줄
  추가: `/insider?tab=convergence` 로 라우팅

## 대시보드 UI

`/insider`에 "🔥 컨버전스" 탭 신규.

- 스코어 desc 정렬 카드 리스트. 카드: 티커, 방향 뱃지(🟢상승/🔴하락), score 뱃지(2=주의/3+=강함,
  강도별 색상), 기여 leg 아이콘 나열
- 카드 클릭 → 드로어 오픈, `legs` 배열 각각을 날짜/공시명/원문링크로 표시 (OpenPlanter
  클릭-드로어 패턴)
- 기존 KR/US 마켓 탭과 별개 최상위 탭(마켓 안 가리고 컨버전스는 KR/US 결과를 함께 보여줌,
  카드 자체에 market 뱃지로 구분)

## 테스트 계획

`compute_convergence()`는 순수함수 — 각 leg를 mock row로 주입해 유닛테스트:
- 단일 leg만 있으면 score 미달로 결과 없음
- 2개 leg 같은 방향 → score=2 반환
- 2개 leg 다른 방향(예: Form4 BUY + 의회 SELL) → 컨버전스 아님(그룹 분리됨)
- 같은 leg 소스에서 여러 건 → score는 leg 종류 수로만 카운트(중복 안 셈)
- HOLD_REPORT/RIGHTS_ISSUE 등 제외 대상 태그는 그룹핑에서 빠짐
- gov-contracts는 애초에 `compute_convergence` 입력에 안 들어감(별도 확인 불필요, 호출 자체를 안 함)

## 변경 파일

- 신규: `insider/convergence.py`, `tests/test_convergence.py`
- 수정: `api_server/main.py` (`GET /insider/convergence` 신규, `get_triggered_alerts()`에
  컨버전스 병합)
- 수정(프론트, `seokminal-dashboard`): `lib/api.ts`(`getInsiderConvergence()` 신규),
  `app/insider/page.tsx`(컨버전스 탭+카드+드로어), `components/AlertPoller.tsx`(`linkFor()`
  라우팅 한 줄)
