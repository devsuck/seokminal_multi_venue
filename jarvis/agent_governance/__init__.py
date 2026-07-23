"""jarvis.agent_governance — Agent Research Governance Layer (P10.6). **연구 에이전트 관리·감사 전용.**

AI 연구 에이전트의 정체성·능력(메타데이터)·연구요청·실험제안·행동감사·사람검토·연구예산·계보를
관리한다. **AI Agent 는 연구 보조자이며 실행 권한이 없다.** 주문/전략배포/live trading/portfolio 변경/
capital allocation/permission 변경/risk threshold 변경/model promotion/execution 호출 없음. 금지
능력·행동은 거부 또는 BLOCKED 기록만. 자동 승인 금지(사람 검토 필수).

Agent VALIDATED ≠ APPROVED FOR TRADING · Research completed ≠ Deployment · Proposal ACCEPTED ≠
Execution permission. P9.8~P10.5 를 READ ONLY 로 참조. append-only 해시체인·결정적·재현.
물리 원장은 arg_ 접두사(P9.10 access_governance 의 ag_ 와 충돌 회피).
"""
from jarvis.agent_governance.engine import AgentGovernanceEngine  # noqa: F401
from jarvis.agent_governance.models import (  # noqa: F401
    ACCEPTED,
    ACTIVE,
    APPROVE,
    APPROVED,
    COMPLETED,
    CREATED,
    DRAFT,
    REGISTERED,
    REJECT,
    REJECTED,
    REQUEST_CHANGE,
    RETIRED,
    REVIEWED,
    REVIEWING,
    RUNNING,
    SUBMITTED,
    SUSPENDED,
    AgentAction,
    AgentArtifact,
    AgentEvent,
    AgentGovernanceReport,
    BudgetRecord,
    Capability,
    ForbiddenCapability,
    HumanApprovalRequired,
    HumanReview,
    IllegalTransition,
    ImmutableAgentError,
    ImmutableRequestError,
    ProposalEvent,
    ResearchRequestEvent,
    UnknownProposal,
)
