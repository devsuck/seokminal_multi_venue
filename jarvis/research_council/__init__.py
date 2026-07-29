"""jarvis.research_council — Multi-Agent Research Council (P11.6). **협의·기록 전용.**

여러 연구 에이전트(Data·Strategy·Alpha·Portfolio·Risk·Simulation·Reviewer·Knowledge)로 구성된 협업 연구 협의체.
이 계층은 연구 토론을 조율할 뿐이며 Council Registry·Council Sessions·Participants·Discussion Records·Research
Arguments·Consensus Records·Minority Opinions·Voting Records·Decision Summaries·Council Reports·Artifact Lineage
를 소유한다.

**절대 실행하지 않는다. 절대 배포를 승인하지 않는다. 절대 상위 연구를 수정하지 않는다.** 협의체는 권고만 할 수
있으며 전략 승인·배포·거래·자본 할당·권한 변경·설정 변경·주문 실행·브로커 호출·포트폴리오 수정을 하지 않는다.
execution/broker/portfolio/risk/permission/live/deployment import·호출 없음. COUNCIL ≠ EXECUTION · CONSENSUS ≠
APPROVAL · RECOMMENDATION ≠ DEPLOYMENT. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 물리 원장은 cnl_ 접두사.
"""
from jarvis.research_council.engine import ResearchCouncilEngine  # noqa: F401
from jarvis.research_council.models import (  # noqa: F401
    AGENT_ROLES,
    CONSENSUS_OUTCOMES,
    COUNCIL_STATES,
    VOTE_CHOICES,
    ArgumentRecord,
    ArtifactRecord,
    ConsensusRecord,
    CouncilRecord,
    CouncilReportRecord,
    CouncilSummary,
    DiscussionRecord,
    IllegalSessionTransition,
    ImmutableArgumentError,
    ImmutableConsensusError,
    ImmutableCouncilError,
    ImmutableMinorityError,
    ImmutableParticipantError,
    ImmutableSummaryError,
    ImmutableVoteError,
    InvalidAgentRole,
    InvalidStance,
    InvalidVoteChoice,
    MinorityRecord,
    ParticipantRecord,
    SessionEventRecord,
    SessionStateError,
    SummaryRecord,
    UnknownArgumentError,
    UnknownCouncilError,
    UnknownSessionError,
    VoteRecord,
)
