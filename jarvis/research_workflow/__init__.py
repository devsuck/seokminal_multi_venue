"""jarvis.research_workflow — Workflow Orchestration & Decision Intelligence (P64-67). **조율만, 실행 없음.**

기존 서브시스템(research_queue·research_assistant·research_council·portfolio_research·
research_risk_intelligence·research_ingestion·paper_feedback)을 **조율**해 하나의 연구 운영체제로 묶는다.
새 지능/새 실험 저장소를 만들지 않는다 — 워크플로/세션 이벤트만 자체 원장(rwf_)에 append(읽기전용·결정적·
사람 승인·append-only). Jarvis 는 결정하지 않는다 — 증거를 조직하고 지식을 보존하며 사람 판단을 지원한다.
"""
from jarvis.research_workflow.decision_support import DecisionSupportEngine  # noqa: F401
from jarvis.research_workflow.explainability import ExplainabilityEngine  # noqa: F401
from jarvis.research_workflow.models import (  # noqa: F401
    STAGES,
    DecisionMemo,
    EvidenceChain,
    SessionState,
    WorkflowState,
)
from jarvis.research_workflow.orchestrator import (  # noqa: F401
    WorkflowCancelledError,
    WorkflowOrchestrator,
)
from jarvis.research_workflow.autonomous_loop import (  # noqa: F401
    AutonomousResearchLoop,
    LoopCancelledError,
    LoopState,
)
from jarvis.research_workflow.alt_data import catalog as alt_data_catalog  # noqa: F401
from jarvis.research_workflow.research_trigger import ResearchTrigger, dispatch as dispatch_trigger  # noqa: F401
from jarvis.research_workflow.research_trigger import from_event as trigger_from_event  # noqa: F401
from jarvis.research_workflow.backtest_bridge import BacktestResearchJob, create_job as create_backtest_job  # noqa: F401
from jarvis.research_workflow.paper_validation import PaperValidationMonitor, validate as validate_paper  # noqa: F401
from jarvis.research_workflow.validation_gap import analyze_gap as analyze_validation_gap  # noqa: F401
from jarvis.research_workflow.strategy_lifecycle import board as lifecycle_board, lifecycle_state  # noqa: F401
from jarvis.research_workflow.quality_monitor import ResearchQualityMonitor, evaluate as evaluate_quality  # noqa: F401
from jarvis.research_workflow.ops_events import ops_events as research_ops_events  # noqa: F401
from jarvis.research_workflow.research_audit import audit_strategy, audit_coverage  # noqa: F401
from jarvis.research_workflow.release_validation import validate_release, safety_check  # noqa: F401
from jarvis.research_workflow.providers import Provider, provider_for, provider_registry  # noqa: F401
from jarvis.research_workflow.market_pipeline import run as run_market_pipeline  # noqa: F401
from jarvis.research_workflow.news_pipeline import run as run_news_pipeline  # noqa: F401
from jarvis.research_workflow.fundamental_pipeline import run as run_fundamental_pipeline  # noqa: F401
from jarvis.research_workflow.ownership_pipeline import run as run_ownership_pipeline  # noqa: F401
from jarvis.research_workflow.research_feed import ResearchFeedPipeline, collect as collect_research_feed  # noqa: F401
from jarvis.research_workflow.data_quality import DataQualityMonitor, build_data_health  # noqa: F401
from jarvis.research_workflow.live_intelligence import build_live_intelligence  # noqa: F401
from jarvis.research_workflow.operational_validation import validate_operations, architecture_safety  # noqa: F401
from jarvis.research_workflow.agent_capability import capability_map as agent_capability_map  # noqa: F401
from jarvis.research_workflow.research_director import ResearchDirector  # noqa: F401
from jarvis.research_workflow.market_analyst import MarketAnalyst  # noqa: F401
from jarvis.research_workflow.company_analyst import CompanyAnalyst  # noqa: F401
from jarvis.research_workflow.strategy_researcher import StrategyResearcher  # noqa: F401
from jarvis.research_workflow.research_reviewer import ResearchReviewer  # noqa: F401
from jarvis.research_workflow.research_writer import ResearchWriter  # noqa: F401
from jarvis.research_workflow.multi_agent_workflow import run as run_agent_workflow  # noqa: F401
from jarvis.research_workflow.agent_validation import validate_agents, agent_safety  # noqa: F401
from jarvis.research_workflow.memory_audit import audit_memory  # noqa: F401
from jarvis.research_workflow.knowledge_graph_upgrade import build_research_knowledge_graph  # noqa: F401
from jarvis.research_workflow.semantic_recall import recall_context  # noqa: F401
from jarvis.research_workflow.research_similarity import ResearchSimilarity, compare as research_compare  # noqa: F401
from jarvis.research_workflow.conflict_detection import detect_conflicts  # noqa: F401
from jarvis.research_workflow.learning_engine import ResearchLearningEngine, learn as learn_lesson  # noqa: F401
from jarvis.research_workflow.agent_memory import knowledge_informed_research  # noqa: F401
from jarvis.research_workflow.knowledge_quality import build_knowledge_health  # noqa: F401
from jarvis.research_workflow.brain_validation import validate_brain, brain_safety  # noqa: F401
from jarvis.research_workflow.research_scheduler import ResearchScheduler, plan_cycle  # noqa: F401
from jarvis.research_workflow.morning_briefing import MorningBriefingGenerator, generate as generate_briefing  # noqa: F401
from jarvis.research_workflow.company_monitor import CompanyMonitor, update as monitor_company  # noqa: F401
from jarvis.research_workflow.strategy_health import StrategyHealthMonitor, report as strategy_health_report  # noqa: F401
from jarvis.research_workflow.report_automation import ReportAutomation, generate as generate_report  # noqa: F401
from jarvis.research_workflow.research_workspace import build_workspace, act as workspace_act  # noqa: F401
from jarvis.research_workflow.research_outcome_tracker import ResearchOutcomeTracker, track as track_outcome  # noqa: F401
from jarvis.research_workflow.agent_performance import AgentPerformanceMonitor, report as agent_performance_report  # noqa: F401
from jarvis.research_workflow.ops_validation import validate_research_ops, ops_safety  # noqa: F401
from jarvis.research_workflow.data_production import build_data_production  # noqa: F401
from jarvis.research_workflow.sector_intelligence import analyze_sector  # noqa: F401
from jarvis.research_workflow.macro_intelligence import build_macro_context  # noqa: F401
from jarvis.research_workflow.company_intelligence import analyze_company  # noqa: F401
from jarvis.research_workflow.research_context_engine import build_research_context  # noqa: F401
from jarvis.research_workflow.cross_asset_intelligence import build_cross_asset  # noqa: F401
from jarvis.research_workflow.institutional_memory_expansion import build_institutional_memory  # noqa: F401
from jarvis.research_workflow.intelligence_quality import score_intelligence  # noqa: F401
from jarvis.research_workflow.institutional_intelligence_validation import validate_intelligence, intelligence_safety  # noqa: F401
from jarvis.research_workflow.investment_committee import build_committee_packet  # noqa: F401
from jarvis.research_workflow.debate_engine import build_debate  # noqa: F401
from jarvis.research_workflow.conviction_framework import build_conviction  # noqa: F401
from jarvis.research_workflow.portfolio_research_view import build_portfolio_research  # noqa: F401
from jarvis.research_workflow.human_decision_center import build_decision_center, act as decision_center_act  # noqa: F401
from jarvis.research_workflow.production_monitor import build_production_status  # noqa: F401
from jarvis.research_workflow.operational_metrics import build_operational_metrics  # noqa: F401
from jarvis.research_workflow.governance import build_governance  # noqa: F401
# P203 Governance Consolidation — 검증 목적별 5도메인 단일 공개 API(validate/validate_all).
from jarvis.research_workflow.governance import (  # noqa: F401
    DOMAINS as GOVERNANCE_DOMAINS,
    validate as validate_domain,
    validate_all as validate_governance,
    validation_inventory,
)
from jarvis.research_workflow.system_validation import validate_system  # noqa: F401
from jarvis.research_workflow.release_v20 import build_release_report  # noqa: F401
from jarvis.research_workflow.backfill import (  # noqa: F401
    plan as backfill_plan,
    run_backfill,
    sync as backfill_sync,
)
# P171-180 Autonomous Research Intelligence Enhancement — 기존 엔진 조율, 새 아키텍처 없음.
from jarvis.research_workflow.creative_hypothesis import discover_hypotheses  # noqa: F401
from jarvis.research_workflow.research_search import build_search_space  # noqa: F401
from jarvis.research_workflow.continuous_queue import build_continuous_queue  # noqa: F401
from jarvis.research_workflow.experiment_prioritization import prioritize_experiments  # noqa: F401
from jarvis.research_workflow.research_expansion import expand_research  # noqa: F401
from jarvis.research_workflow.self_reflection import reflect_on_cycle  # noqa: F401
from jarvis.research_workflow.research_planning import build_research_plan  # noqa: F401
from jarvis.research_workflow.collaborative_research import run_collaborative_research  # noqa: F401
from jarvis.research_workflow.productivity_optimization import build_productivity_report  # noqa: F401
from jarvis.research_workflow.autonomy_validation import validate_autonomy, autonomy_safety  # noqa: F401
# P181-200 Autonomous Research Discovery & Validation Loop v3.0 — 기존 엔진 조율, 새 아키텍처 없음.
from jarvis.research_workflow.research_cycle import ResearchCycleManager, run_cycle  # noqa: F401
from jarvis.research_workflow.market_observation import observe_market  # noqa: F401
from jarvis.research_workflow.hypothesis_discovery import discover_research  # noqa: F401
from jarvis.research_workflow.experiment_designer import design_experiment  # noqa: F401
from jarvis.research_workflow.research_priority import prioritize_research  # noqa: F401
from jarvis.research_workflow.research_gate import build_approval_queue, act as research_gate_act  # noqa: F401
from jarvis.research_workflow.validation_intelligence import build_validation_report  # noqa: F401
from jarvis.research_workflow.research_selection import evaluate_research  # noqa: F401
from jarvis.research_workflow.research_brief import build_research_brief  # noqa: F401
from jarvis.research_workflow.research_loop_v3 import run_research_loop  # noqa: F401
from jarvis.research_workflow.research_metrics_v3 import build_research_metrics  # noqa: F401
from jarvis.research_workflow.research_reflection import reflect as research_reflect  # noqa: F401
from jarvis.research_workflow.autonomous_validation_v3 import validate_loop, audit_production  # noqa: F401
from jarvis.research_workflow.release_v30 import build_release_report_v30  # noqa: F401
# P201 Research Accountability — Forward Prediction Capture + Writer Authority. 기존 rmi_ 재사용, 새 원장 없음.
from jarvis.research_workflow.ledger_writer import WriterAuthority  # noqa: F401
from jarvis.research_workflow.prediction_registry import (  # noqa: F401
    capture_prediction,
    derive_framework,
    evaluate as evaluate_prediction,
    registry_status as prediction_registry_status,
    transition as prediction_transition,
)
# P202 Migration Safety Net — characterization(meaning==meaning) + capture hook + ledger contract.
from jarvis.research_workflow.ledger_writer import JsonlLedgerBackend, LedgerBackend  # noqa: F401
from jarvis.research_workflow.characterization import build_meaning_snapshot, compare_to_golden  # noqa: F401
from jarvis.research_workflow.characterization import build_call_graph, compare_call_graph  # noqa: F401
# P204 Research Discovery Facade — 가설 발견 단일 공개 namespace(내부 모듈 유지·deprecated).
from jarvis.research_workflow import research_discovery  # noqa: F401
# P204.5/P205/P206 Research Accountability — coverage audit · validation score · deprecation registry.
from jarvis.research_workflow.prediction_coverage_audit import build_coverage_audit  # noqa: F401
from jarvis.research_workflow.research_validation_score import build_validation_score  # noqa: F401
from jarvis.research_workflow.governance import deprecations as governance_deprecations  # noqa: F401
# Data integration — 기존 provider 재사용, 데이터만 개선(지능 추가 없음).
from jarvis.research_workflow.data_connection import (  # noqa: F401
    connect_source,
    data_connection_status,
)
from jarvis.research_workflow.research_capture import capture_tracked_research  # noqa: F401
from jarvis.research_workflow.prediction_capture_hook import (  # noqa: F401
    capture_from_agent,
    capture_from_committee,
    capture_from_hypothesis,
    capture_research_output,
)
from jarvis.research_workflow.earnings_intelligence import analyze_earnings  # noqa: F401
from jarvis.research_workflow.insider_flow import analyze_transaction  # noqa: F401
from jarvis.research_workflow.market_data_adapter import MarketEvent, normalize  # noqa: F401
from jarvis.research_workflow.market_data_adapter import ingest as ingest_market_data  # noqa: F401
from jarvis.research_workflow.news_intelligence import analyze_headline  # noqa: F401
from jarvis.research_workflow.supply_chain_impact import propagate as supply_chain_propagate  # noqa: F401
from jarvis.research_workflow.alt_data import observe as alt_data_observe  # noqa: F401
from jarvis.research_workflow.cockpit import build_cockpit  # noqa: F401
from jarvis.research_workflow.council_evolution import deliberate as council_deliberate  # noqa: F401
from jarvis.research_workflow.decision_center import committee_packet, record_decision  # noqa: F401
from jarvis.research_workflow.event_stream import classify_event, stream  # noqa: F401
from jarvis.research_workflow.forward_testing import analyze as forward_analyze  # noqa: F401
from jarvis.research_workflow.market_cockpit import build_market_cockpit  # noqa: F401
from jarvis.research_workflow.opportunity_discovery import discover as discover_opportunities  # noqa: F401
from jarvis.research_workflow.portfolio_sim import simulate as simulate_portfolio  # noqa: F401
from jarvis.research_workflow.regime import detect_regime as detect_market_regime  # noqa: F401
from jarvis.research_workflow.strategy_lab import find_similar, repeated_mistakes, strategy_dna  # noqa: F401
from jarvis.research_workflow.continuous_learning import learning_status, on_research_complete  # noqa: F401
from jarvis.research_workflow.cross_strategy import compare, compare_all  # noqa: F401
from jarvis.research_workflow.health_monitor import build_health  # noqa: F401
from jarvis.research_workflow.knowledge_graph import build_knowledge_graph  # noqa: F401
from jarvis.research_workflow.quality_score import score_research  # noqa: F401
from jarvis.research_workflow.timeline import build_timeline  # noqa: F401
from jarvis.research_workflow.experiment_planner import ExperimentPlanner, ExperimentSpec  # noqa: F401
from jarvis.research_workflow.hypothesis_generator import Hypothesis, HypothesisGenerator  # noqa: F401
from jarvis.research_workflow.research_critic import CritiqueReport, ResearchCritic  # noqa: F401
from jarvis.research_workflow.research_prioritizer import RankedQueue, ResearchPrioritizer  # noqa: F401
from jarvis.research_workflow.session_manager import ResearchSessionManager  # noqa: F401
