# cross_venue_skew 오토리서치 로더 — 스트리밍 재설계

**Status:** approved by user (2026-09-14, "스트리밍 집계로 재설계" 선택). 서버/인프라 제외.

## Background

`research/autoresearch/engines_microstructure.py`의 `skew_divergence_momentum`/
`basis_reversion` 두 소스가 `research/data/cross_venue_skew/`(venue×coin×일자
`.jsonl.gz`, 오더북 레벨5 스냅샷)를 배치마다 로드한다.

2026-09-13 SIGKILL 재현 원인 분석 중 발견한 1차 수정(`_load_venue_snapshots_cached`
캐시 공유 + `SKEW_LOOKBACK_DAYS=45` 윈도 클립, 커밋 전)을 이번 세션에서 타이밍
재검증했다: 45일 윈도로도 배치 프로세스가 1시간 만에 물리 메모리 70.6GB, GC
`gc_collect_main`에 100% 시간 소비 — 강제 종료(SIGTERM)했다.

실측: `okx_BTC_2026-07-20.jsonl.gz` 1개 파일 — 압축 46MB → 압축해제 시 2.99GB
(65배 팽창), 393,740줄. 필드: `symbol, ts, bids, asks, venues, by_venue`(레벨5).

**근본원인 재확인**: 45일 윈도 클립은 파일 개수만 20%(56→45일) 줄였을 뿐, 파일
1개가 이미 GB 스케일이라는 진짜 문제를 못 건드렸다. 원인은 pandas DataFrame이
`bids`/`asks`를 dict 리스트(레벨당 2필드 × 5레벨 × 2사이드 = 20 dict)로 행마다
object dtype 컬럼에 통째로 들고 있는 구조 — GC가 추적해야 할 파이썬 객체 수가
줄 수(39만) × 20+ 배로 폭발한다.

### 소비자 조사 결과 (이번 세션 재확인)

`research/hypotheses/cross_venue_skew.py::load_venue_snapshots()`(원본 DataFrame
로더)의 실제 소비자는 두 갈래로 나뉜다:

1. **`research/run_cross_venue_skew_validate.py`** — 수동 실행 스크리닝 스크립트.
   `build_imbalance`(레벨5 bids/asks 필요) → `align_venues`(1초 그리드) →
   `build_skew_divergence` → `build_spike_signal`(롤링 300틱 z-score) →
   `build_labels_multi_horizon`. **진짜로 레벨5 원본이 필요함.** 배치 루프에
   안 걸림 — 이번 SIGKILL과 무관, 수정 범위 밖.

2. **`engines_microstructure.py`** (배치마다 자동 실행, SIGKILL 발생 지점):
   - `_skew_divergence_result()` — `_skew_candidate`(skew_divergence_momentum)가 씀.
     validate.py와 동일한 `build_imbalance`/`build_price_series`/`align_venues`/
     `build_spike_signal`/`build_labels_multi_horizon` 체인을 그대로 재현한다.
     **레벨5 원본이 필요하지만, 그 함수들이 각 행에서 실제로 뽑는 값은 스칼라
     2개(`imbalance`, `mid`)뿐** — bids/asks 리스트 자체는 그 계산이 끝나면 필요 없음.
   - `_daily_mid()`/`_basis_signs_outcomes()` — `_basis_candidates`(basis_reversion)가
     씀. `best_bid`/`best_ask` → 일별 평균 `mid` 하나만 있으면 됨. bids/asks 원본,
     imbalance 둘 다 불필요.

**결론**: `load_venue_snapshots`(원본 DataFrame 반환) 자체는 그대로 둔다 —
validate.py가 필요로 하고, 배치 루프에 안 걸려 있어 안전하다. `engines_microstructure.py`
쪽 경로만 새 스트리밍 로더로 교체한다: 파일을 줄 단위로 읽으면서 그 줄에서
`imbalance`와 `mid` 스칼라만 뽑고 bids/asks는 즉시 버린다. DataFrame에 원본을
통째로 올리는 단계 자체를 없앤다.

## Non-Goals

- `research/hypotheses/cross_venue_skew.py::load_venue_snapshots`/
  `run_cross_venue_skew_validate.py` 수정 없음 — 배치 루프 밖, 이번 이슈와 무관.
- 신규 데이터 수집기/보존정책 변경 없음.
- `SKEW_LOOKBACK_DAYS`/`_MIN_DAYS`/`_MIN_EVENTS` 등 사전등록 통계 게이트 값 변경 없음
  — 안전 상한으로 그대로 유지.
- 서버 배포/인프라 변경 없음(사용자 명시 제외).
- `absorption_momentum`/`ofi_momentum` 소스(다른 데이터 디렉토리, 이 문제와 무관) 불변.

## Architecture

```
research/hypotheses/cross_venue_skew.py
  ├─ load_venue_snapshots()       # 원본 DataFrame 로더 — 불변, validate.py 전용
  ├─ _imbalance_of(bids, asks, depth_n)   # 신규: 스칼라 imbalance 계산 (기존 build_imbalance._imb 추출)
  ├─ _mid_of(bids, asks)                  # 신규: 스칼라 mid 계산 (기존 build_price_series._mid 추출)
  ├─ build_imbalance()             # 불변, 내부에서 _imbalance_of 재사용 (DRY, 동작 동일)
  ├─ build_price_series()          # 불변, 내부에서 _mid_of 재사용 (DRY, 동작 동일)
  └─ stream_imbalance_and_mid()    # 신규: venue×coin×dates 파일 스트리밍 →
                                    #   (imbalance: pd.Series[ts], mid: pd.Series[ts])
                                    #   bids/asks는 줄 단위로만 존재, 보관 안 함

research/autoresearch/engines_microstructure.py
  ├─ _snapshot_cache               # (venue,coin) -> (imbalance_series, mid_series) 캐시로 교체
  │                                #   (기존: (venue,coin) -> DataFrame, GB급 → 이제 KB~MB급)
  ├─ _load_venue_series_cached()   # 신규, _load_venue_snapshots_cached 대체
  │                                #   내부에서 stream_imbalance_and_mid() 호출 + 45일 윈도 클립 유지
  ├─ _daily_mid()                  # mid_series를 날짜별 groupby-mean으로 재작성
  ├─ _skew_divergence_result()     # raw_by_venue(DataFrame dict) 대신
  │                                #   imbalance_by_venue/mid_by_venue(Series dict) 직접 사용,
  │                                #   build_imbalance/build_price_series 호출 제거(이미 스트리밍이 계산함)
  └─ _basis_signs_outcomes()       # 불변 (내부에서 부르는 _daily_mid()만 바뀜)
```

### `stream_imbalance_and_mid()` 동작

`load_venue_snapshots`와 같은 파일 탐색 규칙(평문 우선, 없으면 `.gz`)을 따르되,
`pd.DataFrame(rows)`로 전량 적재하는 대신 파일 핸들을 줄 단위로 순회한다:

```python
def stream_imbalance_and_mid(
    venue: str, coin: str, dates: list[str], depth_n: int = IMBALANCE_DEPTH_N,
) -> tuple[pd.Series, pd.Series]:
    """load_venue_snapshots와 동일 파일 탐색·파싱이지만 bids/asks를 DataFrame에
    적재하지 않고 줄마다 imbalance/mid 스칼라만 뽑아 즉시 버림 — 피크 메모리가
    파일 크기(GB)가 아니라 스칼라 배열 크기(날짜당 스냅샷 수 × 16바이트*2)에 비례.
    반환값은 build_imbalance/build_price_series가 만들던 것과 동일한 형태
    (index=ts인 pd.Series) — align_venues 등 하위 함수는 무수정으로 그대로 받는다."""
    ts_list, imb_list, mid_list = [], [], []
    for date in dates:
        # ... load_venue_snapshots와 동일한 opener 탐색 로직 ...
        with opener() as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                bids, asks = row["bids"], row["asks"]
                ts_list.append(row["ts"])
                imb_list.append(_imbalance_of(bids, asks, depth_n))
                mid_list.append(_mid_of(bids, asks))
    ts_arr = pd.Series(ts_list)
    order = ts_arr.argsort()
    ts_sorted = ts_arr.to_numpy()[order]
    imbalance = pd.Series(pd.Series(imb_list).to_numpy()[order], index=ts_sorted)
    mid = pd.Series(pd.Series(mid_list).to_numpy()[order], index=ts_sorted)
    return imbalance, mid
```

`_imbalance_of`/`_mid_of`는 `build_imbalance`/`build_price_series`의 기존 클로저
로직(`_imb`/`_mid`)을 행 단위 함수(`(bids, asks) -> float`)로 그대로 추출한 것 —
공식 변경 없음, 두 곳(스트리밍 경로·기존 DataFrame apply 경로)이 같은 함수를 호출해
결과가 항상 일치한다(DRY, 회귀 방지).

### `_skew_divergence_result()` 변경

기존:
```python
raw_by_venue = {v: df for v in SKEW_VENUES if (df := _load_venue_snapshots_cached(v, coin)) is not None}
imbalance_by_venue = {v: build_imbalance(df) for v, df in raw_by_venue.items()}
price = build_price_series(raw_by_venue)
```

이후:
```python
series_by_venue = {v: s for v in SKEW_VENUES if (s := _load_venue_series_cached(v, coin)) is not None}
imbalance_by_venue = {v: imb for v, (imb, _mid) in series_by_venue.items()}
price = pd.concat([mid for _imb, mid in series_by_venue.values()], axis=1).mean(axis=1, skipna=True)
```

(`build_price_series`가 하던 "벤뉴별 mid를 align_venues로 그리드 정렬 후 평균"과
동일한 결과를 내도록 `align_venues`를 재사용 — 정확한 구현은 계획 단계에서 확정.)

### 캐시 무효화/크기

`_snapshot_cache`는 키(venue, coin)당 `(imbalance: pd.Series, mid: pd.Series)` 튜플만
보관 — 45일 × 하루 스냅샷 수(수만 건) × float64 2개 = 수 MB 수준. 기존 GB급 DataFrame
캐시 대비 3~4자리수 축소. `SKEW_LOOKBACK_DAYS=45` 클립은 그대로 유지(안전 상한 —
스트리밍으로 행당 메모리가 줄어도 날짜 수가 무한 증가하면 여전히 위험).

## Error Handling

- 파일 없음/손상 줄: 기존 `load_venue_snapshots`와 동일하게 조용히 skip(에러 없음) —
  동작 변경 없음, 그대로 이식.
- `bids`/`asks` 키 누락 등 `KeyError`: 기존 로더도 방어 안 함(사전조건: 수집기가 항상
  두 키를 채움) — 이 계약 유지, 신규 방어 코드 추가 안 함(YAGNI).

## Testing

- `tests/test_cross_venue_skew.py`: `_imbalance_of`/`_mid_of` 단위 테스트 추가(기존
  `build_imbalance`/`build_price_series` 테스트와 같은 케이스로 값 일치 확인).
  `stream_imbalance_and_mid`가 `load_venue_snapshots`+`build_imbalance`+
  `build_price_series` 조합과 동일한 결과를 내는지 비교 테스트 1개(회귀 방지 핵심).
- `tests/test_engines_microstructure.py`: 기존 `_load_venue_snapshots_cached` 관련
  테스트(캐시 공유, 45일 클립)를 `_load_venue_series_cached` 기준으로 재작성.
  신규: 대용량 파일(예: 10만 줄) 스트리밍 시 피크 메모리가 상수(파일 크기와 무관)에
  가깝다는 걸 확인하는 sanity 테스트 — `tracemalloc`으로 스트리밍 중 피크가 줄 수에
  선형(수 MB)이지 파일 크기(수백 MB 시뮬레이션)에 비례하지 않음을 확인.
- 기존 `test_load_venue_snapshots_cached_clips_to_lookback_window`,
  `test_select_basis_pairs_caches_daily_mid_across_pairs` 테스트는 캐시 키/함수명만
  바뀐 채 의도(캐시 공유, 윈도 클립) 그대로 유지.

## Migration

미커밋 상태인 기존 45일 윈도 fix(`engine.py`, `engines_microstructure.py`, 두 테스트
파일)를 베이스로 위에 쌓는다 — 그 fix의 캐시/윈도 클립 골격은 유지하고 캐시가
담는 값의 타입만 DataFrame → (Series, Series)로 바뀐다. 완료 후 실제 배치 규모
데이터(`research/data/cross_venue_skew/`, 6조합 × 45일)로 재현 타이밍 검증 —
이번엔 물리 메모리(`/usr/bin/sample` 또는 `resource.getrusage`)를 기준으로 확인하고
(`ps` RSS는 이번 세션에서 신뢰 불가로 판명됨), 수 GB 이내에서 배치가 끝나는지 확인
후에만 커밋한다.
