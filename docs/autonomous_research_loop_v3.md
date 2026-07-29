# Jarvis Autonomous Research OS v3.0 (P181–P200)

> v2.0 위에 **지속 운영 가능한 Autonomous Research Organization** 을 구축한다.
> "자동 투자 시스템"이 아니라 "스스로 연구 주제를 발견·가설 생성·검증 우선순위를 정하고 **사람에게 검토를
> 요청**하는 AI Research Organization". 새 DB/ledger/memory/vector/execution/backtest 엔진 **금지** — 기존 조율만.

## 연구 루프

```
Observation → Opportunity → Hypothesis → Experiment Proposal → ★ Human Checkpoint ★
   → External Test → Validation → Ranking → Knowledge Update → Next Cycle
```

★ **Human Checkpoint 에서 정지**한다. 사람이 "외부 테스트 요청"을 승인해야 External Test 로 진입한다.
**자동 백테스트 없음. 승인은 실행 명령이 아니다.**

## 모듈 (모두 `jarvis/research_workflow/`, 기존 엔진 재사용)

| P | 모듈 | 하는 일 | 재사용 |
|---|---|---|---|
| 181 | `research_cycle` | 루프 상태기계(CREATED→…→WAITING_HUMAN→…→COMPLETED), 사람 게이트 | market_observation·hypothesis_discovery·research_priority |
| 182 | `market_observation` | 시장 변화 → Research Opportunity(Signal 아님, BUY/SELL/LONG/SHORT/ALLOCATE 없음) | regime·macro·sector_intelligence |
| 183 | `hypothesis_discovery` | 창의적 가설 v2 — recall-first, 과거 실패 유사 시 "왜 이번엔 다른지" 필수 | creative_hypothesis·semantic_recall |
| 184 | `experiment_designer` | Hypothesis → Experiment Proposal + info_gain·complexity·expected_value | experiment_planner |
| 185 | `research_priority` | Priority = novelty+evidence+data+info_gain+gap−complexity−dup, 각 항목 근거 | experiment_prioritization·semantic_recall |
| 186 | `research_gate` | 사람 승인 큐(APPROVE/REJECT/MODIFY). **APPROVE=외부 테스트 허용, 실행 아님** | backtest_bridge(WAITING_HUMAN 전이만) |
| 187 | `validation_intelligence` | Backtest/Paper/Forward 5갭 → ROBUST/QUESTIONABLE/FAILED + 실패이유 | validation_gap·paper_validation |
| 188 | `research_selection` | 6기준 연구 품질 → Strong/Medium/Weak/Rejected (**투자 추천 아님**) | quality_monitor·validation_intelligence |
| 189 | `research_brief` | Daily Brief 7섹션 | morning_briefing·market_observation·research_gate |
| 190 | `research_loop_v3` | 전체 루프 조율, Human Checkpoint 정지 | research_cycle·gate·validation·selection·continuous_learning |
| 196 | `research_metrics_v3` | 7지표(생성가설·완료실험·검증성공률·중복회피·재사용·실패예방…) | research_ingestion·knowledge_quality |
| 197 | `research_reflection` | 5문 성찰, **학습은 continuous_learning — 새 메모리 없음** | continuous_learning·self_reflection |
| 198-199 | `autonomous_validation_v3` | 루프 9단계 동작 검증 + 생산 감사(중복/실행/브로커/결정성/재현성/감사추적) | governance·ledger |
| 200 | `release_v30` | 최종 릴리스 리포트 | autonomous_validation_v3·governance·release_v20 |

## Jarvis can / cannot (P200)

**CAN**: observe markets · discover opportunities · create hypotheses · design experiments ·
prioritize research · request human validation · analyze results · rank evidence quality ·
write reports · learn from failures.

**CANNOT**: ✗ trade · ✗ execute orders · ✗ allocate capital · ✗ approve investments.

## 안전 불변식 (P198-199 검증)

- 실행/브로커 import 0 · trade/execute/place_order/allocate/approve def 0 (AST 강제)
- **ledger count == 3** 유지 · 중복 엔진(`*Engine`)/원장(`append_*`) 0
- 자동 백테스트 없음 · **WAITING_HUMAN 체크포인트 유지** · APPROVE ≠ 실행
- 모든 산출 `is_advisory=True · is_decision=False · requires_human_review=True`
- 결정적·재현적(hash id, 주입 timestamp) · 감사추적 보존(governance COMPLIANT)

## 콘솔 (READ ONLY)

`GET /console/autonomous-research?q=<질문>` — 사이클·기회·가설·실험큐·검증·랭킹·사람 검토큐·지표·릴리스 v3.0.
대시보드: `/research-os/discovery`.

## 릴리스 상태

```
Jarvis Autonomous Research OS v3.0
Status: Production Ready
Research Automation: Enabled
Human Governance: Required
Execution: Disabled
Decision Authority: Human Only
```

**P200 이후 아키텍처 동결 — 신규 지능 패밀리 없음.** operations·data quality·model improvement·research outcomes 에 집중.
