# Polymarket 엣지 검증(p-value/BH-FDR) 대시보드 노출 — Design Spec

**작성:** 2026-07-21. 브레인스토밍 중 확정, 사용자 승인 대기.

## 1. 배경

폴리마켓 엣지 후보(sharp-wallet convergence, whale spike)는 `research/run_*_validate.py`
러너가 empirical p-value(방향 무작위 셔플 베이스라인) + BH-FDR 다중검정 보정까지
계산한다. **그런데 이 결과가 전부 CLI stdout 프린트로만 존재한다** — 대시보드에서
"지금 통계적 엣지가 있나?"를 확인할 방법이 없다. 유저가 SSH로 들어가
`python -m research.run_polymarket_sharp_wallet_validate`를 직접 돌려야만 볼 수 있다.

서베이(2026-07-21) 확인:
- p-value/BH-FDR가 HTTP로 노출된 건 pairs 코인테그레이션 `eg_pvalue` 하나뿐(`main.py:4173`).
- `/validation` 페이지는 experiment registry(verdict 라벨: candidate/blocked/rejected)만
  보여주고 **p-value 수치·BH-FDR 생존 여부는 안 보여준다.**
- 이미 존재하는 백그라운드-웜 패턴(`lab_api.py:_task_forward`/`_warm_task_forwards`)이
  "느린 계산을 캐시에 워밍하고 엔드포인트는 스냅샷만 반환"하는 정확히 이 용도의 선례.

## 2. 목적 및 범위

**연구/검증 결과의 읽기 전용 노출.** 라이브 시그널·알림·실집행은 범위 밖(엣지 후보
전부 아직 BH-FDR 미통과 — 노출이 "매매해도 된다"로 오해되면 안 됨, §7).

**포함:**
- sharp-wallet 검증(버킷 3 × 호라이즌 3 + score tercile 3 × 호라이즌 3, **2개 분리 BH-FDR 풀**)
- whale 검증(family × 호라이즌, 최대 6 p-value, 1개 BH-FDR 풀)
- 두 검증의 p-value 테이블 + BH-FDR 풀 요약(생존자/임계/alpha) + 데이터 커버리지 노출
- 대시보드 `/validation` 페이지에 "Polymarket 엣지 검증" 섹션 신규

**제외(범위 밖):**
- arb 3-axis go/no-go 게이트(`run_polymarket_arb_validation.py`) — p-value 기반이 아니라
  shape가 다름, 별도 후속
- event-divergence — 아직 validate 러너 없음(수집만)
- 라이브 알림, 실집행, cron 자동 스케줄(수동/주기 워밍만)
- walk-forward(러너들이 스크리닝 전용이라 이미 생략 — UI에 그 사실 명시)

## 3. 핵심 설계 결정

### 3.1 계산-프린트 분리 리팩터 (백엔드 재사용성)

현재 `run_*_validate.py`의 `main()`은 계산과 `print()`가 뒤엉켜 있다. 이걸
`_task_forward`가 페이퍼 러너에 `generate(write=False)` dict 반환을 기대하듯,
각 validate 러너에 **`compute_report() -> dict` 순수 함수를 추출**한다:

- `run_polymarket_sharp_wallet_validate.compute_report() -> dict`
- `run_polymarket_whale_validate.compute_report() -> dict`
- 각 `main()`은 `compute_report()` 호출 후 기존과 동일하게 프린트(CLI 동작 불변 — 회귀 없음)

`compute_report()` 반환 스키마(두 러너 공통 shape):
```python
{
  "hypothesis": "polymarket_sharp_wallet",     # | "polymarket_whale"
  "cost_bps": 100.0,
  "dates": ["2026-07-21", ...],                 # 커버된 수집 날짜
  "n_anchors": 47,                              # 표본 규모(작으면 UI 경고)
  "groups": [                                   # 버킷/tercile/family 축
    {"group": "bucket1", "blocked": false,
     "horizons": [{"horizon": "30s", "n_events": 18, "total_pnl": 0.36,
                   "p_value": 0.27, "percentile": 73.0}, ...]},
    {"group": "bucket3", "blocked": true, "reason": "라벨 없음"},
    ...
  ],
  "pools": [                                    # BH-FDR 풀(sharp-wallet은 2개, whale은 1개)
    {"name": "bucket", "alpha": 0.1, "n_tested": 6, "n_survivors": 0,
     "survivors": [], "threshold": null},
    {"name": "score_tercile", "alpha": 0.1, "n_tested": 9, "n_survivors": 0,
     "survivors": [], "threshold": null},
  ],
  "verdict": "no_edge",                         # n_survivors 합==0 → "no_edge", >0 → "candidate"
}
```

sharp-wallet은 이미 `main()`이 버킷 풀·score tercile 풀을 각각 만들어 프린트하므로,
그 로직을 `compute_report()`로 옮기고 dict로 담기만 하면 된다(신규 통계 계산 없음).

### 3.2 백그라운드-웜 캐시 (동기 요청 블록 방지)

`compute_report()`는 N_RUNS=500 셔플 × 최대 9 p-value라 **수 초~수십 초** 걸린다.
매 요청마다 동기 실행하면 이벤트 루프 블록 + 페이지 폴링이 API를 짓누른다. 그래서
`_task_forward` 선례 그대로:

- 모듈 전역 캐시 `{ts, reports: {hypothesis: report}, warming: bool}`
- `GET /lab/edge-validation` — 캐시 스냅샷 즉시 반환. 캐시가 stale(예: >10분)이고
  워밍 중이 아니면 백그라운드 스레드로 `_warm()` 트리거(요청은 절대 블록 안 함).
- `POST /lab/edge-validation/refresh` — 수동 강제 워밍 트리거(유저가 "지금 다시 계산").
- 캐시 비어있으면 첫 요청은 `{warming: true, reports: {}}` 반환 → 프론트가 "계산 중" 표시.

느린 계산이므로 스레드 실행(`threading.Thread`), 재진입 방지 `warming` 플래그.

### 3.3 데이터 없을 때 / 표본 작을 때

- 수집 날짜 0개 → `compute_report()`가 빈 groups + `verdict:"no_data"` 반환, UI는 "수집 대기".
- `n_anchors`가 작으면(임계는 UI 판단, 예 <30) 배너로 "표본 부족 — 결과 신뢰도 낮음" 경고.
  (수치 자체는 보여주되 과신 방지.)

## 4. 아키텍처

```
research/run_polymarket_sharp_wallet_validate.py   ← compute_report() 추출, main()은 이를 프린트
research/run_polymarket_whale_validate.py           ← 동일
api_server/lab_api.py                                ← 캐시 + GET /lab/edge-validation + POST .../refresh
seokminal-dashboard/lib/api.ts                       ← getEdgeValidation() + 타입
seokminal-dashboard/app/validation/page.tsx          ← "Polymarket 엣지 검증" 섹션
```

신규 파일 없음(수집기/데이터 신규 없음). 순수 리팩터 + 노출.

## 5. 대시보드 UI (`/validation` 페이지 섹션 신규)

기존 experiment-registry 섹션 **아래**에 "Polymarket 엣지 검증" 섹션 추가:

- 상단 배너(항상): **"스크리닝 결과일 뿐 실집행 근거 아님. walk-forward 생략, 표본
  기간 미달. BH-FDR 통과해도 전체 파이프라인 승격 검토 대상."** (프로젝트 규율 그대로)
- 가설별 카드(sharp-wallet / whale):
  - 커버리지: 날짜 범위, `n_anchors`(작으면 경고 뱃지)
  - p-value 테이블: group × horizon 행(n_events, total_pnl, p_value, percentile),
    BLOCKED 그룹은 사유 표시. p_value < 0.05는 강조(단 BH-FDR 생존과는 별개임을 명시)
  - BH-FDR 풀 요약: `n_survivors / n_tested`, 생존자 키 리스트, 임계값. **생존자 0이면
    "확인된 엣지 없음(정상 — 정직한 결과)"으로 명시적 표기**(빈 테이블로 오해 방지)
  - "지금 다시 계산" 버튼 → `POST /refresh`, 워밍 중 스피너
- 블룸버그 톤 유지(기존 `/validation` 페이지 컴포넌트·토큰 재사용, 순흑+시그널 컬러,
  0px radii, mono 데이터 폰트).

## 6. 테스트

- 백엔드: `compute_report()` 단위 테스트 — 합성 ledger(수집 JSONL 픽스처)로
  groups/pools/verdict shape 검증, 데이터 없을 때 `no_data`, 생존자 0 케이스.
  기존 `run_bucket`/`run_score_tercile`/`run_family` 테스트는 불변(회귀 없음).
  `main()`이 여전히 크래시 없이 프린트하는지 스모크(기존 `test_main_*` 유지).
- 프론트: `getEdgeValidation` 타입 정합 + 섹션 렌더(생존자 0 / 표본부족 / 계산중 상태).
- ⚠️ 엔드포인트 런타임 검증은 맥에서(원격 컨테이너는 nautilus 드리프트 + Polymarket
  차단으로 `api_server.main` 미기동).

## 7. Out of scope (명시적)

- 라이브 시그널·알림·실집행 — 엣지 미확인 상태. 노출은 오직 "연구 결과 열람".
- arb 3-axis 게이트, event-divergence 검증 — shape 다름/러너 없음, 별도 후속.
- cron 자동 스케줄 — 수동 refresh + stale 시 백그라운드 워밍만(상시 크론 아님).
- 스코어 절대비교·런 간 비교 — percentile 정규화라 런 내부 상대비교만(원 스코어 스펙 §3 트레이드오프 계승).

## 8. 구현 순서(플랜 단계에서 태스크화)

1. `compute_report()` 추출(sharp-wallet, whale) + 단위테스트 — CLI 동작 불변 확인
2. `lab_api.py` 캐시 + 2개 엔드포인트 + 백그라운드 워밍
3. 프론트 `getEdgeValidation` + `/validation` 섹션
4. 맥에서 런타임 스모크(엔드포인트 200 + 페이지 렌더)
