# Polymarket MLB 스페셜리스트 — Implementation Plan

> 스펙: `docs/superpowers/specs/2026-07-21-polymarket-mlb-specialist-design.md` (승인).
> 샤프월렛 트랙 패턴 재사용. **Polymarket이 이 원격 컨테이너에서 차단(403)** → 순수 로직
> 모듈/테스트는 여기서 `--noconftest`로 완전검증, 수집기 라이브 실행·실검증은 맥에서.

**Goal:** MLB 마켓 식별 → 지갑별 MLB 성적 집계 + 3지표 walk-forward 랭킹 → 컨센서스
신호 + 라벨 → 다변형 BH-FDR 검증(vs 다각화 베이스라인). 수집+검증만, 페이퍼, 라이브 없음.

**Tech:** Python 3.11+, pandas, pytest(`--noconftest`), requests(수집기).

## Global Constraints
- 상수 설계 시점 고정(결과 보고 안 바꿈). 순수함수 우선(테스트 가능성).
- walk-forward: 스페셜리스트는 시점 T까지 이력으로만 선정, 이후 신호만 검증(look-ahead 금지).
- 다변형 BH-FDR: {3지표}×{2임계}×{N} 전부 한 풀. 변형 골라잡기 금지.
- MLB 식별은 라이브 메타 미확인 상태 → 휴리스틱(sports 필드 + 팀명/키워드) 구현, 맥에서 실튜닝.
- 신규 백엔드 없음(연구 스크립트). 재사용: polymarket client, cost model, empirical_p_value, BH-FDR.

---

### Task 1: `research/mlb_specialist/market_filter.py` — MLB 마켓 식별
**순수함수** `is_mlb_market(market: dict) -> bool`: `_map_market` 반환 dict(sports_market_type,
event_title, question, slug 등) 기준. sports 마켓이면서 제목/슬러그에 MLB 팀명 또는
"mlb"/"baseball" 키워드 → True. `MLB_TEAMS`(30팀) 상수. `mlb_condition_ids(markets) -> set[str]`.
- 테스트: 양성(MLB 팀 대결/키워드), 음성(NBA/크립토/일반), 대소문자·부분매칭.
- [ ] TDD: 테스트→실패→구현→통과→커밋.

### Task 2: `research/mlb_specialist/leaderboard.py` — 지갑별 MLB 성적 + 3지표 walk-forward 랭킹
정산된 MLB 베팅(진입가+결과)에서 지갑별 집계, **as_of 시점 파라미터로 walk-forward**:
- `wallet_mlb_stats(trades, resolutions, as_of) -> pd.DataFrame`: 컬럼 proxy_wallet,
  mlb_pnl, mlb_winrate, mlb_roi, mlb_specialization, mlb_n (as_of 이전 정산분만).
  - trades: MLB 체결(proxy_wallet, condition_id, side, price, size, notional_usd, ts).
  - resolutions: {condition_id: winning_side}(정산결과). pnl = (payout-entry)*shares 합.
  - specialization = MLB notional / 전체 notional(입력에 wallet 전체 notional 별도 제공 or MLB만이면 1.0 근사 — 설계: 전체 거래 notional 맵 인자로).
- `rank_specialists(stats, metric, n, min_bets, min_spec) -> list[str]`: 게이트 후 metric
  (`pnl`/`winrate`/`roi`) 내림차순 상위 n proxy_wallet.
- 테스트: 3지표 각각 랭킹 정확, 게이트(min_bets/min_spec) 컷, as_of 경계(미래 정산 제외), 동점.
- [ ] TDD.

### Task 3: 수집기 — `polymarket/client.py` 지갑/마켓 trades + `research/run_mlb_specialist_collect.py`
- client: `get_market_trades(condition_id, limit)` 또는 글로벌 `/trades` 폴링 재사용 —
  샤프월렛 collect 골격 복제하되 필터를 `mlb_condition_ids`로. MLB 마켓 세트 주기 갱신(get_markets→market_filter),
  `/trades` 폴링→MLB만 append(transactionHash dedup). 데이터 `research/data/mlb_specialist/`.
- 순수 파싱/필터는 페이크로 테스트, 라이브 폴링은 맥.
- [ ] 파싱·필터 유닛테스트 + `bash -n`/py_compile. 커밋.

### Task 4: `research/hypotheses/mlb_specialist_consensus.py` — 컨센서스 신호 + 라벨
- `consensus_signals(positions, specialists, min_present, threshold) -> list[dict]`:
  마켓별 스페셜리스트 포지션에서 min_present·threshold(majority|unanimous) 만족 시 방향 신호.
- `build_labels(signals, resolutions, entry_prices, cost_bps) -> pd.DataFrame`: 경기 정산까지
  forward return(이진 승패) 비용차감. 샤프월렛 라벨 컨벤션 참고.
- 테스트: 과반/전원 경계, min_present 미달 무신호, 라벨 승/패/비용.
- [ ] TDD.

### Task 5: `research/run_mlb_specialist_validate.py` — 다변형 BH-FDR 검증
- 변형 그리드({metric}×{threshold}×{N}) 각각 신호→라벨→empirical p-value. **전부 한 BH-FDR 풀**.
  다각화 봇 성과를 베이스라인 컬럼으로. `compute_report()`(대시보드 노출 대비 dict) + main 프린트.
- 테스트: 변형 그리드 생성, 단일 풀 보정, no_data, compute_report shape.
- [ ] TDD.

### Task 6: 맥 라이브(유저)
- 수집기 tmux 상시구동, 데이터 축적(MLB 매일 → 몇 주). 부트스트랩 백필 가능성 확인.
- 축적 후 validate 실행 → BH-FDR 통과 시 승격 검토.

## Self-Review
- 스펙 §3 설계 ↔ 각 태스크. walk-forward(as_of), 다변형 단일풀, 게이트 전부 반영.
- 검증경계: Task1/2/4/5 순수 `--noconftest` 완전검증, Task3 파싱만+라이브는 맥.
