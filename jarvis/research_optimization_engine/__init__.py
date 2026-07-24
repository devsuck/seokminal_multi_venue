"""jarvis.research_optimization_engine — Research Optimization Engine Layer (P12.6). **분석·제안 전용.**

전체 연구 생태계를 분석해 최적화 기회를 식별한다 — 병목 탐지·워크플로 최적화 분석·자원 효율 분석·연구 처리량
분석. Optimization Studies·Bottleneck Reports·Efficiency Analysis·Optimization Proposals·Historical Comparisons
를 소유한다(+generate_report 지원 Reports 원장).

**자동으로 최적화하지 않는다.** 최적화 제안은 코드·설정·권한·전략을 변경할 수 없다. execution/broker/portfolio/
risk/permission/deployment/live import·호출 없음. ANALYZE ≠ OPTIMIZE · PROPOSAL ≠ MODIFICATION · IDENTIFIED ≠
EXECUTION. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P9.8~P12.5 는 READ ONLY. 물리 원장은 roe_ 접두사.
"""
from jarvis.research_optimization_engine.engine import ResearchOptimizationEngine  # noqa: F401
from jarvis.research_optimization_engine.models import (  # noqa: F401
    SEVERITIES,
    STUDY_STATES,
    BottleneckRecord,
    ComparisonRecord,
    EfficiencyRecord,
    ForbiddenOptimizationError,
    IllegalStudyTransition,
    ImmutableBottleneckError,
    ImmutableComparisonError,
    ImmutableEfficiencyError,
    ImmutableProposalError,
    ImmutableStudyError,
    IncompleteProposalError,
    InvalidSeverity,
    OptimizationReportRecord,
    OptimizationSummary,
    ProposalRecord,
    StudyEventRecord,
    UnknownStudyError,
)
