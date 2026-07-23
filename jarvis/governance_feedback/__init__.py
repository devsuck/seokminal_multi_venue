"""jarvis.governance_feedback — Research Governance Feedback Intelligence Layer (P10.20). **분석 전용.**

P9.8~P10.19 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 거버넌스 폐루프 학습 기록을 만든다.
피드백 레지스트리·거버넌스 이슈 레지스트리·패턴 탐지 기록·개선 테마 레지스트리·피드백 집계·거버넌스 추세
리포트·피드백 계보를 제공하며 반복 이슈·재발 실패·개선 기회·과거 해소·장기 추세를 추적한다.

**정책 수정·permission 변경·config 변경·자동 이슈 수정·변경 승인 없음.** execution/broker/order/portfolio
execution/capital allocation/live trading/permission/risk controller import·호출 없음. FEEDBACK ≠ CHANGE ·
PATTERN ≠ DECISION · RECOMMENDATION ≠ IMPLEMENTATION · TREND ≠ AUTOMATIC ACTION. append-only 해시체인·
결정적·재현. 물리 원장은 gf_ 접두사.
"""
from jarvis.governance_feedback.engine import GovernanceFeedbackEngine  # noqa: F401
from jarvis.governance_feedback.models import (  # noqa: F401
    ACKNOWLEDGE,
    ANALYZED,
    ARCHIVED,
    DECLINING,
    DETECTED,
    ESCALATE,
    FEEDBACK_CATEGORIES,
    IMPROVING,
    MONITOR,
    STABLE,
    TRACKED,
    AggregationRecord,
    FeedbackArtifact,
    FeedbackRecord,
    FeedbackReview,
    FeedbackSummary,
    GovernanceIssueEvent,
    GovernanceTrendReport,
    IllegalTransition,
    ImmutableFeedbackError,
    ImmutablePatternError,
    ImmutableThemeError,
    ImprovementTheme,
    InvalidFeedbackCategory,
    InvalidReviewDecision,
    PatternRecord,
    UnknownIssue,
)
