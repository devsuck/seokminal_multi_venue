"""jarvis.governance_memory — Research Governance Knowledge Memory Layer (P10.21). **저장·조회 전용.**

P9.8~P10.20 전 계층을 **READ ONLY** 로 참조(파일 기반, import 없음)해 재사용 가능한 거버넌스 지식을 저장한다.
지식 항목 레지스트리·거버넌스 메모리 기록·경험 기록·해소 이력·유사도 참조·메모리 스냅샷·지식 리포트·메모리
계보를 제공하며 과거 연구 교훈·반복 이슈 해소·검증 경험·거버넌스 패턴·역사적 맥락을 축적한다.

**의사결정 실행·정책 변경·config 수정·strategy 승인·model 배포 없음.** execution/broker/order/portfolio
execution/capital allocation/live trading/permission/risk controller import·호출 없음. MEMORY ≠ AUTHORITY ·
SIMILARITY ≠ DECISION · HISTORICAL PATTERN ≠ FUTURE ACTION · KNOWLEDGE ≠ PERMISSION. append-only 해시체인·
결정적·재현. 물리 원장은 gm_ 접두사(gm_ ≠ mg_ Model Governance).
"""
from jarvis.governance_memory.engine import GovernanceMemoryEngine  # noqa: F401
from jarvis.governance_memory.models import (  # noqa: F401
    CONTRADICTS,
    DERIVED_FROM,
    ENTRY_CATEGORIES,
    LINK_TYPES,
    RELATED_TO,
    SIMILAR_TO,
    ExperienceRecord,
    ImmutableEntryError,
    ImmutableExperienceError,
    ImmutableLessonError,
    ImmutableResolutionError,
    InvalidEntryCategory,
    InvalidLinkType,
    InvalidMemoryLink,
    KnowledgeEntry,
    KnowledgeReport,
    LessonRecord,
    MemoryArtifact,
    MemoryLink,
    MemorySnapshot,
    MemorySummary,
    ResolutionHistory,
    UnknownSnapshot,
)
