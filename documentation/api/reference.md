# API Reference

> 자동 생성(`python -m jarvis.documentation gen`) — 공개 모듈·클래스·함수·CLI 인트로스펙션.
> 관찰·분석·기록 전용. 실행·거래·배포 API 없음.

Total packages: **110**

## jarvis.access_governance

jarvis.access_governance — Access Governance & Operator Identity Layer (P9.10). **감사 전용.**

- module: `jarvis.access_governance` · CLI: `python -m jarvis.access_governance`
- classes: `AccessApproval`, `AccessAuditReport`, `AccessFinding`, `AccessGovernanceEngine`, `AccessGovernanceReport`, `AccessRequest`, `ApprovalError`, `IllegalTransition`, `ImmutableOperatorError`, `ImmutableRoleError`, `OperatorIdentity`, `RoleMetadata`, `SessionRecord`

## jarvis.adaptive_research_loop

jarvis.adaptive_research_loop — Adaptive Research Loop Layer (P12.4). **개선 기록 전용.**

- module: `jarvis.adaptive_research_loop` · CLI: `python -m jarvis.adaptive_research_loop`
- classes: `AdaptationRecord`, `AdaptiveResearchLoopEngine`, `EfficiencyMetricRecord`, `FeedbackRecord`, `ForbiddenModificationError`, `IllegalLoopTransition`, `ImmutableCycleError`, `ImmutableFeedbackError`, `ImmutableProposalError`, `InvalidCategory`, `InvalidDecision`, `LoopCycleRecord`, `LoopReportRecord`, `LoopSummary`, `MissingReviewError`, `ProposalEventRecord`, `UnknownCycleError`, `UnknownProposalError`

## jarvis.agent_governance

jarvis.agent_governance — Agent Research Governance Layer (P10.6). **연구 에이전트 관리·감사 전용.**

- module: `jarvis.agent_governance` · CLI: `python -m jarvis.agent_governance`
- classes: `AgentAction`, `AgentArtifact`, `AgentEvent`, `AgentGovernanceEngine`, `AgentGovernanceReport`, `BudgetRecord`, `Capability`, `ForbiddenCapability`, `HumanApprovalRequired`, `HumanReview`, `IllegalTransition`, `ImmutableAgentError`, `ImmutableRequestError`, `ProposalEvent`, `ResearchRequestEvent`, `UnknownProposal`

## jarvis.agents

Jarvis 에이전트 — 표준 principal(레벨 고정). AI는 자기 레벨 못 올린다.

- module: `jarvis.agents`
- classes: `Level`, `Principal`

## jarvis.alpha_intelligence

jarvis.alpha_intelligence — Alpha Discovery & Signal Intelligence Layer (P10.3). **연구 전용.**

- module: `jarvis.alpha_intelligence` · CLI: `python -m jarvis.alpha_intelligence`
- classes: `AlphaHypothesis`, `AlphaIntelligenceEngine`, `AlphaRanking`, `AlphaReport`, `FeatureDefinition`, `IllegalTransition`, `ImmutableFeatureError`, `ImmutableSignalError`, `ImmutableVersionError`, `SignalArtifact`, `SignalEvaluation`, `SignalExperiment`, `SignalMetadata`, `SignalVersion`

## jarvis.audit

Audit / Black Box — append-only 감사 로그. 삭제·수정 불가.

- module: `jarvis.audit`
- functions: `read_all`, `record`, `tail`

## jarvis.autonomous_experiment_scheduler

jarvis.autonomous_experiment_scheduler — Autonomous Experiment Scheduler Layer (P12.2). **스케줄·기록 전용.**

- module: `jarvis.autonomous_experiment_scheduler` · CLI: `python -m jarvis.autonomous_experiment_scheduler`
- classes: `AutonomousExperimentSchedulerEngine`, `CircularScheduleError`, `DanglingDependencyError`, `DependencyRecord`, `DuplicateRequestError`, `IllegalScheduleTransition`, `ImmutablePolicyError`, `ImmutableScheduleError`, `PolicyRecord`, `PriorityChangeError`, `PriorityRecord`, `ScheduleEventRecord`, `ScheduleRecord`, `ScheduleReportRecord`, `SchedulerSummary`, `SnapshotRecord`, `UnknownRequestError`, `UnknownScheduleError`

## jarvis.autonomous_research_evaluation

jarvis.autonomous_research_evaluation — Autonomous Research Evaluation Layer (P12.5). **평가·기록 전용.**

- module: `jarvis.autonomous_research_evaluation` · CLI: `python -m jarvis.autonomous_research_evaluation`
- classes: `ArtifactRecord`, `AutonomousResearchEvaluationEngine`, `BenchmarkRecord`, `CriterionRecord`, `EvaluationEventRecord`, `EvaluationSummary`, `IllegalEvalTransition`, `ImmutableBenchmarkError`, `ImmutableCriterionError`, `ImmutableEvaluationError`, `ImmutableScoreError`, `InvalidDimension`, `QualityReportRecord`, `ScoreRecord`, `UnknownCriterionError`, `UnknownEvaluationError`

## jarvis.autonomous_research_os

jarvis.autonomous_research_os — Autonomous Research OS Layer (P13). **관찰·분석·기록 전용.**

- module: `jarvis.autonomous_research_os` · CLI: `python -m jarvis.autonomous_research_os`
- classes: `ArtifactRecord`, `AutonomousResearchOSEngine`, `EpisodeRecord`, `ForbiddenOSActionError`, `IllegalOSTransition`, `ImmutableOSError`, `OSEventRecord`, `OSReportRecord`, `OSSummary`, `SnapshotRecord`, `UnknownOSError`, `ViewRecord`

## jarvis.autonomous_research_pipeline

jarvis.autonomous_research_pipeline — Autonomous Research Pipeline Core Layer (P12.1). **오케스트레이션 전용.**

- module: `jarvis.autonomous_research_pipeline` · CLI: `python -m jarvis.autonomous_research_pipeline`
- classes: `ArtifactRecord`, `AutonomousResearchPipelineEngine`, `CycleRecord`, `DanglingReferenceError`, `HistoryRecord`, `IllegalStageTransition`, `ImmutableCycleError`, `ImmutableObjectiveError`, `ImmutablePipelineError`, `ImmutableRunError`, `ImmutableStageError`, `InvalidReferenceType`, `MissingArtifactError`, `ObjectiveRecord`, `PipelineRecord`, `PipelineReportRecord`, `PipelineSummary`, `RunRecord`, `StageRecord`, `TransitionRecord`, `UnknownCycleError`, `UnknownObjectiveError`, `UnknownPipelineError`

## jarvis.benchmark

jarvis.benchmark — 결정적 벤치마킹 유틸리티 (P14 Production Hardening). **측정 전용, 완전 additive.**

- module: `jarvis.benchmark`
- classes: `BenchmarkReport`, `BenchmarkResult`, `StepClock`
- functions: `append_history`, `build_report`, `compare_reports`, `read_history`, `run_benchmark`, `run_suite`

## jarvis.broker_readonly

jarvis.broker_readonly — Broker Read-Only Integration Layer (P7.1).

- module: `jarvis.broker_readonly` · CLI: `python -m jarvis.broker_readonly`
- classes: `AccountSnapshot`, `BrokerHealth`, `BrokerPosition`, `BrokerReadOnlyProvider`, `IBReadOnlyProvider`, `KISReadOnlyProvider`, `MockBrokerProvider`, `ReconciliationReport`
- functions: `reconcile`

## jarvis.cache

jarvis.cache — 불변 읽기 캐시 레이어 (P14 Production Hardening). **읽기 캐시 전용, 완전 additive.**

- module: `jarvis.cache`
- classes: `CacheStats`, `ImmutableCache`, `ImmutableCacheError`

## jarvis.causal_intelligence

jarvis.causal_intelligence — Research Causal Intelligence Layer (P10.11). **연구 인과 분석 전용.**

- module: `jarvis.causal_intelligence` · CLI: `python -m jarvis.causal_intelligence`
- classes: `CausalArtifact`, `CausalCycleError`, `CausalReport`, `CausalSummary`, `Evidence`, `ExperimentEvent`, `GraphEvent`, `HypothesisEvent`, `IllegalTransition`, `ImmutableHypothesisError`, `ImmutableVariableError`, `RelationshipStudy`, `ResearchCausalEngine`, `UnknownExperiment`, `UnknownHypothesis`, `UnknownVariable`, `Variable`

## jarvis.compliance

jarvis.compliance — 컴플라이언스 체크리스트 (P15 Security & Compliance). **평가·보고 전용·완전 additive.**

- module: `jarvis.compliance`
- classes: `CheckItem`
- functions: `release_checklist`, `repository_checklist`, `reproducibility_checklist`, `run_checklist`, `run_compliance`, `security_checklist`

## jarvis.concurrency

jarvis.concurrency — 동시성 안전 유틸리티 (P14 Production Hardening). **안전 append 전용, 완전 additive.**

- module: `jarvis.concurrency`
- classes: `RWLock`, `ThreadSafetyResult`
- functions: `atomic_append`, `file_lock`, `safe_read_lines`, `verify_thread_safety`

## jarvis.data_governance

jarvis.data_governance — Data Governance & Lineage Layer (P9.8). **데이터 거버넌스 전용.**

- module: `jarvis.data_governance` · CLI: `python -m jarvis.data_governance`
- classes: `DataGovernanceEngine`, `DataGovernanceSummary`, `DataQualityReport`, `DataReliabilityScore`, `DatasetMetadata`, `DatasetVersion`, `ImmutableDatasetError`, `ImmutableSchemaError`, `LineageError`, `LineageEvent`, `SchemaDefinition`

## jarvis.db

jarvis.db — SQLite Projection Layer (P3).

- module: `jarvis.db` · CLI: `python -m jarvis.db`
- classes: `Database`, `ProjectionReport`
- functions: `db_path`, `exists`, `rebuild`, `source_checksum`, `verify`

## jarvis.decision_intelligence

jarvis.decision_intelligence — Research Decision Intelligence Layer (P10.7). **판단 지원 전용.**

- module: `jarvis.decision_intelligence` · CLI: `python -m jarvis.decision_intelligence`
- classes: `CandidateEvent`, `DecisionArtifact`, `DecisionIntelligenceReport`, `DecisionReport`, `DecisionSessionEvent`, `EvaluationFramework`, `IllegalTransition`, `ImmutableCandidateError`, `ImmutableFrameworkError`, `ResearchDecisionEngine`, `Scorecard`, `TradeoffAnalysis`, `UnknownCandidate`, `UnknownFramework`

## jarvis.dependency

jarvis.dependency — 의존성 감사 (P15 Security & Compliance). **읽기 전용·완전 additive.**

- module: `jarvis.dependency`
- classes: `DependencyFinding`, `Requirement`
- functions: `build_report`, `canonicalize`, `dependency_graph`, `detect_duplicates`, `detect_outdated`, `detect_unused`, `parse_pyproject`, `parse_requirement`, `scan_dependencies`

## jarvis.diagnostics

jarvis.diagnostics — 진단 (P14 Production Hardening). **관찰·경고 전용, 완전 additive.**

- module: `jarvis.diagnostics`
- classes: `Diagnostic`
- functions: `broken_lineage`, `dead_ledger`, `large_ledger`, `performance_regression`, `run_diagnostics`, `slow_replay`, `snapshot_drift`

## jarvis.documentation

jarvis.documentation — 문서 검증·API 자동생성 (P16 Documentation & Architecture). **읽기 전용·완전 additive.**

- module: `jarvis.documentation` · CLI: `python -m jarvis.documentation`
- functions: `check_api_coverage`, `check_completeness`, `cli_inventory`, `discover_packages`, `doc_root`, `generate_reference`, `introspect_package`, `repo_root`, `validate_all`, `validate_diagram`, `validate_links`, `validate_markdown`, `write_reference`

## jarvis.emergency

jarvis.emergency — Kill Switch & Emergency Response Layer (P9.3). **비상 결정 전용.**

- module: `jarvis.emergency` · CLI: `python -m jarvis.emergency`
- classes: `EmergencyDecision`, `EmergencyEngine`, `RecoveryApproval`, `RecoveryEvent`, `RecoveryNotPermitted`, `RecoveryRequest`

## jarvis.execution

Execution Gateway — 승인된 주문만. 실브로커 실행은 명시 활성화 전까지 BLOCK.

- module: `jarvis.execution`
- classes: `ExecutionGateway`

## jarvis.execution_audit

jarvis.execution_audit — Execution Audit & Attestation Layer (P8.6). **AUDIT-ONLY.**

- module: `jarvis.execution_audit` · CLI: `python -m jarvis.execution_audit`
- classes: `AuditCheck`, `ExecutionAuditCertificate`, `ExecutionAuditEngine`

## jarvis.execution_control

jarvis.execution_control — Execution Control Plane Layer (P7.4).

- module: `jarvis.execution_control` · CLI: `python -m jarvis.execution_control`
- classes: `ControlCheck`, `ExecutionControlPlane`, `ExecutionDecision`, `ExecutionIntent`

## jarvis.execution_cost

jarvis.execution_cost — Execution Cost & Slippage Accounting Layer (P8.4).

- module: `jarvis.execution_cost` · CLI: `python -m jarvis.execution_cost`
- classes: `CostAccountingEngine`, `CostComponents`, `CostRates`, `CostThresholds`, `ExecutionCostInput`, `ExecutionCostReport`
- functions: `calculate`, `cost_bps`, `cost_input_from_fills`, `slippage_bps`, `spread_bps`

## jarvis.execution_readiness

jarvis.execution_readiness — Execution Readiness Certification Layer (P7.7).

- module: `jarvis.execution_readiness` · CLI: `python -m jarvis.execution_readiness`
- classes: `ExecutionReadinessCertificate`, `ExecutionReadinessEngine`, `ReadinessCheck`

## jarvis.execution_reconciliation

jarvis.execution_reconciliation — Execution Reconciliation & Fill Validation Layer (P7.6).

- module: `jarvis.execution_reconciliation` · CLI: `python -m jarvis.execution_reconciliation`
- classes: `ExecutionExpectation`, `ExecutionReconciliationEngine`, `ExecutionValidationReport`, `ValidationThresholds`
- functions: `perfect_expectation`

## jarvis.execution_risk

jarvis.execution_risk — Execution Risk Enforcement Layer (P8.5).

- module: `jarvis.execution_risk` · CLI: `python -m jarvis.execution_risk`
- classes: `ExecutionRiskEngine`, `ExecutionRiskPolicy`, `ExecutionRiskReport`, `RiskCheck`, `RiskContext`

## jarvis.execution_simulation

jarvis.execution_simulation — Execution Simulation & Dry-Run Control Layer (P7.5).

- module: `jarvis.execution_simulation` · CLI: `python -m jarvis.execution_simulation`
- classes: `ExecutionSimulationReport`, `SimulatedFill`, `SimulatedOrder`, `SimulationEngine`

## jarvis.experiment_manager

jarvis.experiment_manager — Autonomous Experiment Manager (P11.4). **제안 전용.**

- module: `jarvis.experiment_manager` · CLI: `python -m jarvis.experiment_manager`
- classes: `ExperimentEventRecord`, `ExperimentManagerEngine`, `ExperimentPlanRecord`, `ExperimentReportRecord`, `ExperimentResultRecord`, `ExperimentStateError`, `ExperimentSummary`, `ForbiddenExecutionError`, `IllegalExperimentTransition`, `ImmutablePlanError`, `ImmutableRequestError`, `ImmutableResultError`, `InvalidOutcome`, `ResearchRequestRecord`, `UnknownExperimentError`

## jarvis.fill_reconciliation

jarvis.fill_reconciliation — Broker Fill Reconciliation Layer (P8.3).

- module: `jarvis.fill_reconciliation` · CLI: `python -m jarvis.fill_reconciliation`
- classes: `BrokerFill`, `FillReconciliationEngine`, `FillReconciliationReport`, `FillThresholds`, `InternalExecutionRecord`
- functions: `aggregate`, `match`

## jarvis.fusion

Signal Fusion Layer — 검증전략 신호 → 설명가능 합성신호(자문). 주문 없음.

- module: `jarvis.fusion` · CLI: `python -m jarvis.fusion`
- classes: `Contribution`, `FusionEngine`, `FusionSignal`, `StrategyPerf`, `StrategySignal`
- functions: `get_scheme`

## jarvis.governance_evolution

jarvis.governance_evolution — Research Governance Evolution Intelligence Layer (P10.22). **분석 전용.**

- module: `jarvis.governance_evolution` · CLI: `python -m jarvis.governance_evolution`
- classes: `EvolutionArtifact`, `EvolutionEvent`, `EvolutionPattern`, `EvolutionReport`, `EvolutionSnapshot`, `EvolutionSummary`, `GovernanceEvolutionEngine`, `GovernanceStateEvent`, `HistoricalComparison`, `IllegalTransition`, `ImmutableEventError`, `ImmutableMaturityError`, `ImmutablePatternError`, `InvalidEventType`, `InvalidMaturityLevel`, `MaturityAssessment`, `UnknownState`

## jarvis.governance_feedback

jarvis.governance_feedback — Research Governance Feedback Intelligence Layer (P10.20). **분석 전용.**

- module: `jarvis.governance_feedback` · CLI: `python -m jarvis.governance_feedback`
- classes: `AggregationRecord`, `FeedbackArtifact`, `FeedbackRecord`, `FeedbackReview`, `FeedbackSummary`, `GovernanceFeedbackEngine`, `GovernanceIssueEvent`, `GovernanceTrendReport`, `IllegalTransition`, `ImmutableFeedbackError`, `ImmutablePatternError`, `ImmutableThemeError`, `ImprovementTheme`, `InvalidFeedbackCategory`, `InvalidReviewDecision`, `PatternRecord`, `UnknownIssue`

## jarvis.governance_memory

jarvis.governance_memory — Research Governance Knowledge Memory Layer (P10.21). **저장·조회 전용.**

- module: `jarvis.governance_memory` · CLI: `python -m jarvis.governance_memory`
- classes: `ExperienceRecord`, `GovernanceMemoryEngine`, `ImmutableEntryError`, `ImmutableExperienceError`, `ImmutableLessonError`, `ImmutableResolutionError`, `InvalidEntryCategory`, `InvalidLinkType`, `InvalidMemoryLink`, `KnowledgeEntry`, `KnowledgeReport`, `LessonRecord`, `MemoryArtifact`, `MemoryLink`, `MemorySnapshot`, `MemorySummary`, `ResolutionHistory`, `UnknownSnapshot`

## jarvis.governance_orchestration

jarvis.governance_orchestration — Research Governance Orchestration Layer (P10.23). **관찰·집계 전용.**

- module: `jarvis.governance_orchestration` · CLI: `python -m jarvis.governance_orchestration`
- classes: `ConflictRecord`, `DependencyEdge`, `GovernanceOrchestrationEngine`, `HealthSummary`, `IllegalTransition`, `ImmutableLayerError`, `ImmutableStatusError`, `InvalidConflictCategory`, `InvalidDependencyGraph`, `LayerEvent`, `LayerStatusRecord`, `OrchestrationArtifact`, `OrchestrationReport`, `OrchestrationSummary`, `SystemSnapshotEvent`, `UnknownLayer`, `UnknownSnapshot`

## jarvis.integrity

jarvis.integrity — 원장·아티팩트 무결성 검증 (P15 Security & Compliance). **읽기 전용·완전 additive.**

- module: `jarvis.integrity`
- functions: `content_hash`, `detect_broken_lineage`, `detect_duplicate_ids`, `detect_invalid_timestamps`, `detect_orphan_artifacts`, `detect_tamper`, `replay_consistency`, `validate_artifact`, `validate_artifacts`, `verify_benchmark`, `verify_checksum`, `verify_graph_export`, `verify_hash_chain`, `verify_ledger`, `verify_snapshot`

## jarvis.knowledge

jarvis.knowledge — Research Knowledge Graph (P4).

- module: `jarvis.knowledge` · CLI: `python -m jarvis.knowledge`
- classes: `GraphReport`
- functions: `build`, `graph_checksum`, `graph_db_path`, `graph_exists`, `verify`

## jarvis.knowledge_intelligence

jarvis.knowledge_intelligence — Advanced Research Knowledge Intelligence Layer (P10.27). **분석 전용.**

- module: `jarvis.knowledge_intelligence` · CLI: `python -m jarvis.knowledge_intelligence`
- classes: `ClusterRecord`, `ContradictionRecord`, `ImmutableClusterError`, `ImmutableContradictionError`, `ImmutableInsightError`, `ImmutablePatternError`, `ImmutableSimilarityError`, `InvalidInsightType`, `InvalidStance`, `KnowledgeArtifact`, `KnowledgeInsight`, `KnowledgeIntelligenceEngine`, `KnowledgeReport`, `KnowledgeSummary`, `ResearchPattern`, `SimilarityRecord`

## jarvis.knowledge_sharing

jarvis.knowledge_sharing — Cross-Agent Knowledge Sharing (P11.8). **공유·기록 전용.**

- module: `jarvis.knowledge_sharing` · CLI: `python -m jarvis.knowledge_sharing`
- classes: `ArtifactRecord`, `CircularReferenceError`, `ConsumerRecord`, `DanglingReferenceError`, `EntryEventRecord`, `IllegalEntryTransition`, `ImmutableEntryError`, `ImmutableRatingError`, `ImmutableTopicError`, `ImmutableTransferError`, `InvalidKnowledgeType`, `InvalidLineageError`, `InvalidLinkType`, `InvalidRating`, `KnowledgeReportRecord`, `KnowledgeSharingEngine`, `LineageRecord`, `LinkRecord`, `RatingRecord`, `RegistryRecord`, `SelfReferenceError`, `SharingSummary`, `SnapshotRecord`, `SourceRecord`, `TopicRecord`, `TransferRecord`, `UnknownEntryError`, `UnknownRegistryError`, `UnknownTopicError`

## jarvis.license

jarvis.license — 라이선스 감사 (P15 Security & Compliance). **읽기 전용·완전 additive.**

- module: `jarvis.license`
- classes: `LicenseEntry`
- functions: `build_inventory`, `categorize`, `compatibility_report`, `normalize_license`, `third_party_notice`

## jarvis.live_execution

jarvis.live_execution — Live Execution Adapter Layer (P8.1). **첫 라이브 집행 경계.**

- module: `jarvis.live_execution` · CLI: `python -m jarvis.live_execution`
- classes: `BrokerExecutionAdapter`, `IBExecutionAdapter`, `KISExecutionAdapter`, `LiveExecutionEngine`, `LiveExecutionRequest`, `LiveExecutionResponse`, `MockExecutionAdapter`
- functions: `build_request`, `get_adapter`, `human_arm`

## jarvis.live_market_data

jarvis.live_market_data — Live Market Data Streaming Layer (P7.2).

- module: `jarvis.live_market_data` · CLI: `python -m jarvis.live_market_data`
- classes: `CacheStreamingProvider`, `IBStreamingProvider`, `KISStreamingProvider`, `LiveMarketDataProvider`, `LiveToMarketDataAdapter`, `MarketTick`, `MockStreamingProvider`
- functions: `live_valuation_provider`, `record_tick`, `simulate_ticks`

## jarvis.market_data

jarvis.market_data — Real Market Data Feed Layer (P6.4).

- module: `jarvis.market_data` · CLI: `python -m jarvis.market_data`
- classes: `CSVHistoricalProvider`, `CacheProvider`, `FallbackProvider`, `MarketDataProvider`, `MarketDataQualityReport`, `OHLCVBar`, `PriceSnapshot`, `PublicAPIProvider`
- functions: `assess_provider`, `assess_series`, `cache_snapshot`, `paper_valuation_provider`, `rebuild_index`

## jarvis.memory

Market Memory — 연구 교훈 영속 저장. Research Agent가 제안 전 필수 조회.

- module: `jarvis.memory`
- classes: `MarketMemory`
- functions: `seed_lessons`

## jarvis.meta_intelligence

jarvis.meta_intelligence — Research Meta Intelligence Layer (P10.12). **연구 과정 메타 분석 전용.**

- module: `jarvis.meta_intelligence` · CLI: `python -m jarvis.meta_intelligence`
- classes: `FailurePattern`, `IllegalTransition`, `ImmutableFailureError`, `ImmutableMethodError`, `ImmutablePatternError`, `InsightEvent`, `InvalidEvolutionLink`, `MetaArtifact`, `MetaReport`, `MetaSummary`, `OutcomeEvent`, `PatternEvent`, `ResearchMetaEngine`, `ResearchMethod`, `ResearchQualityScore`, `UnknownInsight`, `UnknownOutcome`, `UnknownPattern`

## jarvis.model_governance

jarvis.model_governance — Model Governance & AI Oversight Layer (P9.9). **관리·감사 전용.**

- module: `jarvis.model_governance` · CLI: `python -m jarvis.model_governance`
- classes: `ApprovalError`, `DeploymentRecord`, `EvaluationReport`, `IllegalTransition`, `ImmutableModelError`, `ImmutableVersionError`, `ModelApproval`, `ModelDriftReport`, `ModelGovernanceEngine`, `ModelGovernanceReport`, `ModelMetadata`, `ModelVersion`, `TrainingRun`

## jarvis.operational_audit

jarvis.operational_audit — Operational Audit & Compliance Layer (P9.6). **감사 전용.**

- module: `jarvis.operational_audit` · CLI: `python -m jarvis.operational_audit`
- classes: `AuditEvent`, `AuditFinding`, `ComplianceReport`, `ConfigurationSnapshot`, `OperationalAuditEngine`, `OperatorAction`

## jarvis.operations

jarvis.operations — Operations Alerting & Incident Management Layer (P9.2). **관제 전용.**

- module: `jarvis.operations` · CLI: `python -m jarvis.operations`
- classes: `Acknowledgement`, `Alert`, `Escalation`, `IllegalTransition`, `IncidentEvent`, `OperationsEngine`, `Resolution`

## jarvis.operations_console

jarvis.operations_console — Operations Control Center (P9.5). **읽기전용 시각화·관제 뷰.**

- module: `jarvis.operations_console` · CLI: `python -m jarvis.operations_console`
- classes: `DashboardView`, `OperationsConsole`, `OperationsSnapshot`, `TimelineEvent`
- functions: `render_dashboard`

## jarvis.order_lifecycle

jarvis.order_lifecycle — Live Order Lifecycle Control Layer (P8.2).

- module: `jarvis.order_lifecycle` · CLI: `python -m jarvis.order_lifecycle`
- classes: `InvalidTransition`, `OrderLifecycleEvent`, `OrderLifecycleManager`, `OrderLifecycleState`
- functions: `is_valid_transition`

## jarvis.paper

Paper — 자본 없는 페이퍼 운용. 내부 원장(브로커 무관). live 주문 불가.

- module: `jarvis.paper`
- classes: `PaperLedger`

## jarvis.paper_execution

jarvis.paper_execution — Paper Execution Layer (P6.2).

- module: `jarvis.paper_execution` · CLI: `python -m jarvis.paper_execution`
- classes: `FlatMarkProvider`, `PaperExecutionEngine`, `PaperExecutionReport`, `PaperFill`, `PaperOrder`, `PaperPosition`, `PaperRiskReport`, `PaperTradingRunner`, `PortfolioSnapshot`, `PriceSnapshot`, `RuntimeConfig`, `RuntimeEvent`, `StaticPriceProvider`
- functions: `attribution`, `attribution_current`, `monitor`, `portfolio_status`, `valuate`, `valuate_current`, `verify`

## jarvis.permissions

Permission system — 에이전트/행위별 명시 권한. AI는 자기 권한 확장 불가.

- module: `jarvis.permissions`
- classes: `Level`, `PermissionDenied`, `Principal`
- functions: `check`, `require`

## jarvis.planner

jarvis.planner — Research Planner Layer (P5). 커버리지 최적화기(아이디어 생성기 아님).

- module: `jarvis.planner` · CLI: `python -m jarvis.planner`
- classes: `PlannerProposal`, `PlannerReport`, `ResearchGap`
- functions: `run_planner`, `verify`, `write_proposals`

## jarvis.policy_governance

jarvis.policy_governance — Operational Policy & Configuration Governance (P9.7). **관리·감사 전용.**

- module: `jarvis.policy_governance` · CLI: `python -m jarvis.policy_governance`
- classes: `ApprovalError`, `ApprovalRecord`, `DriftError`, `IllegalTransition`, `ImmutablePolicyError`, `PolicyChangeEvent`, `PolicyDefinition`, `PolicyDriftReport`, `PolicyGovernanceEngine`, `PolicyGovernanceReport`, `PolicySnapshot`

## jarvis.portfolio

jarvis.portfolio — 포트폴리오 인프라(P2 준비). **배분 로직 없음(P1.7 = 표준화만).**

- module: `jarvis.portfolio` · CLI: `python -m jarvis.portfolio`
- classes: `EventReturnSource`, `MTMReturnSource`, `Position`, `ReturnMatrix`, `StrategyReturnSeries`
- functions: `business_days`, `buyback_source`

## jarvis.portfolio_research

jarvis.portfolio_research — Portfolio Research Intelligence Layer (P10.4). **연구 전용.**

- module: `jarvis.portfolio_research` · CLI: `python -m jarvis.portfolio_research`
- classes: `ConstructionStudy`, `IllegalTransition`, `ImmutablePortfolioError`, `ImmutableVersionError`, `PortfolioArtifact`, `PortfolioBacktest`, `PortfolioComparison`, `PortfolioHypothesis`, `PortfolioMetadata`, `PortfolioResearchEngine`, `PortfolioResearchReport`, `PortfolioVersion`, `RiskAnalysis`

## jarvis.post_trade_analytics

jarvis.post_trade_analytics — Post-Trade Analytics & TCA Layer (P8.7). **ANALYTICS-ONLY.**

- module: `jarvis.post_trade_analytics` · CLI: `python -m jarvis.post_trade_analytics`
- classes: `ExecutionData`, `PortfolioExecutionSummary`, `PostTradeAnalyticsEngine`, `PostTradeReport`, `TransactionCostAnalysisReport`

## jarvis.production

jarvis.production — Production Readiness Layer (P6.1).

- module: `jarvis.production` · CLI: `python -m jarvis.production`
- classes: `ApprovalGate`, `GateDecision`, `ProductionGate`, `ProductionMonitor`, `ProductionProposal`
- functions: `make_proposal_id`, `submit`, `verify`

## jarvis.profiling

jarvis.profiling — 프로파일링 헬퍼 (P14 Production Hardening). **관찰 전용, 완전 additive.**

- module: `jarvis.profiling`
- classes: `Profiler`, `SectionStat`, `StepClock`, `StepMemSampler`
- functions: `profile_callable`, `profile_cpu`, `profile_graph`, `profile_memory`, `profile_replay`, `profile_simulation`

## jarvis.reconciliation

jarvis.reconciliation — Portfolio Reconciliation & Control Layer (P7.3).

- module: `jarvis.reconciliation` · CLI: `python -m jarvis.reconciliation`
- classes: `ControlEvent`, `DriftThresholds`, `ReconciliationEngine`, `ReconciliationReport`
- functions: `reconcile_runtime`, `record_report`, `report_hash`

## jarvis.recovery_control

jarvis.recovery_control — Recovery Operations Control Plane (P9.4). **복구 관제 전용.**

- module: `jarvis.recovery_control` · CLI: `python -m jarvis.recovery_control`
- classes: `RecoveryAttestation`, `RecoveryAttestationError`, `RecoveryCheck`, `RecoveryChecklist`, `RecoveryControlEngine`, `RecoveryEvidence`, `RecoveryReadinessReport`

## jarvis.redteam

Red-Team 층 — LLM(MD)이 필요한 통제를 요구, 결정적 코드가 실행+판정.

- module: `jarvis.redteam`
- functions: `audit_registry`, `required_controls`, `review_strategy`

## jarvis.registry

Strategy Registry — 불변 상태전이 장부. 불법전이 거부, config 동결, rejected 보존.

- module: `jarvis.registry` · CLI: `python -m jarvis.registry`
- classes: `IllegalTransition`, `Status`, `StrategyRegistry`
- functions: `config_hash`

## jarvis.research_agent_coordinator

jarvis.research_agent_coordinator — Research Agent Execution Coordinator Layer (P12.3). **조정·기록 전용.**

- module: `jarvis.research_agent_coordinator` · CLI: `python -m jarvis.research_agent_coordinator`
- classes: `AgentRegistrationRecord`, `CollaborationRecord`, `ConflictingOwnerError`, `CoordinatorReportRecord`, `CoordinatorSummary`, `HandoffEvidenceError`, `HandoffRecord`, `IllegalAssignmentTransition`, `ImmutableAgentError`, `MissingResultError`, `OwnershipEventRecord`, `ProgressRecord`, `ResearchAgentCoordinatorEngine`, `UnknownAgentError`, `UnknownAssignmentError`

## jarvis.research_agents

jarvis.research_agents — Research Agent Framework (P11.1). **연구 보조 전용.**

- module: `jarvis.research_agents` · CLI: `python -m jarvis.research_agents`
- classes: `ActivityRecord`, `AgentProfileRecord`, `AgentRecord`, `AgentReportRecord`, `AgentSummary`, `CapabilityDenied`, `ForbiddenAgentAction`, `IllegalAgentTransition`, `IllegalTaskTransition`, `ImmutableAgentError`, `ImmutableMessageError`, `ImmutableProfileError`, `ImmutableReportError`, `InvalidAgentType`, `InvalidCapability`, `MessageRecord`, `ResearchAgentEngine`, `TaskEventRecord`, `UnknownAgentError`

## jarvis.research_api

jarvis.research_api — Research Intelligence API Backend (P10.29). **읽기 전용.**

- module: `jarvis.research_api` · CLI: `python -m jarvis.research_api`
- classes: `APIResponse`, `APISummary`, `AccessLogRecord`, `EndpointRecord`, `ForbiddenEndpoint`, `ImmutableEndpointError`, `ImmutableQueryError`, `ImmutableSchemaError`, `ImmutableViewError`, `InvalidEndpointMethod`, `QueryRecord`, `ResearchAPIEngine`, `SchemaRecord`, `UnknownEndpointError`, `ViewRecord`

## jarvis.research_compliance

jarvis.research_compliance — Research Compliance & Integrity Governance Layer (P10.19). **관찰 전용.**

- module: `jarvis.research_compliance` · CLI: `python -m jarvis.research_compliance`
- classes: `AuditReport`, `ComplianceArtifact`, `ComplianceCheck`, `ComplianceRule`, `ComplianceSummary`, `EvidenceRecord`, `IllegalTransition`, `ImmutableCheckError`, `ImmutableEvidenceError`, `ImmutableRuleError`, `InvalidCheckResult`, `InvalidReviewDecision`, `InvalidRuleCategory`, `InvalidViolationCategory`, `MissingReviewer`, `RemediationRecommendation`, `ResearchComplianceEngine`, `ReviewRecord`, `UnknownRule`, `UnknownViolation`, `ViolationEvent`

## jarvis.research_conflict_resolution

jarvis.research_conflict_resolution — Research Conflict Resolution Layer (P11.9). **리뷰·분석 전용.**

- module: `jarvis.research_conflict_resolution` · CLI: `python -m jarvis.research_conflict_resolution`
- classes: `ArtifactRecord`, `ClaimRecord`, `ConflictClosedError`, `ConflictEventRecord`, `ConflictReportRecord`, `ConflictSummary`, `ConsensusRecord`, `EvidenceRecord`, `IllegalConflictTransition`, `ImmutableClaimError`, `ImmutableEvidenceError`, `ImmutableMinorityError`, `ImmutableOutcomeError`, `ImmutablePositionError`, `InvalidEvidenceType`, `InvalidResolutionType`, `MinorityRecord`, `OutcomeRecord`, `PositionRecord`, `RegistryRecord`, `ResearchConflictResolutionEngine`, `SessionRecord`, `UnknownClaimError`, `UnknownConflictError`, `UnknownRegistryError`

## jarvis.research_control

jarvis.research_control — Autonomous Research Control Plane Layer (P12.10). **관찰·분석·기록 전용.**

- module: `jarvis.research_control` · CLI: `python -m jarvis.research_control`
- classes: `AlertRecord`, `ArtifactRecord`, `AutonomousResearchControlPlaneEngine`, `ControlSummary`, `ForbiddenControlActionError`, `HealthRecord`, `IllegalControlTransition`, `ImmutableStateError`, `MetricRecord`, `ResearchEventRecord`, `SnapshotRecord`, `StateEventRecord`, `SystemReportRecord`, `UnknownStateError`

## jarvis.research_control_plane

jarvis.research_control_plane — Research Control Plane Layer (P10.28). **관측 전용.**

- module: `jarvis.research_control_plane` · CLI: `python -m jarvis.research_control_plane`
- classes: `ComponentRecord`, `ControlPlaneSummary`, `ControlReportRecord`, `DependencyRecord`, `GovernanceDashboardRecord`, `HealthMetricRecord`, `ImmutableComponentError`, `ImmutableDashboardError`, `ImmutableDependencyError`, `ImmutableHealthError`, `ImmutableOverviewError`, `ImmutableReportError`, `ImmutableStatusError`, `InvalidComponentCategory`, `LayerStatusRecord`, `ResearchControlPlaneEngine`, `SystemOverviewRecord`, `TimelineEventRecord`, `UnknownComponentError`

## jarvis.research_coordinator

jarvis.research_coordinator — Autonomous Research Coordinator (P11.7). **조율·기록 전용.**

- module: `jarvis.research_coordinator` · CLI: `python -m jarvis.research_coordinator`
- classes: `ArtifactRecord`, `AssignmentEventRecord`, `CompletedTaskError`, `CompletionReportRecord`, `CoordinationEventRecord`, `CoordinatorRecord`, `CoordinatorSummary`, `DependencyCycleError`, `DependencyRecord`, `EscalationRecord`, `IllegalPlanTransition`, `IllegalTaskTransition`, `ImmutableCoordinatorError`, `InvalidSeverity`, `PlanClosedError`, `PlanEventRecord`, `ProgressRecord`, `ResearchCoordinatorEngine`, `ScheduleRecord`, `SelfDependencyError`, `UnknownCoordinatorError`, `UnknownPlanError`, `UnknownTaskError`, `WorkloadRecord`

## jarvis.research_council

jarvis.research_council — Multi-Agent Research Council (P11.6). **협의·기록 전용.**

- module: `jarvis.research_council` · CLI: `python -m jarvis.research_council`
- classes: `ArgumentRecord`, `ArtifactRecord`, `ConsensusRecord`, `CouncilRecord`, `CouncilReportRecord`, `CouncilSummary`, `DiscussionRecord`, `IllegalSessionTransition`, `ImmutableArgumentError`, `ImmutableConsensusError`, `ImmutableCouncilError`, `ImmutableMinorityError`, `ImmutableParticipantError`, `ImmutableSummaryError`, `ImmutableVoteError`, `InvalidAgentRole`, `InvalidStance`, `InvalidVoteChoice`, `MinorityRecord`, `ParticipantRecord`, `ResearchCouncilEngine`, `SessionEventRecord`, `SessionStateError`, `SummaryRecord`, `UnknownArgumentError`, `UnknownCouncilError`, `UnknownSessionError`, `VoteRecord`

## jarvis.research_data

jarvis.research_data — Research Data Platform & Data Governance (P10.1). **연구 데이터 관리 전용.**

- module: `jarvis.research_data` · CLI: `python -m jarvis.research_data`
- classes: `DataLineageRecord`, `DataQualityReport`, `DatasetMetadata`, `FeatureMetadata`, `ImmutableDatasetError`, `ImmutableFeatureError`, `LineageError`, `ResearchDataEngine`, `ResearchDataSummary`, `ResearchSnapshot`

## jarvis.research_event_bus

jarvis.research_event_bus — Research Event Bus Layer (P11.11). **통신 인프라 전용.**

- module: `jarvis.research_event_bus` · CLI: `python -m jarvis.research_event_bus`
- classes: `ArtifactRecord`, `CircularLineageError`, `ConsumerRecord`, `EventBusSummary`, `EventLifecycleRecord`, `EventReportRecord`, `EventTypeRecord`, `IllegalEventTransition`, `ImmutableEventError`, `ImmutableRouteError`, `ImmutableSourceError`, `ImmutableStreamError`, `ImmutableSubscriberError`, `ImmutableTypeError`, `InvalidEventType`, `InvalidRoutingError`, `LineageRecord`, `MissingParentError`, `ResearchEventBusEngine`, `RouteRecord`, `SnapshotRecord`, `SourceRecord`, `StreamRecord`, `SubscriberRecord`, `UnauthorizedSourceError`, `UnknownEventError`, `UnknownStreamError`, `UnknownSubscriberError`

## jarvis.research_evolution

jarvis.research_evolution — Research Evolution Governance Layer (P10.16). **저장·분석·기록 전용.**

- module: `jarvis.research_evolution` · CLI: `python -m jarvis.research_evolution`
- classes: `EvolutionArtifact`, `EvolutionCycleEvent`, `EvolutionReport`, `EvolutionSummary`, `FailurePattern`, `IllegalTransition`, `ImmutableFailureError`, `ImmutableLearningError`, `ImmutableResearchObjectError`, `ImmutableTransferError`, `ImprovementProposalEvent`, `InvalidFailureCategory`, `InvalidLineageLink`, `IterationRecord`, `KnowledgeTransferRecord`, `LearningRecord`, `ResearchEvolutionEngine`, `ResearchObject`, `UnknownCycle`, `UnknownProposal`, `UnknownResearchObject`

## jarvis.research_experience_memory

jarvis.research_experience_memory — Research Memory & Experience Layer (P12.7). **기억·기록·검색 전용.**

- module: `jarvis.research_experience_memory` · CLI: `python -m jarvis.research_experience_memory`
- classes: `ArtifactRecord`, `DanglingReferenceError`, `EpisodeRecord`, `ExperienceRecord`, `FailureRecord`, `IllegalMemoryTransition`, `ImmutableEpisodeError`, `ImmutableExperienceError`, `ImmutableFailureError`, `ImmutableMemoryError`, `ImmutablePatternError`, `InvalidMemoryType`, `MemoryEventRecord`, `MemorySummary`, `PatternRecord`, `ResearchExperienceMemoryEngine`, `RetrievalRecord`, `SummaryRecord`, `UnknownEpisodeError`, `UnknownMemoryError`

## jarvis.research_governance

jarvis.research_governance — Strategy Research & Experiment Governance (P10.2). **연구 관리 전용.**

- module: `jarvis.research_governance` · CLI: `python -m jarvis.research_governance`
- classes: `BacktestRecord`, `ExperimentComparison`, `ExperimentRun`, `IllegalTransition`, `ImmutableStrategyError`, `ImmutableVersionError`, `ResearchArtifact`, `ResearchGovernanceEngine`, `ResearchGovernanceReport`, `ResearchHypothesis`, `StrategyMetadata`, `StrategyVersion`, `ValidationReport`

## jarvis.research_improvement

jarvis.research_improvement — Research Self-Improvement Loop Layer (P11.10). **분석·기록 전용.**

- module: `jarvis.research_improvement` · CLI: `python -m jarvis.research_improvement`
- classes: `ArtifactRecord`, `CircularLearningError`, `CycleRecord`, `DanglingReferenceError`, `FailureRecord`, `IllegalImprovementTransition`, `ImmutableCycleError`, `ImmutableFailureError`, `ImmutableImprovementError`, `ImmutableLearningError`, `ImmutableObservationError`, `ImmutableReportError`, `ImmutableReviewError`, `ImprovementEventRecord`, `ImprovementReportRecord`, `ImprovementSummary`, `InvalidCategory`, `InvalidDecision`, `IterationRecord`, `LearningRecord`, `MetricRecord`, `MissingSourceError`, `ObservationRecord`, `RegistryRecord`, `ResearchImprovementEngine`, `ReviewRecord`, `UnknownCycleError`, `UnknownImprovementError`, `UnknownRegistryError`

## jarvis.research_kg

jarvis.research_kg — Research Knowledge Graph Layer (P10.5). **분석·검색·관계 추적 전용.**

- module: `jarvis.research_kg` · CLI: `python -m jarvis.research_kg`
- classes: `CycleError`, `EntityEvent`, `GraphArtifact`, `GraphSnapshot`, `IllegalTransition`, `ImmutableEntityError`, `InvalidRelationship`, `LineageEdge`, `Relationship`, `ResearchGraphReport`, `ResearchKnowledgeGraphEngine`, `SimilarityReport`, `UnknownEntity`

## jarvis.research_learning

jarvis.research_learning — Research Learning Loop Layer (P12.8). **관찰·분석·기록 전용.**

- module: `jarvis.research_learning` · CLI: `python -m jarvis.research_learning`
- classes: `ArtifactRecord`, `FeedbackRecord`, `ForbiddenAutoActionError`, `IllegalLearningTransition`, `ImmutableFeedbackError`, `ImmutableImprovementError`, `ImmutableLessonError`, `ImmutableLoopError`, `ImmutableObservationError`, `ImprovementCandidateRecord`, `InvalidVerdict`, `LearningReportRecord`, `LearningSummary`, `LessonRecord`, `LoopEventRecord`, `ObservationRecord`, `PatternRecord`, `ResearchLearningLoopEngine`, `UnknownLoopError`

## jarvis.research_lifecycle

jarvis.research_lifecycle — Research Lifecycle Intelligence Layer (P10.26). **생명주기 추적 전용.**

- module: `jarvis.research_lifecycle` · CLI: `python -m jarvis.research_lifecycle`
- classes: `BottleneckRecord`, `IllegalTransition`, `ImmutableBottleneckError`, `ImmutableEventError`, `InvalidBottleneckCategory`, `InvalidEventType`, `InvalidStage`, `LifecycleArtifact`, `LifecycleEvent`, `LifecycleReport`, `LifecycleSummary`, `ProjectEvent`, `ResearchLifecycleEngine`, `StageTransition`, `UnknownProject`

## jarvis.research_literature

jarvis.research_literature — Research Literature Intelligence (P11.3). **읽기·기록 전용.**

- module: `jarvis.research_literature` · CLI: `python -m jarvis.research_literature`
- classes: `CitationRecord`, `ComparisonRecord`, `ConceptRecord`, `ImmutableCitationError`, `ImmutableComparisonError`, `ImmutableConceptError`, `ImmutableLinkError`, `ImmutablePaperError`, `InvalidConceptType`, `InvalidLinkType`, `KnowledgeLinkRecord`, `LiteratureSummary`, `PaperRecord`, `ResearchLiteratureEngine`, `SelfCitationError`, `UnknownConceptError`, `UnknownPaperError`

## jarvis.research_manager

jarvis.research_manager — Autonomous Research Manager Layer (P12.9). **계획·추적·모니터링 전용.**

- module: `jarvis.research_manager` · CLI: `python -m jarvis.research_manager`
- classes: `ArtifactRecord`, `AutonomousResearchManagerEngine`, `CircularDependencyError`, `DanglingDependencyError`, `DependencyRecord`, `IllegalPlanTransition`, `ImmutableDependencyError`, `ImmutablePlanError`, `ImmutableTaskError`, `ManagerSummary`, `PlanEventRecord`, `ProgressRecord`, `StatusReportRecord`, `TaskRecord`, `UnknownPlanError`, `UnknownTaskError`

## jarvis.research_memory

jarvis.research_memory — Research Memory Intelligence Layer (P10.14). **연구 기억 보존·검색 전용.**

- module: `jarvis.research_memory` · CLI: `python -m jarvis.research_memory`
- classes: `IllegalTransition`, `ImmutableLessonError`, `ImmutableMemoryError`, `ImmutablePatternError`, `InvalidConnection`, `MemoryArtifact`, `MemoryCluster`, `MemoryConnection`, `MemoryEvent`, `MemoryPattern`, `MemoryReport`, `MemorySummary`, `ResearchLesson`, `ResearchMemoryEngine`, `RetrievalRecord`, `UnknownMemory`

## jarvis.research_memory_system

jarvis.research_memory_system — Research Memory System Layer (P11.12). **기억 시스템 전용.**

- module: `jarvis.research_memory_system` · CLI: `python -m jarvis.research_memory_system`
- classes: `ArtifactRecord`, `AssociationRecord`, `CircularAssociationError`, `ContextRecord`, `DanglingReferenceError`, `ExperimentMemoryRecord`, `FailureMemoryRecord`, `IllegalMemoryTransition`, `ImmutableAssociationError`, `ImmutableContextError`, `ImmutableExperimentError`, `ImmutableFailureError`, `ImmutableKnowledgeError`, `ImmutableMemoryError`, `ImmutablePatternError`, `ImmutableReportError`, `InvalidMemoryType`, `InvalidSearchMode`, `KnowledgeEntryRecord`, `MemoryEventRecord`, `MemoryReportRecord`, `MemorySummary`, `MissingSourceError`, `RegistryRecord`, `ResearchMemorySystemEngine`, `SearchRecord`, `SnapshotRecord`, `SuccessPatternRecord`, `UnknownMemoryError`, `UnknownRegistryError`

## jarvis.research_observability

jarvis.research_observability — Research Monitoring & Observability Layer (P10.18). **관찰 전용.**

- module: `jarvis.research_observability` · CLI: `python -m jarvis.research_observability`
- classes: `ActivityEvent`, `AnomalyEvent`, `HealthRecord`, `IllegalTransition`, `ImmutableAnomalyError`, `ImmutableHealthError`, `ImmutableMetricError`, `InvalidAnomalyCategory`, `InvalidHealthStatus`, `InvalidMetricType`, `MetricRecord`, `ObservabilityArtifact`, `ObservabilityReport`, `ObservabilitySummary`, `ObservationSnapshot`, `QualitySignal`, `ResearchObservabilityEngine`, `UnknownAnomaly`, `UnknownSnapshot`

## jarvis.research_observatory

jarvis.research_observatory — Research Observatory & Control Plane Layer (P10.10). **관측 전용.**

- module: `jarvis.research_observatory` · CLI: `python -m jarvis.research_observatory`
- classes: `Dashboard`, `DependencyEdge`, `IllegalTransition`, `ImmutableSnapshotError`, `ObservatoryArtifact`, `ObservatoryMetric`, `ObservatoryReport`, `ObservatorySummary`, `ResearchObservatoryEngine`, `SnapshotEvent`, `TimelineEvent`, `TrendReport`, `UnknownSnapshot`

## jarvis.research_optimization_engine

jarvis.research_optimization_engine — Research Optimization Engine Layer (P12.6). **분석·제안 전용.**

- module: `jarvis.research_optimization_engine` · CLI: `python -m jarvis.research_optimization_engine`
- classes: `BottleneckRecord`, `ComparisonRecord`, `EfficiencyRecord`, `ForbiddenOptimizationError`, `IllegalStudyTransition`, `ImmutableBottleneckError`, `ImmutableComparisonError`, `ImmutableEfficiencyError`, `ImmutableProposalError`, `ImmutableStudyError`, `IncompleteProposalError`, `InvalidSeverity`, `OptimizationReportRecord`, `OptimizationSummary`, `ProposalRecord`, `ResearchOptimizationEngine`, `StudyEventRecord`, `UnknownStudyError`

## jarvis.research_orchestration

jarvis.research_orchestration — Research Orchestration & Workflow Intelligence Layer (P10.17).

- module: `jarvis.research_orchestration` · CLI: `python -m jarvis.research_orchestration`
- classes: `BottleneckEvent`, `DependencyEdge`, `IllegalTransition`, `ImmutablePipelineError`, `ImmutableTaskError`, `ImmutableWorkflowError`, `InvalidBottleneckCategory`, `InvalidDependencyGraph`, `OrchestrationArtifact`, `OrchestrationEvent`, `OrchestrationReport`, `OrchestrationSummary`, `PipelineVersion`, `ResearchOrchestrationEngine`, `TaskEvent`, `UnknownBottleneck`, `UnknownTask`, `UnknownWorkflow`, `WorkflowEvent`, `WorkflowRun`

## jarvis.research_organization

jarvis.research_organization — Autonomous Research Organization Layer (P11.13). **조직 전용.**

- module: `jarvis.research_organization` · CLI: `python -m jarvis.research_organization`
- classes: `ArtifactRecord`, `CircularDependencyError`, `DanglingReferenceError`, `IllegalOrgTransition`, `ImmutableOrganizationError`, `ImmutablePolicyError`, `ImmutableResponsibilityError`, `ImmutableRoleError`, `ImmutableTeamError`, `ImmutableUnitError`, `ImmutableWorkflowError`, `InvalidAgentRole`, `InvalidUnitType`, `MissingOwnerError`, `OrgEventRecord`, `OrgReportRecord`, `OrgSummary`, `PolicyRecord`, `ResearchOrganizationEngine`, `ResponsibilityRecord`, `RoleRecord`, `SnapshotRecord`, `TeamRecord`, `UnitRecord`, `UnknownOrganizationError`, `UnknownUnitError`, `WorkflowOwnershipRecord`

## jarvis.research_os

jarvis.research_os — Research Operating System Orchestration Layer (P11). **관찰·조직 전용.**

- module: `jarvis.research_os` · CLI: `python -m jarvis.research_os`
- classes: `CrossLayerEvent`, `DependencyEdge`, `HealthReport`, `IllegalTransition`, `ImmutableLayerError`, `ImmutableWorkflowError`, `InvalidWorkflowGraph`, `LayerEvent`, `LineageEdge`, `OrchestrationArtifact`, `OrchestrationSummary`, `ResearchOSEngine`, `SnapshotEvent`, `UnknownLayer`, `UnknownSnapshot`, `UnknownWorkflow`, `WorkflowEvent`

## jarvis.research_os_core

jarvis.research_os_core — Research Operating System Core (P10.30, Phase 10 최종). **관측 전용.**

- module: `jarvis.research_os_core` · CLI: `python -m jarvis.research_os_core`
- classes: `CatalogRecord`, `GlobalReportRecord`, `GlobalStateRecord`, `ImmutableCatalogError`, `ImmutableModuleError`, `ImmutableReportError`, `ImmutableSnapshotError`, `ImmutableStateError`, `InvalidDomain`, `ModuleRecord`, `OSSummary`, `ResearchOSCoreEngine`, `SnapshotRecord`, `UnknownModuleError`

## jarvis.research_planning

jarvis.research_planning — Research Planning Intelligence Layer (P10.15). **연구 계획 전용.**

- module: `jarvis.research_planning` · CLI: `python -m jarvis.research_planning`
- classes: `DependencyEdge`, `IllegalTransition`, `ImmutableBlueprintError`, `ImmutableHypothesisError`, `ImmutableOpportunityError`, `ImmutablePlanError`, `InvalidDependency`, `OpportunityEvent`, `PlanningArtifact`, `PlanningHypothesis`, `PlanningReport`, `PlanningSummary`, `PriorityAnalysis`, `ResearchBlueprint`, `ResearchPlan`, `ResearchPlanningEngine`, `UnknownOpportunity`, `UnknownPlan`

## jarvis.research_reviewer

jarvis.research_reviewer — AI Research Reviewer Layer (P11.5). **평가·기록 전용.**

- module: `jarvis.research_reviewer` · CLI: `python -m jarvis.research_reviewer`
- classes: `CritiqueRecord`, `EvidenceRecord`, `ImmutableCritiqueError`, `ImmutableEvidenceError`, `ImmutableReportError`, `ImmutableReviewError`, `InvalidDimension`, `InvalidEvidenceType`, `InvalidScore`, `InvalidSeverity`, `MissingDimensions`, `ResearchReviewerEngine`, `ReviewRecord`, `ReviewerReportRecord`, `ReviewerSummary`, `UnknownCritiqueError`, `UnknownReviewError`

## jarvis.research_risk_intelligence

jarvis.research_risk_intelligence — Research Risk Intelligence Layer (P10.25). **연구 과정 리스크 분석 전용.**

- module: `jarvis.research_risk_intelligence` · CLI: `python -m jarvis.research_risk_intelligence`
- classes: `IllegalTransition`, `ImmutableAssessmentError`, `ImmutableFactorError`, `InvalidRiskCategory`, `ResearchRiskIntelligenceEngine`, `RiskArtifact`, `RiskAssessment`, `RiskEvent`, `RiskFactor`, `RiskReport`, `RiskSummary`, `UnknownRisk`

## jarvis.research_task_planner

jarvis.research_task_planner — Autonomous Research Task Planner (P11.2). **계획 전용.**

- module: `jarvis.research_task_planner` · CLI: `python -m jarvis.research_task_planner`
- classes: `DependencyCycleError`, `DependencyRecord`, `IllegalPlanTransition`, `ImmutableDependencyError`, `ImmutablePlanError`, `ImmutableReportError`, `ImmutableScheduleError`, `ImmutableTaskError`, `InvalidTaskKind`, `PlanEventRecord`, `PlanFrozenError`, `PlanReportRecord`, `PlannerSummary`, `ResearchTaskPlannerEngine`, `ScheduleRecord`, `SelfDependencyError`, `TaskRecord`, `UnknownPlanError`, `UnknownTaskError`

## jarvis.research_validation

jarvis.research_validation — Research Validation & Reproducibility Governance (P10.9). **평가 기록 전용.**

- module: `jarvis.research_validation` · CLI: `python -m jarvis.research_validation`
- classes: `EvidenceRecord`, `IllegalTransition`, `ImmutableValidationError`, `LineageReport`, `ReplayReport`, `ReproducibilityChecklist`, `ResearchValidationEngine`, `UnknownValidation`, `ValidationArtifact`, `ValidationAuditSummary`, `ValidationEvent`, `ValidationScore`, `ValidationSession`

## jarvis.resilience

jarvis.resilience — 복구·크래시 진단 (P14 Production Hardening). **원본 원장 불변, 완전 additive.**

- module: `jarvis.resilience`
- classes: `ScanResult`
- functions: `content_hash`, `diagnose_corruption`, `partial_replay`, `recover_to_copy`, `scan_ledger`, `snapshot_recovery`, `validate_checkpoint`, `verify_recoverable`

## jarvis.risk

Risk Governor — 하드 결정적 리스크 통제(LLM 아님).

- module: `jarvis.risk`
- classes: `RiskGovernor`, `RiskLimits`

## jarvis.sbom

jarvis.sbom — SBOM 생성 (P15 Security & Compliance). **읽기 전용·완전 additive.**

- module: `jarvis.sbom`
- classes: `Component`
- functions: `component_hash`, `generate_sbom`, `make_component`, `sbom_from_dependencies`, `verify_sbom`

## jarvis.security

jarvis.security — 시크릿·정적 보안 분석 (P15 Security & Compliance). **탐지·보고 전용·완전 additive.**

- module: `jarvis.security`
- classes: `SecretFinding`, `StaticFinding`
- functions: `analyze_report`, `analyze_source`, `detect_path_traversal`, `redact`, `scan_files`, `scan_line`, `scan_report`, `scan_source`, `scan_text`, `shannon_entropy`

## jarvis.self_audit_intelligence

jarvis.self_audit_intelligence — Research Self Audit Intelligence Layer (P10.24). **READ ONLY 감사 전용.**

- module: `jarvis.self_audit_intelligence` · CLI: `python -m jarvis.self_audit_intelligence`
- classes: `AuditArtifact`, `AuditDefinition`, `AuditReport`, `AuditRunEvent`, `AuditSummary`, `IllegalTransition`, `ImmutableAuditError`, `IntegrityCheck`, `InvalidCheckKind`, `ResearchSelfAuditEngine`, `UnknownRun`, `ViolationRecord`

## jarvis.self_improvement_intelligence

jarvis.self_improvement_intelligence — Research Self-Improvement Intelligence (P10.13). **분석·제안 전용.**

- module: `jarvis.self_improvement_intelligence` · CLI: `python -m jarvis.self_improvement_intelligence`
- classes: `BottleneckRecord`, `IllegalTransition`, `ImmutableBottleneckError`, `ImmutableOpportunityError`, `ImmutableTemplateError`, `ImmutableWorkflowError`, `ImprovementArtifact`, `ImprovementEvidence`, `ImprovementReport`, `ImprovementSummary`, `InvalidImprovementLink`, `OpportunityEvent`, `RecommendationEvent`, `ResearchSelfImprovementEngine`, `TemplateEvolution`, `UnknownOpportunity`, `UnknownRecommendation`, `UnknownWorkflow`, `WorkflowPattern`

## jarvis.simulation_environment

jarvis.simulation_environment — Research Simulation Environment Layer (P10.8). **비실행 분석 전용.**

- module: `jarvis.simulation_environment` · CLI: `python -m jarvis.simulation_environment`
- classes: `IllegalTransition`, `ImmutableRunError`, `ImmutableScenarioError`, `MarketRegimeScenario`, `ParameterScenario`, `ResearchSimulationEngine`, `ScenarioEvent`, `SimulationArtifact`, `SimulationComparison`, `SimulationEnvironmentReport`, `SimulationResult`, `SimulationRunEvent`, `UnknownRun`, `UnknownScenario`

## jarvis.system_health

jarvis.system_health — System Health Monitoring & Operations Layer (P9.1). **OPERATIONS-ONLY.**

- module: `jarvis.system_health` · CLI: `python -m jarvis.system_health`
- classes: `SubsystemProbe`, `SystemHealthEngine`, `SystemHealthReport`
- functions: `collect_all`, `subsystem_names`

## jarvis.threat_model

jarvis.threat_model — 위협 모델 (P15 Security & Compliance). **문서·분석 전용·완전 additive.**

- module: `jarvis.threat_model`
- classes: `Threat`
- functions: `build_threat_model`, `filter_by_severity`, `residual_risks`, `risk_matrix`, `risk_score`, `severity_of`, `threats`, `to_markdown`
