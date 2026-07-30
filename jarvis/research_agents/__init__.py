"""jarvis.research_agents — Research Agent Framework (P11.1). **연구 보조 전용.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found; references elsewhere are string-fixture defaults / declarative ledger keys only, not imports. Migration: no active consumer identified; re-evaluate for full removal in a later phase.

연구를 보조하는 AI 에이전트 계층(Phase 11 시작). Data Analyst·Strategy Research·Backtest Analyst·Risk Analyst·
Reviewer 5종 에이전트가 Research OS 를 **READ ONLY** 로 참조(파일 기반, import 없음)해 읽기·분석·리포트만 수행하고
Agent Registry·Agent Profiles·Agent Tasks·Agent Messages·Agent Reports 를 남긴다.

**에이전트는 연구 보조원일 뿐이다.** 허용: READ·ANALYZE·REPORT. 금지·차단: TRADE·EXECUTE·DEPLOY·ALLOCATE.
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. ASSIST ≠ EXECUTE · ANALYZE ≠ TRADE · REPORT ≠ DEPLOY. 모든 활동은 append-only 감사 원장에 남는다.
불변·해시체인·결정적·재현. 물리 원장은 ragt_ 접두사.
"""
from jarvis.research_agents.engine import ResearchAgentEngine  # noqa: F401
from jarvis.research_agents.models import (  # noqa: F401
    AGENT_TYPES,
    ALLOWED_CAPABILITIES,
    FORBIDDEN_ACTIONS,
    TASK_STATES,
    ActivityRecord,
    AgentProfileRecord,
    AgentRecord,
    AgentReportRecord,
    AgentSummary,
    CapabilityDenied,
    ForbiddenAgentAction,
    IllegalAgentTransition,
    IllegalTaskTransition,
    ImmutableAgentError,
    ImmutableMessageError,
    ImmutableProfileError,
    ImmutableReportError,
    InvalidAgentType,
    InvalidCapability,
    MessageRecord,
    TaskEventRecord,
    UnknownAgentError,
)
