# XAU Session Confluence 포팅 — 구현 플랜

**스펙:** `docs/superpowers/specs/2026-07-21-xau-session-confluence-port-design.md` (승인됨, 설정=Pine 기본값 유저 확인).
**브랜치:** `claude/polymarket-wallet-scoring-awzj6n`. TDD, `pytest --noconftest`.

## 데이터 레이어 (기존 재사용)
- `research.data.intraday_store.load_ohlc_lists(symbol, tf)` → `{ts(UTC epoch s), open, high, low, close, volume}`. tf ∈ {1m,5m,15m,1h,1d}.
- 아시안레인지는 60m security → `1h` 직접 사용. HTF바이어스(기본 OFF)는 240m → `1h`에서 4h 리샘플(필요 시).
- **베이스 평가 TF**: 파라미터화, 기본 `15m`(세션전략 관행). ⚠️ 유저 차트 TF와 맞춰야 트레이드 수 일치 — 플랜4에서 대조하며 확정.
- 컨테이너엔 XAU parquet 없음 → 백테스트 실행/대조는 **맥**. 순수 로직/상태머신은 합성 바로 여기서 유닛테스트.

## Task 1 — `research/xau_session/sessions.py` (순수, tz-aware)
- `SESSIONS` 상수: asian(19:00–03:00), london(02:00–11:30), ny(08:00–16:00) — NY 로컬, `zoneinfo("America/New_York")`.
- `ny_dt(ts_utc) -> datetime` (UTC epoch → NY aware). `in_session(ts_utc, name) -> bool` (자정 넘는 asian 처리).
- `session_boundary(ts_utc, name) -> {"start","end"}` 판정 헬퍼(사이클 리셋용: asian 시작=19:00, 종료=03:00).
- **테스트** `tests/test_xau_sessions.py`: 세션 포함/제외 경계, 자정 넘는 asian, DST 전환일(3월/11월) 경계 정확성.

## Task 2 — `research/xau_session/strategy.py` (순수 상태머신, 결과=트레이드 리스트)
입력: 베이스 바 시퀀스(ts/o/h/l/c) + 60m 아시안레인지 소스(no-lookahead 확정봉) + config.
상태머신(§4 바 종가 평가, 사이클당 dedup):
1. **아시안레인지**: asian 세션 중 hi/lo 추적 → 03:00 종료 시 `fixed_asian_hi/lo` 고정. `cycle_range_ready` 플래그(오버랩 stale 가드).
2. **런던 돌파**(사이클 1회): london 중 `close>hi`→롱 / `close<lo`→숏. 동봉 양방향=롱 우선. `breakout_level`·방향 기록.
3. **NY 연속**(사이클 1회): ny 중 같은 방향 `close`가 `breakout_level` 재돌파.
4. **엔트리**: `use_london_breakout AND 런던돌파` OR `use_ny_continuation AND NY연속`.
5. **리스크**: SL=반대 아시안극단, risk=|entry−SL|, TP=entry±`riskReward`(0.5)·risk, qty=`equity·riskPercent`(3)/100/(risk·point_value).
6. **필터**(토글): 아시안폭 `(hi−lo)/lo·100∈[1.2,100]` **ON**; HTF바이어스 240m EMA50 OFF; 스탑거리 OFF; 캔들강도 OFF.
7. **엑싯**: SL+TP(기본). 브레이크이븐/시간청산/트레일 OFF 토글(구조만, 기본 미동작).
8. 사이클 리셋: 아시안 시작(19:00)에 fixed/breakout/flags 초기화.
- `Config` dataclass = Pine 인풋 기본값 그대로. `run(bars, htf_bars, cfg) -> list[Trade]`.
- **테스트** `tests/test_xau_strategy.py`: 레인지 고정, 런던돌파 dedup·타이브레이크, NY연속 방향의존, R:R 청산가·qty, 아시안폭 게이트 통과/차단, 사이클 리셋, no-lookahead(미래봉 미참조).

## Task 3 — `research/run_xau_session_backtest.py` (러너, TV 대조용 통계)
- `_resample_ohlc(bars, factor)` (15m→60m 등, ffill 없이 봉경계 집계). `load(symbol, base_tf)` → 베이스+60m(+240m).
- `backtest(symbol, base_tf, cfg)` → 트레이드 리스트 + 통계 `{n_trades, win_rate, profit_factor, net, gross_win, gross_loss, avg_R}`.
- 체결가정: process_orders_on_close(바 종가), commission 2.5/계약, slippage 2, pyramiding0(동시1). 복리(equity 갱신).
- `main()`: symbol=보유분(`xyz:GOLD`/`PAXG`/`GC` 중 존재), 통계 표 출력.
- **테스트** `tests/test_xau_backtest.py`: 리샘플 봉경계, PF/승률 산식, 합성 시나리오 known-answer.

## Task 4 — TV 대조 (맥, 유저와)
- 맥에서 `python -m research.run_xau_session_backtest` → 트레이드 수/승률/PF/총손익을 유저 TradingView Strategy Tester와 대조.
- 불일치 시 원인 좁히기: 베이스 TF(우선), 세션경계/DST, 데이터소스(TV 스팟 XAU ↔ HL/IB). 통계적 근사=충실도 OK.
- 확정 후 `docs/progress.md` 업데이트.

## Task 5 (후속) — 라이브 페이퍼 엔진
- 충실도 검증 후 `run_ict_paper_engine.py` 패턴 재사용(상태·저널). 이번 플랜 범위 밖.

## 커밋 단위
Task1, Task2, Task3 각각 코드+테스트 커밋. Task4는 대조 결과를 progress.md에.
