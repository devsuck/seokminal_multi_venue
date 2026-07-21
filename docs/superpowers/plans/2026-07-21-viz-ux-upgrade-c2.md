# Phase C2 — 자본/성과 곡선 Implementation Plan (increment 1)

> 스펙: `docs/superpowers/specs/2026-07-21-viz-ux-upgrade-design.md`(승인). C1 프리미티브 재사용.
> 전부 dashboard 레포, 프론트 전용. C2는 여러 increment — 이 플랜은 increment 1(폴리마켓).

**Goal:** C1의 프리미티브에 이어 `TimeSeries`(lightweight-charts v5 래퍼) + `BarChart`(SVG)
프리미티브 추가하고, 사용자가 보고 있는 `/polymarket` 페이지에 realized-pnl 누적 곡선 +
리더보드 상위 PnL 막대를 얹는다. (성과 곡선 = C2 테마)

**Tech:** lightweight-charts@5(TimeSeries), SVG(BarChart). 신규 백엔드 없음 — 기존
`/polymarket/status`(log: resolve ts+pnl, realized_pnl 총계) + `/polymarket/leaderboard` 소비.

## Global Constraints
- 블룸버그 톤, 상태색은 polarity 전용, 곡선/막대 색은 pnl 극성(pos/neg) 또는 seq 매그니튜드.
- 곡선은 **realized_pnl 총계에 앵커** — 로그 창(최근 40)만으론 총계 안 맞으므로, 마지막
  점 = status.realized_pnl가 되게 역산(정직: "최근 추이"로 라벨).
- 접근성: 기존 리더보드 테이블/포지션 테이블 유지, 차트는 추가.

---

### Task 1: `TimeSeries` + `BarChart` 프리미티브

**Files:** New `components/charts/TimeSeries.tsx`, `components/charts/BarChart.tsx`

**`TimeSeries`** (RollingChart.tsx v5 패턴 그대로): props `{ series: {label,color,points:{time:number(sec),value:number}[]}[], height?, yFormat? }`. `createChart`+`addSeries(LineSeries)`, Bloomberg 레이아웃(TOKEN), `fitContent`, cleanup `chart.remove()`. 컨테이너 `style={{height}}`(허용 예외).

**`BarChart`** (SVG 수평 막대): props `{ items: {label,value,color?,href?}[], height?, valueFmt? }`. 값 최대치 기준 폭, 막대별 툴팁, 라벨+값. 색 기본 seq 또는 pos/neg(극성). 4px 라운드 데이터엔드.
- [ ] tsc 클린. 커밋.

### Task 2: `/polymarket` 적용

**Files:** Modify `app/polymarket/page.tsx`

- **realized-pnl 누적 곡선**(TimeSeries): status.log의 resolve 이벤트(ts,pnl) 오름차순,
  마지막=realized_pnl 앵커 역산 → 누적 곡선. resolve 0건이면 EmptyState. 요약줄 근처 배치.
  색 pos/neg(마지막 값 부호). 캡션 "최근 정산 추이(총 realized_pnl 앵커)".
- **리더보드 상위 PnL 막대**(BarChart): leaderboard 상위 ~12명 PnL 수평막대(프로필 링크),
  기존 50행 테이블 위에. 테이블 유지(접근성/전체).
- [ ] tsc + `validate_palette` 재확인. 커밋.

### Task 3: 시각 스모크(유저, 맥)
- `/polymarket`에 pnl 곡선 + 리더보드 막대 렌더 확인.

## Self-Review
- C1 ChartFrame 재사용. 신규 백엔드 없음. 곡선 총계 앵커(정직). 테이블 병존(접근성). one-axis.
- 후속: C2 increment 2(/performance·/pnl equity 곡선 — 그쪽 시계열 데이터 서베이 후).
