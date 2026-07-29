"""jarvis.research_memory_system — Research Memory System Layer (P11.12). **기억 시스템 전용.**

장기 연구 기억 계층 — 연구 생태계 전반의 역사적 연구 지식을 저장·조직·검색·분석한다(연구 이력 보존·실험 기억·
실패 접근 추적·재사용 지식 발굴·방법론 회상·연구 맥락 검색·유사도 기반 기억 조회). Memory Registry·Research
Memories·Knowledge Entries·Experiment Memories·Failure Memories·Success Patterns·Research Context Records·
Memory Associations·Memory Snapshots·Memory Reports·Artifact Lineage 를 소유한다(+검색 기록 Search 원장).

**전략 실행·연구결과 수정·모델/거래 승인·배포·권한 변경·상위 데이터 변경을 하지 않는다.** execution/broker/
portfolio/risk/permission/deployment/live import·호출 없음. 기억은 삭제·덮어쓰기·재작성이 없고 새 정보는 새 기억
이벤트를 만든다. MEMORY ≠ EXECUTION · RECALL ≠ APPROVAL · PATTERN ≠ DEPLOYMENT. 불변·append-only 해시체인·
이벤트 소싱·결정적·재현. 유사도는 결정적·설명가능·기록된다. 상위 P10.1~P10.8·P11.1~P11.11 은 READ ONLY.
물리 원장은 rmem_ 접두사(기존 rm_ 계층과 구별).
"""
from jarvis.research_memory_system.engine import ResearchMemorySystemEngine  # noqa: F401
from jarvis.research_memory_system.models import (  # noqa: F401
    MEMORY_STATES,
    MEMORY_TYPES,
    SEARCH_MODES,
    ArtifactRecord,
    AssociationRecord,
    CircularAssociationError,
    ContextRecord,
    DanglingReferenceError,
    ExperimentMemoryRecord,
    FailureMemoryRecord,
    IllegalMemoryTransition,
    ImmutableAssociationError,
    ImmutableContextError,
    ImmutableExperimentError,
    ImmutableFailureError,
    ImmutableKnowledgeError,
    ImmutableMemoryError,
    ImmutablePatternError,
    ImmutableReportError,
    InvalidMemoryType,
    InvalidSearchMode,
    KnowledgeEntryRecord,
    MemoryEventRecord,
    MemoryReportRecord,
    MemorySummary,
    MissingSourceError,
    RegistryRecord,
    SearchRecord,
    SnapshotRecord,
    SuccessPatternRecord,
    UnknownMemoryError,
    UnknownRegistryError,
)
