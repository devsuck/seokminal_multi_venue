# Phase C1 — 시각화 파운데이션 + 플래그십(엣지검증 viz) Implementation Plan

> 스펙: `docs/superpowers/specs/2026-07-21-viz-ux-upgrade-design.md` (승인됨). 이 플랜은 C1만.
> 전부 대시보드 레포(`seokminal_dashboard`), 프론트 전용 — tsc + 색검증으로 완전 검증 가능.

**Goal:** 재사용 차트 프리미티브 레이어 + 검증된 viz 색 램프를 만들고, 방금 만든
`/validation` 엣지검증 섹션에 group×horizon **Heatmap** + per-row **NullDistribution**
(percentile strip)로 시각화. 추상 p-value 테이블 → 직관적 통찰.

**Tech Stack:** Next.js/TS, SVG(+CSS var 색), lightweight-charts는 C1 미사용(통계 차트라 SVG).

## Global Constraints
- 블룸버그 톤 유지: 순흑, mono 라벨, 0px radii, 텍스트는 text 토큰·마크만 색.
- 상태색(pos/neg/warn/accent/hud) 계열식별 재사용 금지 → 신설 categorical 램프 사용.
- categorical 램프는 `validate_palette.js`(dataviz) 다크 PASS 필수(이미 통과한 5색 사용).
- 접근성: 기존 p-value **테이블 유지**(table view fallback), 차트는 위에 추가. 호버 툴팁.
- 신규 백엔드 없음 — 기존 `/lab/edge-validation` 데이터(group/horizon: p_value·percentile·
  total_pnl·n_events)만 소비. NullDistribution은 percentile 기반 strip(전체 null 히스토그램은
  백엔드 null 분위수 필요 → C1 범위 밖, 향후).

---

### Task 1: viz 색 램프(`@theme`) + `lib/chart-colors.ts`

**Files:** Modify `app/globals.css`; New `lib/chart-colors.ts`

`app/globals.css` `@theme`에 추가(신호색 블록 아래):
```css
/* data-viz 램프 — categorical은 #000 서피스 validate_palette.js 전항목 PASS, 상태색과 분리 */
--color-chart-1: #2563EB;  --color-chart-2: #EA580C;  --color-chart-3: #0D9488;
--color-chart-4: #9333EA;  --color-chart-5: #DB2777;
/* sequential(매그니튜드) — 시안 단일 hue light→dark */
--color-seq-1: #CFFAFE;  --color-seq-2: #22D3EE;  --color-seq-3: #0E7490;  --color-seq-4: #164E63;
```

`lib/chart-colors.ts`:
```typescript
export const CHART_CAT = [
  "var(--color-chart-1)", "var(--color-chart-2)", "var(--color-chart-3)",
  "var(--color-chart-4)", "var(--color-chart-5)",
] as const;
// 고정 순서, 절대 순환 금지 — 6번째 계열은 "기타"로 접기
export function catColor(i: number): string { return CHART_CAT[i] ?? "var(--color-text-3)"; }
// sequential: t in [0,1] (0=약함→1=강함) → 시안 램프 보간(4스텝 이산)
export function seqColor(t: number): string {
  const steps = ["var(--color-seq-1)", "var(--color-seq-2)", "var(--color-seq-3)", "var(--color-seq-4)"];
  const clamped = Math.max(0, Math.min(1, t));
  return steps[Math.min(steps.length - 1, Math.floor(clamped * steps.length))];
}
```
- [ ] `npx tsc --noEmit` 클린. 커밋.

---

### Task 2: `components/charts/` 프리미티브

**Files:** New `components/charts/ChartFrame.tsx`, `components/charts/Heatmap.tsx`, `components/charts/NullDistribution.tsx`

**`ChartFrame`** — 제목 + optional 범례 + 빈/로딩 상태 래퍼(Panel과 별개, 차트 내부용).
props: `{ title?, legend?: {label,color}[], empty?, children }`. 범례 2계열↑ 상시.

**`Heatmap`** — group×horizon 격자. props:
```typescript
{ rows: string[]; cols: string[];
  cell: (r: string, c: string) => { value: number | null; label: string; tone?: "sig" | "muted" } | null;
  colorOf: (value: number) => string;  // 기본 seqColor(1 - p_value)
}
```
SVG rect 격자, 각 셀 fill=colorOf, 셀 hover시 title 툴팁(값+라벨). null 셀=BLOCKED(회색 hatch).
행/열 라벨 mono. 셀 사이 2px 서피스 갭.

**`NullDistribution`** (percentile strip form) — 실제값이 방향셔플 null 대비 어디 있나.
props: `{ percentile: number; pValue: number; label?: string }`.
0–100 수평 축(null 랭크), 실제값 마커를 percentile 위치에, 상위 유의영역(percentile ≥ 95,
= p 0.05) 음영. p<0.05면 accent 강조. 축 아래 "vs 랜덤 500 셔플" 캡션. 순수 SVG, 툴팁.
- [ ] `npx tsc --noEmit` 클린. 커밋.

---

### Task 3: `/validation` 엣지검증 섹션에 적용

**Files:** Modify `app/validation/page.tsx`

`EdgeReportCard` 안에서(기존 p-value 테이블 **위에**):
- **Heatmap**: rows = 그룹명(bucket1/2/3, low/mid/high 또는 news/sports), cols = horizons(30s/120s/300s).
  cell = 해당 group×horizon의 p_value(있으면), colorOf = `seqColor(1 - p_value)`(유의할수록 진함),
  BLOCKED 그룹 셀 = null(hatch). 셀 툴팁 "p=…, n=…, net=…".
- 기존 테이블은 유지(접근성 table view). 테이블의 percentile 컬럼을 **NullDistribution 미니 strip**으로
  교체(non-blocked 행). 
- BH-FDR 풀 요약은 기존대로.
- 색: 범례에 seq 램프 의미("진함=유의") 명시.
- [ ] `npx tsc --noEmit` 클린 + `validate_palette.js` 재확인. 커밋.

---

### Task 4: 시각 스모크(유저, 맥)
- `/validation` 페이지 하단 엣지검증 섹션에 heatmap + strip 렌더 확인, 라벨충돌/오버플로우 눈으로.

## Self-Review Notes
- 스펙 §4 램프 ↔ Task1 토큰 ↔ Task2 colorOf 일치. 상태색 재사용 없음(신설 chart-*/seq-*).
- 신규 백엔드 없음(기존 엔드포인트 소비). 테이블 유지(접근성). one-axis(heatmap·strip 단일 축).
- 검증경계: 전 태스크 tsc + 색검증. 시각 렌더는 맥 스모크(Task4).
