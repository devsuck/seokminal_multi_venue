"""jarvis.research_agent_coordination — Autonomous Research Agent Coordination Layer (P26). **협업 조정 전용.**

**ARCHIVED (Phase1 STEP3-B, 2026-07-31):** no active real-import caller found; only historically referenced by security_audit's dynamic AUDIT_TARGETS scan (outside default testpaths). Migration: if security_audit scanning is revived, this is a listed consumer; otherwise safe candidate for full removal in a later phase.

복수 연구 에이전트의 조정·역할 관리·작업 위임 기록·협업 이력·합의 추적·연구 토론 계보를 관리한다. Research Agent
Registry·Agent Role Definitions·Research Team Structures·Agent Collaboration Sessions·Task Delegation Records·
Research Discussion Events·Consensus Records·Coordination Reports·Agent Collaboration Lineage 를 소유한다.

**연구 협업만 관리한다. 거래·주문·자본 배분·전략 배포·라이브 승인·권한 수정·자율 투자 결정 선택을 하지 않는다.**
execution/broker/live_trading/portfolio_execution import·호출 없음. CONSENSUS ≠ APPROVAL · CONSENSUS ≠
DEPLOYMENT · COORDINATION ≠ EXECUTION. 불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층(P10~P25)은
READ ONLY. 원장 racd_ 접두사(rac_ 충돌 회피). 권한·정체성·행동 제한은 P10.6 Agent Governance 소유(중복 없음).
"""
from jarvis.research_agent_coordination.engine import ResearchAgentCoordinator  # noqa: F401
from jarvis.research_agent_coordination.models import (  # noqa: F401
    CONSENSUS_VERDICTS,
    ROLE_EXAMPLES,
    SESSION_STATES,
    TASK_STATES,
    AgentRecord,
    ArtifactRecord,
    ConsensusRecord,
    CoordinationReportRecord,
    CoordinationSummary,
    IllegalSessionTransition,
    IllegalTaskTransition,
    MessageRecord,
    RoleRecord,
    RoleSeparationError,
    SessionEventRecord,
    TaskEventRecord,
    TaskIsolationError,
    TeamRecord,
    UnknownEntityError,
    agreement_score,
    can_session_transition,
    can_task_transition,
    classify_consensus,
    contains_forbidden_action,
)
