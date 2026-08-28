# Jarvis Research Loop + Investment OS 전면 부활

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**배경:** 2026-08-01 Phase1 STEP4 감사에서 jarvis 93개 모듈 중 32개(진짜 죽음, 콜러 0) 삭제 완료, 이번 세션에서 그 잔재(__pycache__ 껍데기) 마저 정리해 58개로 확정. 남은 58개 재감사 결과 `dart_autobot.py`/`polymarket_bot.py`는 jarvis를 아예 import 안 함(별개 시스템) — jarvis의 진짜 운영 표면은 `jarvis.boot()` + `/lab`,`/investment-os` 대시보드 페이지뿐. 그 안에서 2개 조각이 "죽은 게 아니라 데이터 쌓일 때까지 의도적으로 잠재운" 상태로 확인됨. 이제 부활.

**Goal:** (1) 히스토리 지식 기반 가설/후보 생성 레이어(`research_strategy_generation`, P29)를 실제 파이프라인에 연결하고, (2) `research/autoresearch`가 매일 만드는 BH-survivor 후보가 Investment OS 추천에 실제로 반영되도록 registry seed 로직의 root cause(1회성 가드)를 고친다. 둘 다 끝나면 `/investment-os` 페이지(이미 nav에 살아있음, 코드 변경 불필요)가 최신 데이터를 자동으로 보여준다.

**비목표(명시):** 실제 자본 집행 아님. `AUTO_EXECUTION_ENABLED=False`는 하드 불변식 — 이 계획에서 건드리지 않음. 브로커 연결·주문 라우팅 없음. 전부 추천/시뮬레이션(`is_advisory=True`, `is_decision=False`) 그대로 유지.

## Global Constraints

- Python: `/Library/Frameworks/Python.framework/Versions/3.14/bin/python3`
- pytest: `asyncio_mode="auto"`, `@pytest.mark.asyncio` 절대 금지
- Research OS 불변 원칙 유지: Investment OS는 Research 원장에 절대 안 씀(읽기전용), `separation.validate_separation()` 통과 유지 필수
- `jarvis.registry.StrategyRegistry`가 유일한 investment_os 데이터 소스 — 이 경로 벗어나지 말 것
- 프론트엔드 변경 시 디자인 토큰만 (`bg-bg/panel/panel-2`, `text-text-1/2/3`, `text-accent`), raw fetch 금지(`lib/api.ts`)
- pre-existing failures 없음(2026-07-30 기준) — 회귀 생기면 즉시 원인 규명

---

### Task 1: Registry seed 파이프라인 — root cause 고치기

**현황(확인됨):** `jarvis/registry/lifecycle.py:207 seed_from_experiment_registry()`가 `if reg.all_current(): return 0`으로 **1회성 가드** 걸려있음. `jarvis.registry`는 이미 61건(과거 1회 시드 완료) 있어서 매 boot마다 즉시 no-op. `research/autoresearch/engine.py`는 매일 `research.agents.experiment_registry.log_experiment()`로 신규 후보(어제 `fac_kr_size_smb`, n=82, p=0.0033, BH survivor, redteam CLEARED 포함)를 쌓지만 **jarvis.registry로 승격 안 됨** → `investment_os.knowledge_consumer.consume_research()`가 오래된 5건(paper_active 4 + watchlist 1)만 계속 봄.

**Files:**
- Modify: `jarvis/registry/lifecycle.py` (`seed_from_experiment_registry`)
- Modify or create test: `jarvis/registry/tests/test_lifecycle.py` (또는 기존 seed 테스트 파일)

**Design decisions:**
- 가드를 "registry 전체가 비었을 때만"에서 "이미 등록된 `hypothesis_id` 집합은 skip, 신규만 추가"로 바꾼다 — idempotent 유지, 1회성 제거. 기존 `register()`가 같은 id 중복 등록 시 어떻게 동작하는지 먼저 확인하고 그 동작에 맞춰 skip 조건 구현(중복 register 자체가 에러/무시라면 가드 없이도 안전할 수 있음 — 코드 보고 판단).
- `jarvis/__init__.py:16`에서 매 boot마다 호출되는 구조는 유지(스케줄러 새로 안 만듦) — boot마다 "신규만" 반영되면 충분.
- `research.agents.experiment_registry`의 verdict/status → registry lifecycle 상태 매핑은 기존 로직(blocked/rejected/candidate) 그대로 재사용, 새 매핑 규칙 추가 안 함.
- 회귀 확인: `investment_os` 테스트 11개, `separation.validate_separation()`, registry 관련 pytest 전부 통과 유지.

**검증:**
- [ ] `seed_from_experiment_registry()` 두 번 연속 호출해도 count 증가 없음(idempotent) 확인하는 테스트
- [ ] 신규 `hypothesis_id`가 experiment_registry에 추가된 후 seed 호출 시 그것만 추가되는지 확인
- [ ] `python3 -c "..."`로 `StrategyRegistry().all_current()`에 `fac_kr_size_smb` 계열 최근 후보 실제로 잡히는지 수동 확인
- [ ] `/console/investment-os` 응답(`api_server/console_api.py:2085`)에 신규 후보 반영 확인 (curl)
- [ ] 전체 pytest 회귀 없음

---

### Task 2: 히스토리 지식 기반 후보 생성 — `research_strategy_generation` 부활

**현황(확인됨):** `research_strategy_generation`(P29)은 append-only 이벤트소싱 **원장**이지 자동 생성기가 아님 — `generate_candidate(sess, category, statement, source_refs)`는 `statement`를 호출자가 직접 넣어야 함. 콜러 0(자기 테스트 제외). `research_discovery.generate()`(P204 파사드)는 이미 3가지 모드(recall_first/creative/template) 조율 중이며 그 중 `recall_first`(`hypothesis_discovery`, P183)가 "과거 실패 유사 시 왜 다른지" 근거를 문 뒤 후보를 냄 — 이게 "히스토리 지식" 소스로 재사용 가능한 유일하게 검증된 후보.

**Files:**
- Create: `jarvis/research_workflow/historical_candidate_bridge.py` (또는 팀 컨벤션에 맞는 이름 — recall_first 결과를 statement로 변환해 `research_strategy_generation`에 로깅하는 얇은 어댑터)
- Modify: `jarvis/research_workflow/research_discovery.py` (`generate()`에 `mode="historical"` 분기 추가)
- Modify: `jarvis/research_workflow/characterization.py` (`CALL_GRAPH_MODULES`에 반영 — Call Graph Golden 깨지지 않게)
- Modify: `jarvis/research_strategy_generation/__init__.py` 상단 `ARCHIVED` 마커 제거 + 상태 갱신(부활 사실 기록)
- Test: `jarvis/research_workflow/tests/test_research_discovery.py`, `jarvis/research_strategy_generation/tests/`

**Interfaces:**
- `historical_candidate_bridge.propose(topic: str, limit: int = 5) -> dict`
  1. `research_discovery.generate(topic, mode="recall_first", limit=limit)` 호출해 원시 후보 얻음
  2. 각 후보를 `statement`로 정리해 `research_strategy_generation.engine.ResearchStrategyGenerationEngine`의 `create_session → start_generating → generate_candidate(..., source_refs=[해당 recall_first 근거 id])` 순서로 로깅(append-only, commit=True)
  3. 반환 형식은 다른 3개 모드와 동일한 shape(`{"items":[...], "mode":"historical", ...}`)으로 맞춰 `generate()`에서 바로 합류 가능하게
- `research_discovery.generate(mode="historical")` → 위 브리지 호출

**Design decisions:**
- 새 지식 저장소 만들지 않는다 — P204 원칙("새 지능/저장소 없음") 그대로 준수. `research_strategy_generation`의 기존 원장(`rsg_` 접두사)에만 씀.
- `recall_first`를 소스로 고른 이유: 이미 "과거 대비 왜 다른가" 근거를 요구하는 유일한 모드라 P10~P28 히스토리 소비 원칙과 가장 맞음. `creative`/`template`는 대상에서 제외(스코프 커짐 방지).
- `ARCHIVED` 마커는 지우되 docstring에 "REVIVED 2026-08-20 — historical_candidate_bridge를 통해 research_discovery(mode=historical)에서 호출됨" 한 줄만 남김. 장문 설명 안 씀(기존 파일 문체 유지).

**검증:**
- [ ] `research_discovery.generate(topic="...", mode="historical")` 수동 호출 → `research_strategy_generation`의 세션/후보 원장에 실제로 이벤트 쌓이는지 확인
- [ ] `characterization.py` 골든 테스트(Call Graph) 안 깨지는지 확인
- [ ] `governance.validate_all()` 여전히 COMPLIANT
- [ ] Research OS 회귀 스위트 전체 통과(불변 원칙 위반 없음 — `separation.validate_separation()` 포함)

---

### Task 3: 확인만 — Investment OS 대시보드는 이미 살아있음

**현황(확인됨):** `/investment-os`, `/investment-os?tab=research` 둘 다 `CommandRail.tsx`에 이미 링크돼 있고 `app/hud/page.tsx`가 폴링도 함. Phase216에서 죽었다고 판정된 8개 콘솔 페이지와는 다른 페이지 — **오해였음, 코드 변경 불필요.**

**할 일:** Task 1 끝난 뒤 `/investment-os` 실제로 열어서 신규 후보(`fac_kr_size_smb` 등)가 화면에 뜨는지 브라우저로 눈으로 확인만.

- [ ] Task 1 배포 후 `/investment-os` 페이지 방문, 최신 BH-survivor 후보 렌더 확인
- [ ] 콘솔 API(`GET /console/investment-os`) 응답과 화면 표시가 일치하는지 확인

---

## SDD 파이프라인 순서

1. Task 1 → 2 순서로(1이 데이터 흐름 고치는 root fix라 더 검증 쉬움, 2는 신규 브리지라 1 위에서 눈으로 확인하며 만드는 게 안전)
2. 각 Task: implementer subagent → task reviewer → fix → re-review
3. 둘 다 끝나면 branch review, `docs/progress.md`에 Phase 항목 추가(완료 작업/변경 파일/다음 할 일)
