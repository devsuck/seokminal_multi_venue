"""jarvis.research_lifecycle — Research Lifecycle Intelligence Layer (P10.26). **생명주기 추적 전용.**

P10.2~P10.25 를 **READ ONLY** 로 참조(파일 기반, import 없음)해 전 모듈에 걸친 연구 생명주기를 추적한다.
연구 프로젝트·생명주기 이벤트·스테이지 전이·병목 기록·생명주기 리포트를 제공하며 생명주기는 IDEA→HYPOTHESIS
→EXPERIMENT→BACKTEST→VALIDATION→DECISION→ARCHIVE 이다. 이벤트 소싱·불변 생명주기 이력·전이 검증·누락
스테이지 탐지를 보장한다.

**실행·배포·승인·거래 없음.** execution/broker/order/portfolio execution/capital allocation/live trading/
permission/risk controller import·호출 없음. LIFECYCLE TRACKING ≠ EXECUTION · TRANSITION ≠ APPROVAL · STAGE ≠
DEPLOYMENT · RECORD ≠ DECISION. append-only 해시체인·결정적·재현. 물리 원장은 rl_ 접두사.
"""
from jarvis.research_lifecycle.engine import ResearchLifecycleEngine  # noqa: F401
from jarvis.research_lifecycle.models import (  # noqa: F401
    ARCHIVE,
    BACKTEST,
    DECISION,
    EXPERIMENT,
    HYPOTHESIS,
    IDEA,
    STAGES,
    VALIDATION,
    BottleneckRecord,
    IllegalTransition,
    ImmutableBottleneckError,
    ImmutableEventError,
    InvalidBottleneckCategory,
    InvalidEventType,
    InvalidStage,
    LifecycleArtifact,
    LifecycleEvent,
    LifecycleReport,
    LifecycleSummary,
    ProjectEvent,
    StageTransition,
    UnknownProject,
)
