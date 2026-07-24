"""jarvis.research_agent_coordinator — Research Agent Execution Coordinator Layer (P12.3). **조정·기록 전용.**

연구 작업을 수행하는 연구 에이전트를 조정한다(에이전트 배정·작업 위임·협업 추적·에이전트 진행·연구 핸드오프).
Agent Assignment Registry·Research Task Ownership·Agent Progress Records·Collaboration Sessions·Handoff Records·
Coordinator Reports 를 소유한다.

**외부 행위를 실행하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live import·호출 없음.
COORDINATE ≠ EXECUTION · ASSIGN ≠ AUTHORIZATION · HANDOFF ≠ DEPLOYMENT. 한 작업은 상충 소유자를 가질 수 없고,
핸드오프는 증거가 필요하며, 완료는 기록된 결과가 필요하다. 불변·append-only 해시체인·이벤트 소싱·결정적·재현.
상위 P10.6·P11.13·P12.1·P12.2 는 READ ONLY. 물리 원장은 rac_ 접두사(기존 rco_ 계층과 구별).
"""
from jarvis.research_agent_coordinator.engine import ResearchAgentCoordinatorEngine  # noqa: F401
from jarvis.research_agent_coordinator.models import (  # noqa: F401
    ASSIGNMENT_STATES,
    AgentRegistrationRecord,
    CollaborationRecord,
    ConflictingOwnerError,
    CoordinatorReportRecord,
    CoordinatorSummary,
    HandoffEvidenceError,
    HandoffRecord,
    IllegalAssignmentTransition,
    ImmutableAgentError,
    MissingResultError,
    OwnershipEventRecord,
    ProgressRecord,
    UnknownAgentError,
    UnknownAssignmentError,
)
