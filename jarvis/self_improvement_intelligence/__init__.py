"""jarvis.self_improvement_intelligence — Research Self-Improvement Intelligence (P10.13). **분석·제안 전용.**

P10.2~P10.12 연구 이력을 READ ONLY 로 소비해 연구 효율·검증 공백·반복 실수·실험 설계 품질·워크플로
병목·증거 수집 완성도를 분석하고 개선 기회·권고를 기록한다.

**연구 과정 분석·제안만 수행한다.** research strategy/model/signal 수정·실험 자동 선택·trading 실행·
deploy 없음. execution/broker/portfolio/risk execution/permission/capital allocation import·호출 없음.
IMPROVEMENT SUGGESTION ≠ ACTION · RESEARCH RECOMMENDATION ≠ APPROVAL · INSIGHT ≠ EXECUTION. ACCEPTED 는
사람 인지일 뿐 자동 변경 없음. append-only 해시체인·결정적·재현. 물리 원장은 si_ 접두사(sim_ 과 구별).
"""
from jarvis.self_improvement_intelligence.engine import ResearchSelfImprovementEngine  # noqa: F401
from jarvis.self_improvement_intelligence.models import (  # noqa: F401
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    CREATED,
    HIGH,
    IDENTIFIED,
    LOW,
    MEDIUM,
    REVIEWED,
    BottleneckRecord,
    IllegalTransition,
    ImmutableBottleneckError,
    ImmutableOpportunityError,
    ImmutableTemplateError,
    ImmutableWorkflowError,
    ImprovementArtifact,
    ImprovementEvidence,
    ImprovementReport,
    ImprovementSummary,
    InvalidImprovementLink,
    OpportunityEvent,
    RecommendationEvent,
    TemplateEvolution,
    UnknownOpportunity,
    UnknownRecommendation,
    UnknownWorkflow,
    WorkflowPattern,
)
