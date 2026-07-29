# Dashboard Consolidation Plan (P207) — Migration Inventory ONLY

> **UI 구현 없음.** 21 페이지 → 5 페이지 마이그레이션 인벤토리만. 기관도 화면 21개를 순회하지 않는다.
> 실제 사용자는 아침에 "오늘의 리서치 브리프" 한 화면을 본다.

## 현재 21 페이지

`agents · autonomous · brain · chat · cockpit · committee · console · discovery · explain · graph ·
intel-feed · intelligence · intelligence-plus · live-intelligence · market · organization · production ·
strategy-lab · timeline · validation · workflow`

## 목표 5 페이지 (역할·흐름 기준)

| # | 통합 페이지 | 흡수하는 기존 페이지 | 소비 엔드포인트(기존) |
|---|---|---|---|
| 1 | **Brief** (랜딩) | cockpit · console · chat | `/console/status`, research brief |
| 2 | **Discovery** | discovery · autonomous · intelligence-plus · strategy-lab · workflow | `/console/autonomous-research`, `/console/research-intelligence` |
| 3 | **Intelligence** | intelligence · market · intel-feed · live-intelligence | `/console/live-intelligence` 등 |
| 4 | **Brain** | brain · graph · timeline · explain · validation | `/console/brain`, `/console/graph` |
| 5 | **Committee & Governance** | committee · production · organization · agents | `/console/production-readiness`, `/console/governance` |

**커버리지: 21/21** (모든 기존 페이지가 5개 중 하나로 흡수됨. 유실 없음.)

## Brief(랜딩) 구성 — 사용자가 아침에 보는 것

```
1. 중요한 시장 변화        (market_observation)
2. 새 연구 발견            (research_discovery / autonomous-research)
3. 검토 필요한 실험        (research_gate 큐)
4. 실패한 연구 교훈        (research_ingestion / reflection)
5. 내가 봐야 하는 것       (human review queue + prediction coverage)
```

## 마이그레이션 원칙 (실제 구현 시)

- **삭제 대신 리다이렉트** — 기존 21 경로는 ≥1 릴리스 동안 5개 통합 페이지로 redirect 유지(북마크·문서 의존).
- **컴포넌트 재사용** — 기존 패널/위젯(Panel·StatTile·Badge) 그대로, 페이지만 통합.
- **엔드포인트 무변경** — 백엔드 `/console/*` read-only 표면은 그대로. 프론트 통합만.
- **한 번에 하나씩** — 5개를 한꺼번에 말고 Brief → Discovery → … 순차. 각 단계 후 배포·확인.

## 성공 지표

```
Before: 21 pages
After:   5 pages (+ 21 redirects, ≥1 릴리스)
Coverage: 21/21 흡수
Endpoints: 무변경   Meaning: 무변경
```

**이 문서는 계획(inventory)일 뿐 — UI 구현은 별도 승인 후.**
