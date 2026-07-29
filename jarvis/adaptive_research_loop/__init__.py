"""jarvis.adaptive_research_loop — Adaptive Research Loop Layer (P12.4). **개선 기록 전용.**

연구 프로세스를 개선하는 피드백 루프 — 실패 실험 분석·개선 제안·워크플로 적응·연구 효율 추적을 관리한다.
Research Feedback·Improvement Proposals·Loop Cycles·Efficiency Metrics·Adaptation History·Reports 를 소유한다.

**개선을 기록만 하며 자동 수정을 하지 않는다.** 개선 제안은 모델·전략·권한을 수정할 수 없고 인간 리뷰 기록이
필요하다. execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. IMPROVEMENT ≠ EXECUTION ·
PROPOSAL ≠ MODIFICATION · RECORDED ≠ DEPLOYMENT. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P12.1·
P12.2·P12.3·P11.10 은 READ ONLY. 물리 원장은 arl_ 접두사.
"""
from jarvis.adaptive_research_loop.engine import AdaptiveResearchLoopEngine  # noqa: F401
from jarvis.adaptive_research_loop.models import (  # noqa: F401
    ADAPTATION_CATEGORIES,
    DECISIONS,
    LOOP_STATES,
    AdaptationRecord,
    EfficiencyMetricRecord,
    FeedbackRecord,
    ForbiddenModificationError,
    IllegalLoopTransition,
    ImmutableCycleError,
    ImmutableFeedbackError,
    ImmutableProposalError,
    InvalidCategory,
    InvalidDecision,
    LoopCycleRecord,
    LoopReportRecord,
    LoopSummary,
    MissingReviewError,
    ProposalEventRecord,
    UnknownCycleError,
    UnknownProposalError,
)
