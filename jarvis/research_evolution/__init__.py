"""jarvis.research_evolution — Research Evolution Governance Layer (P10.16). **저장·분석·기록 전용.**

이전 연구 산출물(성공/실패)을 READ ONLY 로 소비해 무엇이 통했는가·무엇이 실패했는가·왜 실패했는가·무엇을
개선할 수 있는가·어떤 후속 연구 질문이 남는가를 구조화된 불변 학습 기록으로 전환한다. 연구 객체 등록·실패 패턴
분석·개선 제안·이터레이션·학습 기록·지식 이전·진화 사이클을 남기며, 계보 무결성·결정적 재현·변조 탐지를 보장한다.

**strategy/signal/model/parameter 수정 없음·배포 없음·실행 트리거 없음·자본 배분 없음.** execution/broker/
order/portfolio execution/capital allocation/live trading/permission/risk controller import·호출 없음.
LEARNING ≠ MODIFICATION · PROPOSAL ≠ APPROVAL · ACCEPTED ≠ DEPLOYMENT · IMPLEMENTED(record) ≠ PRODUCTION
CHANGE. append-only 해시체인·결정적·재현. 물리 원장은 ev_ 접두사.
"""
from jarvis.research_evolution.engine import ResearchEvolutionEngine  # noqa: F401
from jarvis.research_evolution.models import (  # noqa: F401
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    CREATED,
    DRAFT,
    FAILURE_CATEGORIES,
    IMPLEMENTED,
    LEARNING_CAPTURED,
    REVIEWING,
    EvolutionArtifact,
    EvolutionCycleEvent,
    EvolutionReport,
    EvolutionSummary,
    FailurePattern,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableLearningError,
    ImmutableResearchObjectError,
    ImmutableTransferError,
    ImprovementProposalEvent,
    InvalidFailureCategory,
    InvalidLineageLink,
    IterationRecord,
    KnowledgeTransferRecord,
    LearningRecord,
    ResearchObject,
    UnknownCycle,
    UnknownProposal,
    UnknownResearchObject,
)
