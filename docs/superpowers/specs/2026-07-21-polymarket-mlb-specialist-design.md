# Polymarket MLB 스페셜리스트 컨센서스 — Design Spec

**작성:** 2026-07-21. 브레인스토밍 확정, 사용자 승인 대기.

## 1. 배경

폴리마켓에 MLB만 전문으로 파는 수익 지갑(예: `@bolinger-`)이 존재한다. 일반
whale/컨버전스 추종("샤프월렛 아무나 몰리면 신호")은 "왜 돈 버는지" 스토리가 약한
반면, **카테고리 특화 지갑 추종은 도메인 엣지**(선발 매치업·부상·불펜 등 시장보다
나은 정보)라는 명확한 근거가 있다.

MLB를 택한 이유: (1) 스포츠 중 유동성 상위, (2) **매일 경기 → 당일 정산** = 표본이
빠르게 쌓여 통계 검정에 힘이 붙음(기존 폴리마켓 트랙의 최대 약점인 "표본 부족" 해소).
KBO/NPB는 유동성 부족, NBA/NFL은 7월 오프시즌, 그 외는 서브 후보로 보류.

기존 다각화 봇은 **접지 않고 무엣지 베이스라인(대조군)으로 병행 유지** — "스페셜리스트
컨센서스가 무방향 다각화보다 유의하게 나은가"가 판정 기준이 된다. 이 트랙은 다각화를
줄이는 게 아니라 **추가 서브 트랙**이다.

## 2. 목적 및 범위

**수집 + 검증(스크리닝) 전용.** 라이브 실집행·알림 없음(house 규율: 검증 전 페이퍼).
MLB 단일. 상수는 설계 시점 고정.

**포함:** MLB 마켓 식별 → 지갑별 MLB 성적 집계(bottom-up) → 3지표 스페셜리스트 랭킹
(walk-forward) → 컨센서스 신호(파라미터화) → BH-FDR 검증 vs 다각화 베이스라인.

**제외:** 라이브 집행/알림, 비-MLB 스포츠, 인앱 UI(검증 통과 후 별도 — 기존 p-value
노출 패턴 재사용). walk-forward 표본기간 미달 시 승격 보류.

## 3. 핵심 설계

### 3.1 스페셜리스트 유니버스 — bottom-up
글로벌 `/trades` 피드(기존 whale/샤프 수집기 패턴)를 **MLB 마켓으로 필터**해 축적.
MLB에서 활동하는 모든 지갑을 후보로 삼는다(전체 리더보드에 없어도 됨 — 순수 MLB러 포착).

### 3.2 지갑별 MLB 성적 → 3지표 랭킹 (Q2)
각 지갑의 **정산된** MLB 베팅(진입가 + 경기결과)으로 계산:
- `mlb_pnl` — MLB 실현손익 합(절대 $)
- `mlb_winrate` — MLB 베팅 승률
- `mlb_roi` — MLB 투입액 대비 수익률
- `mlb_specialization` — MLB 거래량 / 전체 거래량(순수도)
- `mlb_n` — 정산된 MLB 베팅 수(신뢰 게이트)

**게이트:** `mlb_n ≥ MIN_BETS` AND `mlb_specialization ≥ MIN_SPEC`. 통과한 지갑을
**세 지표별로 각각 랭크 → 상위 N명 = 3개 스페셜리스트 세트**(pnl판/winrate판/roi판).
데이터가 "어느 지표가 진짜 예측력 있는 스페셜리스트를 잡나"를 답하게 한다.

### 3.3 walk-forward 선정 (생존편향 방지 — 핵심)
스페셜리스트 명단은 **매일**, 그 시점까지의 이력(시즌 누적)으로만 재선정. 선정 *이후*
발생한 컨센서스 신호만 검증 대상 — 미래 정보로 승자 뽑는 look-ahead 원천 차단.

### 3.4 컨센서스 신호 (파라미터화)
특정 오픈 MLB 마켓에서, 그 마켓에 포지션 잡은 스페셜리스트 중:
- 최소 `MIN_PRESENT`명 이상이 그 마켓에 있고 (예: 5명 중 3명),
- 그중 `THRESHOLD` 이상이 같은 방향(과반 `majority` | 전원 `unanimous`)이면
→ 그 방향 신호. 파라미터: `N`(기본 5), `MIN_PRESENT`(기본 3), `THRESHOLD`(majority|unanimous).

### 3.5 라벨 / 검증
- 라벨: 경기 정산까지 forward return(이진 승패), 비용(폴리마켓 cost model) 차감.
- **다변형 BH-FDR:** 검증 변형 = {3 랭킹지표} × {2 임계} × {N값들} — 전부 **한 BH-FDR 풀**에서
  보정(변형 골라잡기 = p-해킹 방지, 프로젝트 전역 규율). 다각화 봇 성과가 베이스라인.
- empirical p-value(방향 무작위/베이스라인 대비) + walk-forward.

## 4. 데이터 수집

- **MLB 마켓 식별:** `_map_market`의 `sports_market_type`/`game_start_time` + 이벤트 태그/제목
  (팀명·"MLB"). 정확 태그 슬러그는 구현 시 폴리마켓 API로 확정.
- **지갑별 MLB 이력:** MLB 마켓 `/trades`(지갑·방향·가격·크기) 축적 + 마켓 정산결과 조인 →
  지갑별 실현 MLB PnL/승률/ROI. 부트스트랩: 과거 정산 MLB 마켓 거래이력 백필 가능하면
  즉시 명단 구성, 아니면 forward 축적(MLB 매일이라 몇 주면 충분).
- **컨센서스 감지:** 오픈 MLB 마켓별 스페셜리스트 현재 포지션 스냅샷(주기 폴링).
- 신규 수집기 `research/run_mlb_specialist_collect.py`, 데이터 `research/data/mlb_specialist/`.

## 5. 아키텍처 (신규 모듈 — 샤프월렛 트랙 패턴 재사용)

```
research/mlb_specialist/market_filter.py        ← MLB 마켓 식별(순수함수)
research/mlb_specialist/leaderboard.py          ← 지갑별 MLB 성적 집계 + 3지표 랭킹(walk-forward)
research/run_mlb_specialist_collect.py          ← 수집기(트레이드+포지션 스냅샷)
research/hypotheses/mlb_specialist_consensus.py ← 컨센서스 신호 구성 + 라벨링
research/run_mlb_specialist_validate.py         ← 다변형 BH-FDR 검증 vs 다각화 베이스라인
```
재사용: `polymarket/client.py`(get_markets 등 + 지갑별 `/trades` 신규 메서드), cost model,
`empirical_p_value`, `benjamini_hochberg`, `trade_metrics`. 상수 전부 설계 고정.

## 6. 정직한 함정 (스펙이 다뤄야 할 것)
- **생존편향** → §3.3 walk-forward로 해소(과거 승자 카피 금지).
- **승률-페이버릿 편향** — 페이버릿만 쳐도 승률 높음(엣지 아님) → ROI/PnL 지표 병행 + 비용차감이 드러냄.
- **소표본 ROI 노이즈** → §3.2 게이트(MIN_BETS)로 완화.
- **다변형 = 다중검정 팽창** → §3.5 단일 BH-FDR 풀.
- **시즌성** — MLB 인시즌(4~10월)만 유효, 오프시즌 휴면. 명시.

## 7. 구현 순서(플랜 단계 태스크화)
1. MLB 마켓 식별 + 지갑별 `/trades` 수집기 → 데이터 축적 시작
2. 지갑별 성적 집계 + 3지표 walk-forward 랭킹
3. 컨센서스 신호 + 라벨 + 다변형 BH-FDR 검증기(vs 베이스라인)
4. (데이터 축적 후) 검증 실행 → 통과 시 별도 승격 검토

## 8. Out of scope
라이브 집행/알림, 비-MLB, 인앱 UI(검증 후), 실자본.
