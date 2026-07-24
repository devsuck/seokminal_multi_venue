"""jarvis.knowledge_sharing — Cross-Agent Knowledge Sharing (P11.8). **공유·기록 전용.**

연구 에이전트 간 연구 지식·발견·교훈·재사용 아티팩트·구조화된 경험을 교환하는 계층. Knowledge Registry·
Knowledge Topics·Knowledge Entries·Knowledge Sources·Knowledge Links·Knowledge Transfers·Knowledge Consumers·
Knowledge Ratings·Knowledge Snapshots·Knowledge Reports·Knowledge Artifacts·Knowledge Lineage 를 소유한다.

**실행하지 않는다. 연구 결과를 바꾸지 않는다. 상위 원장을 수정하지 않는다. 배포를 승인하지 않는다.**
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. SHARING ≠ EXECUTION · TRANSFER ≠
DEPLOYMENT · REUSE ≠ APPROVAL. 중복 불변·순환·dangling·잘못된 계보 거부. 결정적 ID·재현. 불변·append-only·이벤트
소싱·해시체인. 물리 원장은 ksh_ 접두사.
"""
from jarvis.knowledge_sharing.engine import KnowledgeSharingEngine  # noqa: F401
from jarvis.knowledge_sharing.models import (  # noqa: F401
    ENTRY_STATES,
    KNOWLEDGE_TYPES,
    LINK_TYPES,
    ArtifactRecord,
    CircularReferenceError,
    ConsumerRecord,
    DanglingReferenceError,
    EntryEventRecord,
    IllegalEntryTransition,
    ImmutableEntryError,
    ImmutableRatingError,
    ImmutableTopicError,
    ImmutableTransferError,
    InvalidKnowledgeType,
    InvalidLineageError,
    InvalidLinkType,
    InvalidRating,
    KnowledgeReportRecord,
    LineageRecord,
    LinkRecord,
    RatingRecord,
    RegistryRecord,
    SelfReferenceError,
    SharingSummary,
    SnapshotRecord,
    SourceRecord,
    TopicRecord,
    TransferRecord,
    UnknownEntryError,
    UnknownRegistryError,
    UnknownTopicError,
)
