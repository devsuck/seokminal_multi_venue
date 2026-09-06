# console_api.py 엔드포인트 전수 감사 (2026-09-06)

**요약:** 전체 `@router.get` 엔드포인트 107개 중 사전 확인된 3개(macro-intelligence/insider-flow-live/dart-events-live)를 제외한 **104개**를 감사. `data_source` 분포 — **REAL 76 / MIXED 14 / DEMO 14**. `trading_relevant=YES`이면서 `data_source`가 REAL/MIXED인 후보는 **5개** (`/fusion`, `/overlay`, `/investment-os`, `/forward-learning`, `/monthly-review`) — 전부 전략 단위(strategy-level)이며 개별 종목 필터 쿼리파라미터는 없음.

**정정 이력(2026-09-06 리뷰 반영):** `/data-health`를 DEMO→REAL, `/market-cockpit`을 DEMO→MIXED로 정정. 근거는 각 행의 notes 참조. 최초 감사 방법론의 맹점 — "backing 함수가 빈 인자(`{}`)로 호출된다"는 사실만으로 DEMO 처리하고, 그 함수 내부에서 실제로 무엇을 계산하는지 재확인하지 않은 것 — 을 교정하기 위해 유사 패턴(호출부에서 하드코딩된 빈/기본 인자를 넘기는 엔드포인트) 전체를 재점검함. 상세는 표 하단 "정정 내역" 절 참조.

## 조사 방법 및 판정 기준

- `grep -n '@router\.get' api_server/console_api.py` (107건) 기준, 핸들러 함수 본문을 전부 읽고 backing 함수를 추적.
- **REAL**: `jarvis.registry` / `jarvis.*_execution.ledger` / `jarvis.audit` / `jarvis.research_workflow.*` 등 실제 원장·레지스트리·자격증명(env) 상태를 읽어 값을 도출. 대부분 **jarvis 내부 시스템 상태(governance/registry/ledger)** 이지 외부 시장데이터가 아님 — 존재는 실측이나 트레이딩 신호로서의 정보가치는 별개 문제.
- **DEMO**: 핸들러 또는 backing 모듈에 하드코딩된 dict/리스트 상수를 그대로(또는 거의 그대로) 반환. 예: `_DEMO_BT`/`_DEMO_PAPER`, `demo=True` 플래그, 하드코딩된 `financials=[{"expected":{"eps":0.5},"actual":{"eps":0.62}}]`, 하드코딩된 상관계수(`{"AAPL~SPY":0.72}`), 정적 seed 딕셔너리(`_SECTOR_SEED`, `ALT_SOURCES`, `AGENT_CAPABILITY_MAP`), 또는 항상 빈 인자(`discover({})`, `build_market_cockpit({},{})`)로 호출되어 구조적으로 비어있음.
- **MIXED**: 여러 하위 호출을 합성하는 aggregator 엔드포인트에서 일부는 REAL(레지스트리/원장), 일부는 DEMO(하드코딩) 조합인 경우. 또는 실측 감지기가 있으나 데이터 없으면 정직하게 UNKNOWN으로 폴백하는 경우.
- **symbol_scoped**: 쿼리파라미터로 개별 종목/기업(ticker·company·entity)을 필터링할 수 있으면 YES. sector/topic/q(자유텍스트)는 종목 단위가 아니므로 NO.
- **trading_relevant**: 개별 종목 매수/매도 판단에 실제 정보가치가 있으면 YES. 순수 거버넌스/운영모니터링/메타연구 프로세스 대시보드는 NO. 하드코딩된 가짜 재무(eps 등)로 감싸진 경우, 겉보기엔 symbol_scoped=YES여도 정보가치가 없으므로 trading_relevant는 NO로 판정.
- 애매한 경우 backing 모듈(`jarvis/research_workflow/*.py`, `jarvis/investment_os/*.py`)까지 직접 열어 확인함 (약 20개 모듈 직접 검증: `sector_intelligence.py`, `alt_data.py`, `providers.py`, `data_production.py`, `opportunity_discovery.py`, `news_intelligence.py`, `agent_capability.py`, `institutional_memory_expansion.py`, `data_connection.py`, `investment_os/knowledge_consumer.py`, `decision_support.py`, `explainability.py`, `research_context_engine.py`, `conviction_framework.py`, `debate_engine.py`, `investment_committee.py`, `human_decision_center.py`, `semantic_recall.py`, `council_evolution.py`, `research_trigger.py`, `hypothesis_discovery.py` 등). 그 외 다수는 console_api.py 호출부 패턴(하드코딩 리터럴 유무·실 registry/ledger import 유무)으로 판정 — 표의 notes에 "패턴 기반, 미상세 확인"으로 표시.
- 제외 3건(이미 확인 완료): `/macro-intelligence`(FRED 실측 + demo 폴백 = MIXED), `/insider-flow-live`(OpenInsider 실측 캐시 = REAL), `/dart-events-live`(OpenDART 실측 캐시 = REAL).

## 감사 표

| endpoint | backing_module | data_source | symbol_scoped | trading_relevant | notes |
|---|---|---|---|---|---|
| `/status` | `jarvis.status`, `jarvis.registry.StrategyRegistry`, `jarvis.paper_execution.ledger` | REAL | NO | NO | 거버넌스/자본 요약, 이미 실배선. 종목 개념 없음. |
| `/regime` | `jarvis.portfolio.regime.detect_regime` + registry 파생 posture | MIXED | NO | NO | 레짐 감지기 미구성 시 정직하게 UNKNOWN. posture는 레지스트리 실측 파생이나 포트폴리오 단위. |
| `/pipeline` | `jarvis.*_execution/*.ledger` (10단계) | REAL | NO | NO | P8 집행 파이프라인 원장 카운트(거버넌스). |
| `/council` | `jarvis.portfolio.journal.read_latest` / `jarvis.audit.tail` | REAL | NO | NO | 포트폴리오 결정 로그/감사 tail. 종목 시그널 아님. |
| `/strategies` | `jarvis.registry.StrategyRegistry` | REAL | NO | NO | 전략 DNA 목록(전략 단위). |
| `/strategies/{sid}` | registry + `research.agents.experiment_registry` | REAL | NO | NO | 전략 단위 상세, sid는 종목 아님. |
| `/experiments` | `research.agents.experiment_registry.load_all` | REAL | NO | NO | 실험 원장 실측. |
| `/validation` | `jarvis.redteam.review.audit_registry` + experiment_registry | REAL | NO | NO | 검증 리포트, 전략 단위. |
| `/agents` | jarvis 여러 서브시스템 실상태 조합 | REAL | NO | NO | AI Council 조직도(거버넌스 트리). |
| `/logs` | `jarvis.audit.tail` | REAL | NO | NO | 원시 감사 로그. |
| `/knowledge` | registry 파생 그래프 + `jarvis.knowledge.query.find_failed_strategies` | REAL | NO | NO | 전략·팩터 관계 그래프, 종목 아님. |
| `/research` | `jarvis.planner.query.latest_proposals` + registry 커버리지 갭 | REAL | NO | NO | proposals 비어있을 수 있음(정직). |
| `/market` | registry 파생 팩터 posture + `regime()` | REAL | NO | NO | 포트폴리오 posture, 종목 랭킹 아님. |
| `/allocation` | `jarvis.portfolio.allocation_ledger`/`journal` + registry 동일비중 파생 | REAL | NO | NO | 전략별 배분(제안 전용), 종목 배분 아님. |
| `/fusion` | `jarvis.fusion.ledger.read_latest` | REAL | NO | **YES** | 합성 트레이드 시그널 원장 — CLI 미실행 시 비어있음. symbol 쿼리파라미터 추가하면 종목단위 배선 용이. |
| `/overlay` | `jarvis.portfolio.journal` + `jarvis.portfolio.signal_overlay.compute_overlay` | REAL | NO | **YES** | 전략비중×종목신호 합성(journal 있을 때만). symbol 필터 파라미터 없음. |
| `/positions` | `jarvis.paper_execution.ledger.current_positions` | REAL | NO | NO | 페이퍼 포지션 모니터링. 데이터는 종목별이나 필터 파라미터 없고 목적이 모니터링. |
| `/risk` | `jarvis.risk.governor.RiskLimits` + `execution_risk.ledger` | REAL | NO | NO | 리스크 거버너 상태(포트폴리오 단위). |
| `/orders` | `jarvis.live_execution.ledger` + `order_lifecycle.ledger` | REAL | NO | NO | 라이브 주문 원장, 자본경계 CLOSED로 대개 비어있음. |
| `/broker` | `jarvis.broker_readonly.adapters`, `jarvis.live_execution.adapters` health_check | REAL | NO | NO | 브로커/집행 어댑터 헬스(인프라 상태). |
| `/monitor` | `pipeline()` + `status()` 조합 | REAL | NO | NO | 집행 모니터 상세. |
| `/research-os` | `jarvis.research_navigation/integration_audit/local_runtime/research_assistant/local_automation` | REAL | NO | NO | 코드베이스 자기소개(모듈수·헬스·커버리지). 트레이딩과 무관. |
| `/assistant` | `jarvis.research_assistant.engine.ResearchAssistantEngine` | REAL | NO | NO | 자연어 Q&A, 실 레코드 기반 회상이나 메타 어시스턴트. |
| `/failure-intel` | `ResearchAssistantEngine.failure_intelligence/memory_graph/perspectives` | REAL | NO | NO | 실패 분류·메모리 그래프(실측 레코드). |
| `/research-workflow` | `jarvis.research_workflow` ledger/orchestrator/session_manager/research_queue | REAL | NO | NO | 워크플로/세션/큐 조율 상태. |
| `/research-strategy-generation` | `jarvis.research_strategy_generation` ledger + engine | REAL | NO | NO | 후보 생성 원장(candidate ≠ strategy). |
| `/decision-memo` | `jarvis.research_workflow.decision_support.DecisionSupportEngine` | REAL | NO | NO | `assistant.recall()`로 실측 회상 종합. q 자유텍스트, 공식 symbol 파라미터 아님. |
| `/explainability` | `jarvis.research_workflow.explainability.ExplainabilityEngine` | REAL | NO | NO | 증거사슬, recall 기반 실측. |
| `/operating-console` | research_assistant + research_queue + `event_intelligence`(정적 참조그래프) + paper_execution + session_manager + council | MIXED | NO | NO | 대부분 실측 집계이나 이벤트 관계 그래프는 정적 참조 데이터. |
| `/autonomous-runtime` | `hypothesis_generator/experiment_planner/research_critic/research_prioritizer`(q 기반 생성) + `research_workflow.ledger`(loops 실측) | MIXED | NO | NO | loops는 실 원장, preview(가설 생성)는 registry 의존 낮은 프레임워크. |
| `/research-timeline` | `jarvis.research_workflow.timeline.build_timeline` | REAL | NO | NO | append-only 원장 재구성. |
| `/research-graph` | `jarvis.research_workflow.knowledge_graph.build_knowledge_graph` (memory_graph + relationship_graph) | MIXED | NO | NO | relationship_graph 부분은 정적 참조 그래프 가능성(미상세 확인). |
| `/research-health` | `jarvis.research_workflow.health_monitor.build_health` | REAL | NO | NO | 결정적 운영 건강 지표. |
| `/continuous-learning` | `jarvis.research_workflow.continuous_learning.learning_status` | REAL | NO | NO | 메모리 채널 축적량. |
| `/research-quality` | `jarvis.research_workflow.quality_score.score_research` + `_strategy_metrics()`(실 `jarvis.experiment_tracking` 원장) | REAL | NO | NO | q=전략명(종목 아님), 실험 원장 기반 채점. |
| `/cross-strategy` | `jarvis.research_ingestion.ledger` + `jarvis.research_workflow.cross_strategy.compare_all` | REAL | NO | NO | 전략 간 쌍별 비교, 실 원장 기반. |
| `/cockpit` | `jarvis.research_workflow.cockpit.build_cockpit` | REAL | NO | NO | 역량 통합 홈(내부 집계, 패턴 기반 판정). |
| `/market-regime` | `jarvis.research_workflow.regime.detect_regime(indicators)` | MIXED | NO | NO | indicators 없으면 정직하게 UNKNOWN(사실상 상시 UNKNOWN에 가까움). |
| `/opportunity-queue` | `jarvis.research_workflow.opportunity_discovery.discover({})` | DEMO | NO | NO | 항상 빈 dict로 호출 — 구조적으로 count=0 stub. 상류 이상탐지 신호 미연결. |
| `/alt-data` | `jarvis.research_workflow.alt_data.catalog()` | DEMO | NO | NO | 정적 하드코딩 소스 카탈로그(`ALT_SOURCES`), 실 관측 없음. |
| `/council-expanded` | `jarvis.research_workflow.council_evolution.deliberate(q)` | REAL | NO | NO | `assistant.recall`/`mistake_check` 실측 결합, 7관점 논거 생성. |
| `/strategy-lab` | `jarvis.research_workflow.strategy_lab.strategy_dna/repeated_mistakes` + `_strategy_metrics()`(실 원장) | REAL | NO | NO | q=전략명, 실험 원장 기반. |
| `/market-cockpit` | `jarvis.research_workflow.market_cockpit.build_market_cockpit({}, {})` | MIXED | NO | NO | 정정(리뷰 반영): `indicators`/`signals`가 `{}`로 고정돼 `market_state`(UNKNOWN)·`research_opportunities`(빈 리스트)만 구조적으로 비지만, 응답 대부분(active_experiments/validation_status/risk/portfolio_context/decision_queue/knowledge_growth/timeline/health_score 등)은 인자와 무관하게 `cockpit.build_cockpit()`(REAL)을 그대로 반환 — DEMO 아니라 MIXED. |
| `/news-intel` | `jarvis.research_workflow.news_intelligence.analyze_headline(q)` | DEMO | NO | NO | 키워드 기반 분류기 + 정적 관계그래프. 실 뉴스 피드 수집 없음(호출자가 텍스트 직접 입력). |
| `/supply-chain-impact` | `jarvis.research_workflow.supply_chain_impact.propagate` | DEMO | NO | NO | 정적 공급망/기업 관계 참조 그래프("정적 공급망 그래프" — 코드 주석 명시). |
| `/earnings-intel` | 없음(백킹 모듈 미연결) | DEMO | NO | NO | 하드코딩된 스텁 note+필드 스키마만 반환. "데이터 소스 연결 시 채워짐"이라 코드에 명시. |
| `/market-intel-feed` | news_intel(DEMO) + supply_chain(DEMO) + regime(MIXED) + opportunity_discovery(DEMO, 항상 `{}`) | MIXED | NO | NO | 대부분 구성요소가 DEMO/stub. q 없으면 피드 빈값(정직). |
| `/research-trigger` | `jarvis.research_workflow.research_trigger.dispatch` (`event_stream.classify_event` + recall 실측) | REAL | NO | NO | entity/q 자유텍스트, 트레이드 신호 아님(연구 태스크 체인). |
| `/strategy-lifecycle` | `jarvis.research_workflow.strategy_lifecycle.board` | REAL | NO | NO | 기존 원장 파생 생애주기 보드. |
| `/research-ops-events` | `jarvis.research_workflow.ops_events.ops_events` | REAL | NO | NO | 이벤트 계층 파생(가설·백테스트·검증실패 등). |
| `/research-audit` | `jarvis.research_workflow.research_audit.audit_coverage/audit_strategy` | REAL | NO | NO | strategy 파라미터는 전략명(종목 아님). append-only 원장 재구성. |
| `/v2-release` | `jarvis.research_workflow.release_validation.validate_release` | REAL | NO | NO | 릴리스 검증(내부 안전점검). |
| `/validation-loop` | lifecycle/ops(REAL) + `_DEMO_BT`/`_DEMO_PAPER`(코드에 `is_demo: True` 명시) | MIXED | NO | NO | validation/quality 패널은 명시적 데모 백테스트·페이퍼 지표로 시연. |
| `/data-capability-map` | `jarvis.research_workflow.providers.provider_registry` | REAL | NO | NO | 정적 카탈로그 + 실측 env credential 체크(available/not_configured). 인프라 상태. |
| `/data-health` | `jarvis.research_workflow.data_quality.build_data_health()` (인자 없이 호출) | REAL | NO | NO | 정정(리뷰 반영): `series_by_source`/`rows_by_source` 미주입이라 freshness/schema 서브리포트만 빈 리스트지만, `overall_status`/`api_availability`는 `providers.provider_registry()`(실측 env credential 체크) 기반 `avail_ratio`로 결정적 계산됨(`/data-capability-map`과 동일 소스) — 하드코딩 아님. |
| `/research-feed` | `jarvis.research_workflow.research_feed.collect(demo)` | DEMO | NO | NO | `demo = {"market":[{"asset":"AAPL",...}], "news":[...]}` 하드코딩 변수명 자체가 demo. |
| `/live-intelligence` | `jarvis.research_workflow.live_intelligence.build_live_intelligence(demo=True)` | DEMO | NO | NO | 파라미터명 자체가 `demo=True`. |
| `/operational-validation` | `jarvis.research_workflow.operational_validation.validate_operations` | REAL | NO | NO | 아키텍처 안전 검증(내부). |
| `/agent-capability-map` | `jarvis.research_workflow.agent_capability.AGENT_CAPABILITY_MAP`(직접 확인) | DEMO | NO | NO | 정적 튜플 문서(역할·입출력·사용엔진 하드코딩). 실측 없음. |
| `/agent-validation` | `jarvis.research_workflow.agent_validation.validate_agents` | REAL | NO | NO | 에이전트 시스템 검증(내부). |
| `/agent-workspace` | `agent_capability.capability_map`(DEMO) + `multi_agent_workflow.run(objective 기본값, company)` | MIXED | YES(company) | NO | objective 없으면 코드가 `is_demo: True`로 명시. company 있어도 데모 objective 기본값이면 실질 신호 없음. |
| `/memory-audit` | `jarvis.research_workflow.memory_audit.audit_memory` | REAL | NO | NO | rmi_/memory_graph 등 실측 저장소 감사. |
| `/knowledge-graph` | `jarvis.research_workflow.knowledge_graph_upgrade.build_research_knowledge_graph` | REAL | NO | NO | 레지스트리+실험 확장 그래프. |
| `/semantic-recall` | `jarvis.research_workflow.semantic_recall.recall_context`(직접 확인, `assistant.recall` 실측 원장) | REAL | NO | NO | 실 expt_/rmi_/ring_ 원장 회수. |
| `/knowledge-conflicts` | `jarvis.research_workflow.conflict_detection.detect_conflicts` | REAL | NO | NO | 지식 모순 탐지(패턴 기반, 미상세 확인이나 지식원장 의존 구조 확인). |
| `/knowledge-health` | `jarvis.research_workflow.knowledge_quality.build_knowledge_health` | REAL | NO | NO | 지식 건강 점수(내부). |
| `/brain-validation` | `jarvis.research_workflow.brain_validation.validate_brain` | REAL | NO | NO | 연구 두뇌 검증(내부). |
| `/research-brain` | knowledge_graph_upgrade + memory_audit + conflict_detection + knowledge_quality + 실패패턴(assistant) | REAL | NO | NO | 지식 시스템 통합 뷰, 전부 실측 하위모듈. |
| `/research-schedule` | `jarvis.research_workflow.research_scheduler.plan_cycle` | REAL | NO | NO | 연구 운영 계획(패턴 기반, 미상세 확인). |
| `/morning-briefing` | `jarvis.research_workflow.morning_briefing.generate(events=demo_events)` | DEMO | NO | NO | `demo_events = [{"kind":"macro","text":"CPI surprise"},{"kind":"earnings","text":"NVDA earnings"}]` 하드코딩. |
| `/company-monitor` | `jarvis.research_workflow.company_monitor.update(name, financials=[하드코딩 eps 0.5/0.62], headlines=[템플릿 텍스트])` | DEMO | YES(company) | NO | company 파라미터가 있어도 재무/헤드라인이 항상 가짜값 — symbol_scoped처럼 보이나 정보가치 없음. |
| `/strategy-health` | `jarvis.research_workflow.strategy_health.StrategyHealthMonitor().board()` | REAL | NO | NO | 전략 건강 보드(패턴 기반, registry/experiment 의존 추정). |
| `/agent-performance` | `jarvis.research_workflow.agent_performance.report(objective="momentum research" 고정)` | MIXED | NO | NO | 리포트 메커니즘은 실측이나 objective가 고정값이라 실질 컨텍스트 없음. |
| `/research-workspace` | `jarvis.research_workflow.research_workspace.build_workspace` | REAL | NO | NO | inbox/review queue/agent outputs(내부). |
| `/research-ops-validation` | `jarvis.research_workflow.ops_validation.validate_research_ops` | REAL | NO | NO | v1.5 검증(내부). |
| `/research-organization` | briefing(DEMO) + company_monitor(DEMO) + strategy_health(REAL) + agent_performance(MIXED) + knowledge_quality(REAL) + workspace(REAL) + ops_validation(REAL) | MIXED | NO | NO | 조합형 대시보드, 절반 이상 하드코딩 데모 조각 포함. |
| `/data-production` | `jarvis.research_workflow.data_production.build_data_production`(직접 확인) | REAL | NO | NO | provider 실측 env 체크 + freshness. 인프라 상태(트레이딩 신호 아님). |
| `/sector-intelligence` | `jarvis.research_workflow.sector_intelligence.analyze_sector`(직접 확인, `_SECTOR_SEED` 정적) | DEMO | NO | NO | 3개 섹터만 정적 seed(`semiconductor/ai_infra/tech`), 연구질문도 템플릿 문자열. |
| `/company-intelligence` | `jarvis.research_workflow.company_intelligence.analyze_company(entity, financials=[하드코딩], headlines=[템플릿])` | DEMO | YES(entity) | NO | company-monitor와 동일 패턴 — entity 있어도 재무 데이터가 가짜. |
| `/research-context` | `jarvis.research_workflow.research_context_engine.build_research_context` (semantic_recall 실측 + macro_intelligence 기본 `{}` + regime) | MIXED | YES(entity) | NO | recall 부분은 실측, macro 컨텍스트 부분은 인자 미주입으로 사실상 비어있음. |
| `/cross-asset` | `jarvis.research_workflow.cross_asset_intelligence.build_cross_asset(correlations=하드코딩)` | DEMO | NO | NO | `{"AAPL~SPY":0.72,"GLD~DXY":-0.58,"TLT~SPY":-0.35}` 하드코딩 상관계수. |
| `/institutional-memory` | `jarvis.research_workflow.institutional_memory_expansion.build_institutional_memory`(직접 확인, rmi_ 실측 재구성) | REAL | NO | NO | 테마 분류는 정적 키워드이나 원천 데이터는 실 rmi_ 레코드. |
| `/intelligence-quality` | `jarvis.research_workflow.intelligence_quality.score_intelligence` | REAL | NO | NO | data/evidence/historical/conflict 여러 실측 서브엔진 결합(패턴 기반). |
| `/intelligence-validation` | `jarvis.research_workflow.institutional_intelligence_validation.validate_intelligence` | REAL | NO | NO | 기관 인텔리전스 검증(내부). |
| `/institutional-intelligence` | data_production(REAL) + regime(REAL/UNKNOWN) + sector_intelligence(DEMO) + macro_intelligence(하드코딩 5.0/3.5/4.2, FRED 미사용) + company_intelligence(DEMO) + knowledge_quality(REAL) + intelligence_quality(REAL) + validation(REAL) | MIXED | YES(entity 기본 TSMC) | NO | `/macro-intelligence`와 달리 여기선 FRED 실측 fetch 없이 항상 하드코딩 매크로 수치 사용. |
| `/committee-packet` | `jarvis.research_workflow.investment_committee.build_committee_packet(q)`(decision_center/debate_engine 등 recall 기반) | REAL | NO | NO | q 있으면 실측 회상 종합. BUY/SELL 없음. |
| `/debate` | `jarvis.research_workflow.debate_engine.build_debate(q)`(직접 확인, `semantic_recall` 실측 결합) | REAL | NO | NO | 강세/약세/리스크 논거, 실 회상 기반. |
| `/conviction` | `jarvis.research_workflow.conviction_framework.build_conviction(topic)`(직접 확인, intelligence_quality/recall/quality_monitor/conflict_detection 실측 결합) | REAL | NO | NO | 6요인 확신도 프레임워크, 실측 하위모듈. |
| `/portfolio-research` | `jarvis.research_workflow.portfolio_research_view.build_portfolio_research(correlations=하드코딩)` | DEMO | NO | NO | `{"AAPL~SPY":0.72,"GLD~DXY":-0.58}` 하드코딩. |
| `/decision-center` | `jarvis.research_workflow.human_decision_center.build_decision_center(q)`(직접 확인, investment_committee+ops_events+timeline 실측 결합) | REAL | NO | NO | committee packet·decision log·follow-up(내부). |
| `/production-status` | `jarvis.research_workflow.production_monitor.build_production_status` | REAL | NO | NO | 7 컴포넌트 severity(내부 운영). |
| `/operational-metrics` | `jarvis.research_workflow.operational_metrics.build_operational_metrics` | REAL | NO | NO | 처리량/지연/가용성(내부 운영). |
| `/governance` | `jarvis.research_workflow.governance.build_governance` | REAL | NO | NO | 권한/감사/무결성(내부). |
| `/system-validation` | `jarvis.research_workflow.system_validation.validate_system` | REAL | NO | NO | 전체 시스템 검증(내부). |
| `/release-v20` | `jarvis.research_workflow.release_v20.build_release_report` | REAL | NO | NO | 릴리스 준비도 리포트(내부, 일부 정적 capability_matrix 가능성). |
| `/production-readiness` | committee(REAL)+debate(REAL)+conviction(REAL)+portfolio(DEMO 하드코딩 상관)+governance(REAL)+production(REAL)+metrics(REAL)+release(REAL)+decision_center(REAL) | MIXED | NO | NO | 대부분 REAL 조각이나 portfolio_research 부분이 하드코딩. |
| `/research-intelligence` | creative_hypothesis/research_search/continuous_queue/experiment_prioritization/research_planning/productivity_optimization/self_reflection/autonomy_validation(직접 확인 일부, recall 기반) | REAL | NO | NO | 메타 연구 프로세스(가설·탐색·큐·우선순위), 종목 무관. |
| `/autonomous-research` | research_cycle/market_observation/hypothesis_discovery(직접 확인, recall 기반)/research_priority/research_gate/research_brief/research_metrics_v3/autonomous_validation_v3/release_v30 | REAL | NO | NO | v3.0 연구 자동화 루프(내부), 실행/거래 없음. |
| `/data-connection` | `jarvis.research_workflow.data_connection.data_connection_status`(직접 확인, 실측 credential 체크) + prediction_coverage_audit + research_validation_score | REAL | NO | NO | KRX/OpenDART/SEC-EDGAR 연결 상태, 없으면 정직하게 NEEDS_CREDENTIALS. 인프라. |
| `/research-factory` | `jarvis.research_workflow.research_factory.run_on_registry` | REAL | NO | NO | 실 전략 레지스트리 이력에 REJECT 깔때기 적용. 전략 단위. |
| `/research-accountability` | `jarvis.research_workflow.research_accountability.accountability_report` | REAL | NO | NO | batting average/edge score(실측 레지스트리/예측원장 기반). 전략 단위. |
| `/investment-os` | `jarvis.investment_os`(`consume_research`/`construct_portfolio`/`analyze_exposure`/`build_risk_budget`/`analyze_scenarios`/`check_compliance`/`evaluate_gates`/`recommend_position_sizes`)(직접 확인, `knowledge_consumer.py` 실 registry 기반) | REAL | NO | **YES** | 실 전략 후보(paper_active 등)에서 포트폴리오 구성·포지션사이징 추천 — 전략 단위 실질 정보가치 있음. symbol 필터 파라미터는 없음. |
| `/forward-learning` | `jarvis.investment_os.build_forward_learning_records` | REAL | NO | **YES** | registry/experiment_registry/prediction_registry/paper.deploy 조인 — thesis vs 실제결과 추적. 전략 단위. |
| `/monthly-review` | `jarvis.investment_os.build_monthly_review` | REAL | NO | **YES** | KEEP/WATCH/PAUSE/REJECT 제안(전략 단위), 기존 실데이터 재사용. |

## 배선 우선순위 후보 (Task 3+ 참고용)

trading_relevant=YES + REAL/MIXED 후보 5개는 전부 **전략 단위**이며 **종목 단위 쿼리파라미터가 없다**는 공통점이 있음:

1. `/fusion`, `/overlay` — 원장이 채워지려면 오프라인 CLI(퓨전 계산/오케스트레이터 evaluate)가 먼저 실행되어야 함. symbol 필터 추가는 코드 한 줄 수준(난이도 낮음)이나, 원장 자체가 비어있는 게 선결 문제.
2. `/investment-os`, `/forward-learning`, `/monthly-review` — 이미 실 레지스트리/실험/예측 원장을 조인하는 성숙한 모듈(`jarvis/investment_os/`). symbol 단위로 세분화하려면 candidate 구조에 종목 필드를 추가해야 함(전략이 다종목 유니버스를 다루는 경우 전략:종목 매핑이 필요) — 중간 난이도.

나머지 99개 엔드포인트는 (a) 순수 거버넌스/운영모니터링/메타연구 프로세스(REAL이지만 종목과 무관), (b) 하드코딩된 데모 데이터로 감싸인 프레임워크(DEMO), 또는 (c) 그 혼합(MIXED)이다. 특히 `/sector-intelligence`, `/company-intelligence`, `/company-monitor`는 종목/섹터 파라미터가 있어 symbol_scoped처럼 보이지만 재무 데이터가 하드코딩 가짜값(`eps: 0.5/0.62` 등)이라 trading_relevant=NO로 판정했다 — 이 3개는 실제 재무 데이터 소스(SEC-EDGAR/OpenDART/data.go.kr — `providers.py`의 `PROVIDER_CATALOG`에 이미 목록화됨)만 연결하면 빠르게 REAL로 전환 가능해 보인다.

## 정정 내역 (2026-09-06, 리뷰 반영)

리뷰어가 `/data-health` 판정 오류를 지적함: 최초 감사는 "backing 함수가 빈/기본 인자로 호출된다"는 호출부 패턴만 보고 DEMO로 분류했는데, 실제로는 함수 내부에서 `providers.provider_registry()`(실측 env-credential 체크)를 사용해 `overall_status`를 결정적으로 계산하고 있어 REAL이 맞음. 이 지적을 계기로 같은 실수 패턴(호출부가 빈/기본 인자를 넘긴다는 이유만으로 DEMO 처리하고, backing 함수 내부에서 그 인자와 무관하게 실측 데이터를 쓰는지는 재확인하지 않음)이 있는지 `market_cockpit.py`(비슷하게 `{}, {}` 인자로 호출됨) · `opportunity_discovery.py`(`discover({})`)를 다시 열어 재검증함.

- **`/data-health`: DEMO → REAL.** `build_data_health()`는 인자가 없어도 `provider_registry()` 기반 `avail_ratio`로 `overall_status`(HEALTHY/DEGRADED/LIMITED)를 실측 계산한다(`/data-capability-map`과 동일 근거). `series_by_source`/`rows_by_source` 미주입으로 비는 건 freshness/schema 서브리포트뿐.
- **`/market-cockpit`: DEMO → MIXED.** `build_market_cockpit({}, {})`는 인자와 무관하게 `cockpit.build_cockpit()`(REAL)의 대부분 필드를 그대로 반환한다. `indicators`/`signals`가 `{}`라서 비는 건 `market_state`(UNKNOWN)와 `research_opportunities`(빈 리스트) 두 필드뿐 — 응답의 절반 이상은 실측.
- **`/opportunity-queue`: DEMO 유지(재확인 완료, 오분류 아님).** `discover(signals)`는 `signals.items()`를 순회하는 구조라 `discover({})`는 정말로 아무 조각도 만들지 않고 `count=0`을 반환한다 — market-cockpit과 달리 "인자와 무관하게 실측을 섞어 반환하는 다른 경로"가 없는 순수 구조적 stub이 맞음.

이 두 건 수정으로 요약 카운트가 REAL 75→76, DEMO 16→14, MIXED 13→14로 변경됨(총 104 불변). trading_relevant=YES 후보 5개는 두 행 모두 NO라 영향 없음.

**남은 우려**: "패턴 기반, 미상세 확인"으로 표시한 다른 REAL/MIXED 행들(예: `/research-graph`, `/cockpit`, `/strategy-health`, `/knowledge-conflicts` 등)도 같은 방식(호출부 인자 패턴만 보고 판정)의 위험이 남아있을 수 있어, 실제 배선(Task 3+) 전 해당 backing 모듈 소스를 직접 열어 재확인할 것을 권장.
