"""jarvis.research_assistant — Personal Research Assistant Layer (P44). **분석만, 결정·승인·집행 없음.**

한 명의 연구자가 Jarvis 산출물을 이해하도록 돕는다: 일일 요약·최근 실험 요약·실패 분석·지식 리캡·연구 진행 요약·
잠재 연구 영역. **기존 원장을 READ ONLY 로 읽어 분석만 한다 — 투자 결정·전략 승인·행동 실행 없음.**
ASSISTANT ANALYZES · DOES NOT DECIDE / APPROVE / EXECUTE. execution/broker/live_trading import·호출 없음. 엔진은
execute()/trade()/deploy()/allocate()/approve()/decide() 를 노출하지 않는다. 결정적·불변·해시체인. 산출 스냅샷은
자체 ras_ 원장에만 append. 기존 P1~P43 불변.
"""
from jarvis.research_assistant.engine import ResearchAssistantEngine  # noqa: F401
from jarvis.research_assistant.models import (  # noqa: F401
    SOURCES,
    AdvisoryNoteRecord,
    AssistantReportRecord,
    AssistantSummary,
    DailySummary,
    ExperimentSummary,
    FailureAnalysis,
    KnowledgeRecap,
    PotentialAreas,
    ProgressSummary,
    is_failure_signal,
    numeric_stats,
)
