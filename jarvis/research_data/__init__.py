"""jarvis.research_data — Research Data Platform & Data Governance (P10.1). **연구 데이터 관리 전용.**

데이터셋/피처를 불변 버전으로 등록하고 스키마 검증·데이터 품질(EXCELLENT/GOOD/WARNING/FAILED)·
lineage(사이클 차단)·재현 스냅샷을 관리한다. append-only 해시체인·결정적·재현가능.

**전략 실행·주문·포트폴리오·브로커·live capital 없음.** execution/live/gateway/broker/portfolio/
risk거버너/paper/strategy runtime import·coupling 없음. 외부 데이터는 injected/file reader 로만 소비.
"""
from jarvis.research_data.engine import ResearchDataEngine  # noqa: F401
from jarvis.research_data.models import (  # noqa: F401
    EXCELLENT,
    FAILED,
    GOOD,
    WARNING,
    DataLineageRecord,
    DataQualityReport,
    DatasetMetadata,
    FeatureMetadata,
    ImmutableDatasetError,
    ImmutableFeatureError,
    LineageError,
    ResearchDataSummary,
    ResearchSnapshot,
)
