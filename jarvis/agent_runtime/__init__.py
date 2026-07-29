"""jarvis.agent_runtime — Agent Runtime Layer (P45). **거래·배포·실행·자본 결정 없음.**

연구 에이전트 런타임을 관리한다: 에이전트 생애주기·태스크 배정·산출물·메모리 참조·상태·로그.

**에이전트는 거래·배포·자본 결정을 할 수 없다. 무제한 도구 접근 없음 — 능력 허용목록만.** execution/broker/
live_trading/portfolio_execution import·호출 없음. AGENT RUNTIME ≠ AUTONOMOUS TRADING. 엔진은 execute()/trade()/
deploy()/allocate()/approve() 를 노출하지 않는다. 산출물은 항상 is_binding=False·is_executed=False(사람 검토용).
불변·append-only·해시체인·이벤트 소싱·결정적·재현. 상위 계층은 READ ONLY. 원장 agrt_ 접두사. 기존 P1~P44 불변.
"""
from jarvis.agent_runtime.engine import AgentRuntimeEngine  # noqa: F401
from jarvis.agent_runtime.models import (  # noqa: F401
    AGENT_ROLES,
    AGENT_STATES,
    ALLOWED_CAPABILITIES,
    FORBIDDEN_CAPABILITIES,
    OUTPUT_KINDS,
    AgentEventRecord,
    AgentReportRecord,
    AgentSummary,
    ArtifactRecord,
    ForbiddenCapabilityError,
    IllegalAgentTransition,
    LogRecord,
    MemoryReferenceRecord,
    OutputRecord,
    TaskAssignmentRecord,
    UnknownEntityError,
    can_agent_transition,
    validate_capabilities,
)
