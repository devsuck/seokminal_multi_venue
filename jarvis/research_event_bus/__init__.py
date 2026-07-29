"""jarvis.research_event_bus — Research Event Bus Layer (P11.11). **통신 인프라 전용.**

내부 연구 이벤트 통신 계층 — 연구 컴포넌트가 연구 생애주기 이벤트를 통제·감사 가능·append-only 방식으로 발행·
소비하게 한다(이벤트 등록·발행·구독 추적·이력·워크플로 동기화·교차계층 관찰성). Event Registry·Event Streams·
Event Messages·Event Subscribers·Event Consumers·Event Routing Rules·Event Snapshots·Event Reports·Event
Artifacts·Event Lineage 를 소유한다(+register_source 지원 Sources 원장).

**거래 실행·배포·전략/모델 수정·자본 배분·권한 변경·자동 승인을 하지 않는다.** execution/broker/portfolio/
risk/permission/deployment/live import·호출 없음. EVENT ≠ EXECUTION · PUBLISH ≠ DEPLOY · ROUTE ≠ APPROVAL.
불변·append-only 해시체인·이벤트 소싱·결정적·재현. 상위 P10.2~P10.8·P11.1~P11.10 은 READ ONLY. 물리 원장은 reb_.
"""
from jarvis.research_event_bus.engine import ResearchEventBusEngine  # noqa: F401
from jarvis.research_event_bus.models import (  # noqa: F401
    CONSUMER_ACTIVITIES,
    EVENT_STATES,
    EVENT_TYPES,
    ArtifactRecord,
    CircularLineageError,
    ConsumerRecord,
    EventBusSummary,
    EventLifecycleRecord,
    EventReportRecord,
    EventTypeRecord,
    IllegalEventTransition,
    ImmutableEventError,
    ImmutableRouteError,
    ImmutableSourceError,
    ImmutableStreamError,
    ImmutableSubscriberError,
    ImmutableTypeError,
    InvalidEventType,
    InvalidRoutingError,
    LineageRecord,
    MissingParentError,
    RouteRecord,
    SnapshotRecord,
    SourceRecord,
    StreamRecord,
    SubscriberRecord,
    UnauthorizedSourceError,
    UnknownEventError,
    UnknownStreamError,
    UnknownSubscriberError,
)
