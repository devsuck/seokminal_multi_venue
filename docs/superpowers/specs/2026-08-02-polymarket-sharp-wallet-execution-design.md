# Polymarket sharp_wallet paper 라이브 집행 봇 — Design Spec

**Status:** 사용자 승인 완료. 아키텍처(그룹별 병렬 포지션) 수락, CLOB/positions API 반영 지시, 저장공간/RAM 제약 반영 지시 — 전부 본 스펙에 통합.

## Goal

검증된(BH-FDR + walk-forward 이중 생존) Polymarket sharp_wallet 신호를 실집행 없는 paper 라이브 봇으로 돌린다. 기존 `polymarket_bot.py`(다각화 봇) 패턴 재사용하되, 청산 방식은 정산대기가 아니라 horizon 마크아웃으로 바뀐다.

## 진입 신호 — 통계적으로 확정된 그룹만

`research/run_polymarket_sharp_wallet_validate.py` 라이브 재실행 결과(가장 최신 참값):

- **진입 허용**: `bucket1`(30/120/300s 전부), `bucket3`(300s만), `mid`(30/120s만), `high`(30/120/300s 전부) — 8개 그룹.
- **진입 금지**: `bucket2`(전부 WF 탈락, 일부 wf_first 역부호), `bucket3`(30/120s), `low`(BH-FDR 자체 미생존), `mid`(300s).
- 그룹 판정 로직은 `research/hypotheses/polymarket_sharp_wallet.py`의 `build_convergence_count`/`build_convergence_score`를 **그대로 재사용** — 새로 안 짬. 다만 배치용(전체 기간 일괄계산)이라 봇에서는 600초 트레일링 롤링 윈도우로 증분 재현해야 함(수집기가 이미 쌓는 raw anchor+context 트레이드 버퍼에서 계산).

## 포지션 모델 — 그룹별 병렬 (사용자 확정)

한 anchor가 여러 그룹을 동시 충족하면(예: bucket1 AND high) **그룹마다 별도 paper 포지션**을 연다. 그룹당 사이징은 안 쪼갬 — 기존 봇과 동일 flat `trade_size_usd`. 이유: 검증 당시 사이징(`TRADE_SIZE=1.0` 고정, 그룹 무관)과 어긋나면 실집행 P&L이 통계검증 가정과 괴리됨.

노출 제한은 그룹별 서브버짓이 아니라 **전역 `max_concurrent_positions`** 하나로. YAGNI — 그룹별 예산 관리는 지금 필요성 없음.

## 청산 — horizon 마크아웃 (기존 봇과 다른 점)

기존 `polymarket_bot.py`는 정산(`m["closed"]`)까지 보유. 이 봇은 **entry_ts + 그룹의 horizon_s** 시점에 그 순간 시장가로 강제 청산. 포지션 레코드에 `exit_at` 필드로 기록, tick마다 `now >= exit_at`인 오픈 포지션을 청산 처리. 손익식은 검증기와 동일: `direction * (exit_price - entry_price) - cost`.

## 비용모델 — CLOB 실측 스프레드로 교체 (신규 반영)

`research/validation/cost_model.py`의 `polymarket_effective_cost_bps()`는 `POLYMARKET_SPREAD_BPS=200.0`이 **"미검증 근사치"**라고 코드에 명시돼 있음 — 여기가 CLOB 데이터가 실제로 확률/손익 추정에 의미있는 영향을 주는 지점.

- 포지션 진입/청산 **각 순간**에만 CLOB 오더북(`clob.polymarket.com`) 1회 조회 — best bid/ask 상위 몇 틱만. 연속 폴링/스트리밍 안 함(저장공간·트래픽 절약).
- 실측 스프레드로 그 포지션의 비용 계산(`spread_bps = (ask-bid)/mid * 10000`), 통계검증에 쓴 200bps 기본값 대신 사용. **주의**: 이건 봇의 paper P&L을 더 정확하게 만들 뿐 진입 게이트(어느 그룹이 유효한가)는 안 건드림 — 게이트를 실시간 신호로 바꾸면 이미 통과한 walk-forward 검증이 무효화됨.
- 오더북 스냅샷(상위 3틱 bid/ask)은 기존 JSONL 이벤트 로그에 포지션 레코드 옆에 같이 기록 — 별도 파일/캐시 안 만듦. 포지션당 수백 바이트 수준, 기존 로그 증가폭 무시 가능.

## Positions API — 로그만, 게이트엔 미사용 (신규 반영)

`data-api.polymarket.com` positions 엔드포인트(지갑별 순보유)는 컨센서스 방향성 강도의 추가 정보이긴 하나, **통계검증(BH-FDR/walk-forward)에 들어간 적 없는 신호**다. 지금 게이트에 넣으면 검증 안 된 규칙으로 조용히 진입기준이 바뀌는 셈 — 금지.

포지션 진입 시점에 그 anchor를 구성한 sharp wallet들의 현재 포지션만 1회 조회해서 이벤트 로그에 **참고 필드로만** 남긴다(향후 별도 가설 검증용 원재료). 봇의 진입/사이징/청산 로직 어디에도 관여 안 함.

## 저장공간/RAM 제약 반영

- CLOB/positions 호출 둘 다 **포지션 이벤트당 1회**(연속 폴링 없음) — anchor 빈도 낮고 포지션 수 유한하므로 API 콜량 작음.
- 신규 상시 프로세스/tmux 세션 없음 — 기존 봇 tick 루프(`_loop()` 패턴)에 얹음.
- 신규 대용량 캐시/데이터셋 없음(blackbox의 3MB 캐시 같은 거 안 만듦) — 전부 기존 JSONL 이벤트 로그에 필드 추가하는 수준.

## HUD

기존 `polymarket_bot.py` 라우터 패턴(`/status`, `/config`, `/run-now`) 그대로 복제해 신규 라우터로 등록, 유닛 로스터에 신규 항목 추가.

## 테스트

- 롤링 윈도우 컨버전스 계산이 배치 버전(`build_convergence_count`/`build_convergence_score`)과 **동일 결과**를 내는지 합성 트레이드 시퀀스로 대조 테스트.
- horizon 마크아웃 청산 손익식이 검증기(`_variant_pvalue`류 손익식)와 **동일 공식**인지 유닛테스트.
- 그룹별 병렬 포지션: 한 anchor가 2개 이상 그룹 동시충족할 때 포지션이 그룹 수만큼 개별 생성되는지 테스트.
- CLOB 스프레드 실측치가 비정상(0, 음수, 극단치)일 때 기본 200bps로 폴백하는지 테스트.
- positions API 실패해도(스킵) 포지션 진입/청산 로직 자체는 안 죽는지 테스트(참고 필드일 뿐이므로).

## Out of Scope

- 실집행(paper만).
- 그룹별 서브버짓/차등 사이징.
- positions API를 게이트/사이징에 반영(향후 별도 가설 검증 통과해야만 고려).
- CLOB 데이터 상시 수집/저장(포지션 이벤트 시점 1회성 조회만).
