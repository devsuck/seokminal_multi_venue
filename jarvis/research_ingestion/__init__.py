"""jarvis.research_ingestion — Research Data Pipeline (P53). **통합 오케스트레이터, 실행 없음.**

완료된 백테스트 결과를 기존 실험 원장(expt_)·실패 메모리(rmi_)로 흘려보낸다. 그 결과 research_assistant 의
recall/failure_intelligence/perspectives 가 실데이터로 채워진다. **새 실험/실패 저장소를 만들지 않는다 — 기존 엔진
API 재사용(Integration over Expansion).** 결정적 결과 판정 + 9종 실패 자동분류 + 멱등. 거래·집행·배포 없음.
기존 P1~P52 불변. 원장 ring_ 접두사(수집 감사만).
"""
from jarvis.research_ingestion.backtest_adapter import (  # noqa: F401
    adapt,
    ingest_backtest,
    ingest_backtests,
)
from jarvis.research_ingestion.engine import ResearchIngestionEngine  # noqa: F401
from jarvis.research_ingestion.history_importer import (  # noqa: F401
    HistoricalResearchImporter,
    ImportSummary,
    map_record,
    read_records,
)
from jarvis.research_ingestion.models import (  # noqa: F401
    OUTCOMES,
    REQUIRED_VALIDATIONS,
    IngestionRecord,
    IngestionResult,
    SchemaError,
    auto_classify_failure,
    classify_outcome,
    validate_backtest,
)
