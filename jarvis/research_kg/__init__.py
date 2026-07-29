"""jarvis.research_kg — Research Knowledge Graph Layer (P10.5). **분석·검색·관계 추적 전용.**

P9.8~P10.4 연구 원장을 **READ ONLY** 로 연결해 연구 엔티티(전략·신호·피처·데이터셋·모델·실험·
백테스트·검증·포트폴리오·리스크분석)와 그 관계·계보·유사도를 지식 그래프로 만든다. 엔티티 생명주기
(REGISTERED→LINKED→ANALYZED→SNAPSHOTTED)·관계(규칙 검증·순환 차단)·계보 파생·유사도(SIMILAR/
RELATED/DISTINCT)·그래프 스냅샷. append-only 해시체인·결정적·재현.

**실행/배포/주문/자본배분/모델적용 권한 없음.** execution/broker/portfolio mutation/risk governor/
permission/live trading/capital allocation/strategy deployment/model promotion import·변경 없음.
VALIDATED ≠ DEPLOYED · RANKED ≠ SELECTED · CONNECTED ≠ ENABLED. 상위 레이어 파일은 읽기만 한다.
기록·분석 목적만. 물리 원장은 kg_ 접두사.
"""
from jarvis.research_kg.engine import ResearchKnowledgeGraphEngine  # noqa: F401
from jarvis.research_kg.models import (  # noqa: F401
    ANALYZED,
    BACKTEST,
    DATASET,
    DISTINCT,
    EXPERIMENT,
    FEATURE,
    LINKED,
    MODEL,
    PORTFOLIO,
    REGISTERED,
    RELATED,
    RISK_ANALYSIS,
    SIGNAL,
    SIMILAR,
    SNAPSHOTTED,
    STRATEGY,
    VALIDATION,
    CycleError,
    EntityEvent,
    GraphArtifact,
    GraphSnapshot,
    IllegalTransition,
    ImmutableEntityError,
    InvalidRelationship,
    LineageEdge,
    Relationship,
    ResearchGraphReport,
    SimilarityReport,
    UnknownEntity,
)
