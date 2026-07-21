# 시각화/UX 강화 (Phase C) — Design Spec

**작성:** 2026-07-21. 브레인스토밍 중 확정, 사용자 승인 대기.

## 1. 배경

서베이(2026-07-21) 결과 대시보드 시각화가 **오더플로우(11개 커스텀 프리미티브)와
기술지표(11개 인디케이터)에만 몰려 있고**, 나머지(`/validation`, `/experiments`,
`/performance`, `/pnl`, `/polymarket`, `/risk-guard`, `/agents`, `/lab` 등)는 전부
테이블 + MetricCard 위주라 시각적으로 얇다. 공유 차트 추상화가 `ui/ChartPanel`
하나뿐이고, lightweight-charts 프리미티브 외에 재사용 가능한 통계/시계열 차트
컴포넌트가 없다 — 페이지마다 bespoke.

디자인 시스템은 이미 의도적 "블룸버그 터미널"(순흑 배경, 앰버 액센트 `#FF9F0A`,
시안 HUD `#22D3EE`, 0px radii, mono 데이터 폰트, 시그널 컬러 pos/neg/warn/info)이
`app/globals.css @theme`에 정립돼 있다. **그러나 이 시그널 컬러는 "상태"(polarity/
state)용 예약색**이라, 다계열 차트의 계열 식별(categorical)에 재사용하면 안 된다
(dataviz 규율). 즉 데이터 시각화용 램프(categorical/sequential/diverging)가 없다.

**방법론:** `dataviz` 스킬 채택 — form 먼저, 색은 마지막, "색은 계산한다(eyeball 금지)",
one-axis, 상태색 예약, 범례/툴팁/테이블/CVD 접근성.

## 2. 목적 및 범위

**블룸버그 톤을 유지하면서** 재사용 차트 프리미티브 레이어 + 검증된 viz 색 램프를
만들고, 얇은 페이지부터 우선순위대로 실제 차트를 얹어 UX/UI를 강화한다.

**포함:**
- `components/charts/` 재사용 차트 컴포넌트 라이브러리(공통 축/범례/툴팁 규약)
- viz 색 램프(categorical/sequential/diverging) `@theme`에 추가 — 시그널 컬러와 분리
- 우선순위 페이지 롤아웃(§6)

**제외(범위 밖):**
- 테마 토큰 재디자인 — 기존 블룸버그 시스템 **위에 쌓는다**, 갈아엎지 않음
- 오더플로우/기술지표 차트 재작업 — 이미 풍부, 안 건드림
- 신규 백엔드 데이터/엔드포인트 — 차트는 **기존 엔드포인트 소비만**(신규 데이터 없음)
- 라이트 모드 — 앱은 순흑 터미널로 커밋됨, 다크 전용(램프도 다크 서피스 기준 검증)

## 3. 설계 원칙 (dataviz)

1. **Form 먼저.** 데이터의 일 → 차트 타입. 매그니튜드=bar, 시계열=line/area,
   분포=histogram, 극성=diverging, 단일 헤드라인=stat tile(차트 아님). 억지 차트 금지.
2. **One axis.** 이중 y축 절대 금지. 스케일 다른 두 측정 → 별도 차트 or 공통베이스 인덱싱.
3. **상태색 예약.** pos/neg/warn/info(+accent 앰버, hud 시안)는 polarity/state 전용 —
   **계열 식별에 재사용 금지.** 다계열은 별도 categorical 램프(§4).
4. **색은 계산.** 모든 categorical 램프는 `scripts/validate_palette.js`(dataviz)로
   다크 서피스(#000/#1a1a19) 검증 통과 필수 — CVD ΔE·명도밴드·대비.
5. **범례/직접라벨/은은한 축.** 2계열↑이면 범례 상시(1계열은 제목이 이름), 얇은 마크
   (2px 라인, 4px 라운드 데이터엔드, 겹침 2px 서피스 링), 축·그리드 recessive.
6. **호버 레이어 기본.** line/area 크로스헤어+툴팁, bar/cell 마크별 툴팁. 테이블 뷰 병존.
7. **렌더 후 눈으로 확인.** 검증기는 색만 봄 — 라벨 충돌·오버플로우는 스크린샷으로.

## 4. viz 색 시스템 확장 (검증됨)

`@theme`에 신규 램프 추가 — 기존 시그널 컬러와 **분리**:

- **Categorical(계열 식별)** — 고정 순서, 절대 순환 안 함. 다크 #000 서피스에서
  `validate_palette.js` **전 항목 PASS**한 5색:
  `#2563EB(blue) · #EA580C(orange) · #0D9488(teal) · #9333EA(violet) · #DB2777(rose)`
  (명도밴드 0.48–0.67 · CVD 최악 ΔE 13.8 · normal 23.4 · 대비 ≥3:1 전부 통과).
  6번째 계열은 새 hue 생성 금지 → "기타"로 접거나 small-multiples/facet.
  ⚠️ 플랜에서 teal↔hud(시안)·orange↔accent(앰버) 실사용 혼동 없는지 눈으로 재확인,
  필요시 indigo/magenta로 스왑(검증 재실행).
- **Sequential(매그니튜드)** — 단일 hue 명도 스텝(light→dark). 기본 hud 시안 계열
  또는 앰버 계열 한 톤. heatmap 매그니튜드·밀도용. 라이트엔드 ≥2:1 대비.
- **Diverging(극성)** — 2 hue + 중립 회색 midpoint. pnl/수익률/편차 heatmap용.
  neg(적)↔중립(회)↔pos(녹) — 단 이건 "상태 극성"이라 시그널 컬러 재사용이 정당한 유일 케이스.
  중간에 hue 금지(무지개 금지).

램프는 `globals.css @theme`에 `--chart-cat-1..5`, `--chart-seq-*`, `--chart-div-*`로 토큰화.

## 5. 재사용 차트 컴포넌트 (`components/charts/`)

시계열은 lightweight-charts@5(이미 표준), 통계/분포는 SVG(+필요시 d3-scale)로. 공통
`ChartFrame`(제목/축/범례/툴팁 규약) 위에 조립. **플래그십 = 방금 만든 p-value 작업과
직결**:

| 컴포넌트 | 용도 (form) | 기반 |
|---|---|---|
| **`<NullDistribution>`** ★플래그십 | empirical p-value 시각화 — 방향셔플 null 분포(histogram) + 실제값 마커 + p-value 음영. "이 엣지가 랜덤과 구분되나"를 한 눈에 | SVG |
| `<Heatmap>` | group×horizon p-value 격자(sequential/diverging), 상관행렬, 캘린더 | SVG |
| `<TimeSeries>` | equity/pnl/확률(가격)-over-time, 다계열 라인/영역, 크로스헤어+툴팁 | lightweight-charts |
| `<BarChart>` | 리더보드 PnL, 그룹 매그니튜드(수평/수직), 마크별 툴팁 | SVG |
| `<Sparkline>` | 테이블·카드 인라인 미니트렌드 | SVG |
| `<ChartFrame>`/`<ChartLegend>`/`<ChartTooltip>` | 공통 축·범례·툴팁·빈상태·로딩 | — |

전부 블룸버그 톤(순흑, mono 라벨, 0px, 텍스트는 text 토큰·마크만 색). 각 컴포넌트
테이블 뷰 fallback + 범례 + 호버.

## 6. 우선순위 롤아웃 (가치순, 최근 작업과 연결)

- **C1 — 파운데이션 + 플래그십:** `components/charts/` 프리미티브 + viz 램프(@theme) +
  `/validation` 적용. 방금 만든 엣지검증 p-value **테이블을 `<NullDistribution>`(실제 vs
  셔플 null) + `<Heatmap>`(group×horizon)로 시각화**. 추상 숫자 → 직관적 통찰. ★최고 ROI
- **C2 — 자본/성과 곡선:** `/polymarket`(리더보드 bar, 포지션·realized_pnl over time),
  `/performance`·`/pnl`(equity/pnl 곡선), `/portfolio`(구성 bar).
- **C3 — 나머지 얇은 페이지:** `/risk-guard`, `/agents`(에이전트별 성과 sparkline),
  논문 파이프라인 가시화(수집/리젝 추이), `/experiments` 등.

각 페이즈 독립 배포 가능. C1이 프리미티브를 만들면 C2/C3는 조립만.

## 7. 테스트 및 검증

- `npx tsc --noEmit` 클린(전 페이즈).
- **색 검증:** 모든 categorical 램프 `validate_palette.js` PASS(다크). 인페이지
  `<script type="module">`로 CI/개발 중 재검증 가능.
- 접근성: 2계열↑ 범례 상시, 테이블 뷰 병존, 호버 툴팁, CVD 통과(위 검증).
- ⚠️ **시각 스모크는 맥에서**(원격 컨테이너 백엔드 미기동) — 렌더 후 라벨충돌/오버플로우 눈으로 확인.

## 8. 구현 순서(플랜 단계에서 태스크화)

1. viz 램프 `@theme` 추가 + `validate_palette` 최종 확정(teal/orange 혼동 재확인)
2. `components/charts/` 공통(ChartFrame/Legend/Tooltip) + `<NullDistribution>` + `<Heatmap>`
3. `/validation` 엣지검증 섹션에 두 차트 적용(C1 완료)
4. C2/C3는 후속 플랜(프리미티브 재사용)

## 9. Out of scope (명시적)
- 테마 토큰 재디자인, 오더플로우/기술지표 재작업, 신규 백엔드 데이터, 라이트 모드.
- 실집행/라이브 알림 — 이건 viz 스펙, 검증 규율(스크리닝 배너)은 기존대로 유지.
