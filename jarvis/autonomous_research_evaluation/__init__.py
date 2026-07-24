"""jarvis.autonomous_research_evaluation — Autonomous Research Evaluation Layer (P12.5). **평가·기록 전용.**

자율 연구 사이클을 평가한다 — 연구 품질·재현성·증거 강도·효율·강건성·지식 기여를 측정한다. Evaluation Registry·
Evaluation Criteria·Research Scores·Quality Reports·Benchmark Records·Evaluation Lineage 를 소유한다.

**점수는 승인이 아니고 배포 권한이 아니다.** execution/broker/portfolio/risk/permission/deployment/live import·
호출 없음. SCORE ≠ APPROVAL · SCORE ≠ DEPLOYMENT PERMISSION · EVALUATION ≠ SELECTION. 불변·append-only 해시체인·
이벤트 소싱·결정적·재현. 상위 P12.1~P12.4·P10.7 은 READ ONLY. 물리 원장은 are_ 접두사.
"""
from jarvis.autonomous_research_evaluation.engine import AutonomousResearchEvaluationEngine  # noqa: F401,E501
from jarvis.autonomous_research_evaluation.models import (  # noqa: F401
    EVAL_DIMENSIONS,
    EVAL_STATES,
    ArtifactRecord,
    BenchmarkRecord,
    CriterionRecord,
    EvaluationEventRecord,
    EvaluationSummary,
    IllegalEvalTransition,
    ImmutableBenchmarkError,
    ImmutableCriterionError,
    ImmutableEvaluationError,
    ImmutableScoreError,
    InvalidDimension,
    QualityReportRecord,
    ScoreRecord,
    UnknownCriterionError,
    UnknownEvaluationError,
)
