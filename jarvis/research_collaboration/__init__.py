"""jarvis.research_collaboration — Multi-Agent Research Collaboration & Human Coordination (P19). **협업·조정·기록 전용.**

연구 에이전트 협업·참여·메시지·제안·동료검토·합의·갈등·사람 검토를 조정·기록만 한다. Research Teams·Collaboration
Sessions·Participation·Messages·Proposals·Peer Reviews·Consensus·Conflicts·Human Reviews·Reports·Lineage 를 소유한다.

**실행 계층이 아니다. 거래하지 않는다. 전략을 배포하지 않는다. 권한을 부여하지 않는다.** execution/broker/portfolio/
permission/deployment/live import·호출 없음. COLLABORATE ≠ EXECUTE · CONSENSUS ≠ APPROVAL · REVIEW ≠ DEPLOYMENT.
불변·append-only·해시체인·이벤트 소싱·결정적·재현. P10.6 agent_governance 등 상위/통합 계층은 READ ONLY. 원장 rcol_ 접두사.
"""
from jarvis.research_collaboration.engine import ResearchCollaborationEngine  # noqa: F401
from jarvis.research_collaboration.models import (  # noqa: F401
    COLLAB_STATES,
    CONFLICT_STATES,
    CONFLICT_TYPES,
    CONSENSUS_POSITIONS,
    CONSENSUS_STATES,
    HUMAN_REVIEW_STATES,
    MESSAGE_TYPES,
    PARTICIPATION_STATES,
    PROPOSAL_STATES,
    REVIEW_CATEGORIES,
    ArtifactRecord,
    CollabEventRecord,
    CollaborationReportRecord,
    CollaborationSummary,
    ConflictEventRecord,
    ConsensusEventRecord,
    HumanReviewEventRecord,
    HumanReviewRequired,
    IllegalTransition,
    ImmutableRecordError,
    MessageRecord,
    ParticipationEventRecord,
    ProposalEventRecord,
    ReviewRecord,
    ReviewerRequired,
    UnknownEntityError,
)
