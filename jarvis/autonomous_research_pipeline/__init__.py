"""jarvis.autonomous_research_pipeline — Autonomous Research Pipeline Core Layer (P12.1). **오케스트레이션 전용.**

중앙 연구 자동화 파이프라인 — 고립된 연구 컴포넌트를 반복 가능한 연구 사이클로 전환한다(연구 목표 인테이크·가설
생성·실험 계획·실험 실행 조정·결과 수집·리뷰 라우팅·지식 영속화·개선 사이클). Research Pipeline Registry·Research
Cycles·Research Objectives·Pipeline Runs·Workflow Stages·Stage Transitions·Pipeline Artifacts·Pipeline Reports·
Execution History Records 를 소유한다.

**거래 실행·전략 배포·자본 배분·라이브 시스템 수정·프로덕션 모델 승인·권한 변경을 하지 않는다.** execution/
broker/portfolio/risk/permission/deployment/live import·호출 없음. PIPELINE ≠ EXECUTION · STAGE ≠ DEPLOYMENT ·
COLLECT ≠ APPROVAL. 불변·append-only 해시체인·이벤트 소싱·결정적·재현. 스킵·역행·무단 완료 전이는 거부된다.
상위 P9.8/P9.9·P10.1~P10.8·P11.1~P11.13 은 READ ONLY. 물리 원장은 arp_ 접두사.
"""
from jarvis.autonomous_research_pipeline.engine import AutonomousResearchPipelineEngine  # noqa: F401
from jarvis.autonomous_research_pipeline.models import (  # noqa: F401
    CYCLE_STAGES,
    PIPELINE_COMPONENTS,
    REF_TYPES,
    ArtifactRecord,
    CycleRecord,
    DanglingReferenceError,
    HistoryRecord,
    IllegalStageTransition,
    ImmutableCycleError,
    ImmutableObjectiveError,
    ImmutablePipelineError,
    ImmutableRunError,
    ImmutableStageError,
    InvalidReferenceType,
    MissingArtifactError,
    ObjectiveRecord,
    PipelineRecord,
    PipelineReportRecord,
    PipelineSummary,
    RunRecord,
    StageRecord,
    TransitionRecord,
    UnknownCycleError,
    UnknownObjectiveError,
    UnknownPipelineError,
)
