"""Research Event Bus Engine (P11.11) — 내부 연구 이벤트 통신. **통신 인프라 전용.**

연구 컴포넌트가 연구 생애주기 이벤트를 통제·감사 가능·append-only 로 발행·소비하게 한다. **거래 실행·배포·
전략/모델 수정·자본 배분·권한 변경·자동 승인을 하지 않는다.** execution/broker/portfolio/risk/permission/
deployment/live import·호출 없음. EVENT ≠ EXECUTION · PUBLISH ≠ DEPLOY · ROUTE ≠ APPROVAL. 결정적·불변·
append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_event_bus import ledger
from jarvis.research_event_bus.models import (
    ACT_CONSUMED,
    ACT_DELIVERED,
    ART_EVENT,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_STREAM,
    CONSUMER_ACTIVITIES,
    E_ARCHIVED,
    E_CONSUMED,
    E_CREATED,
    E_PUBLISHED,
    E_ROUTED,
    EVENT_TYPES,
    GENESIS,
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
    ancestors,
    artifact_id as _artifact_id,
    can_transition,
    consumer_record_id as _consumer_record_id,
    content_hash,
    detect_cycle,
    event_id as _event_id,
    event_lifecycle_id as _event_lifecycle_id,
    event_type_id as _event_type_id,
    input_digest,
    lineage_id as _lineage_id,
    payload_digest,
    report_id as _report_id,
    route_id as _route_id,
    snapshot_id as _snapshot_id,
    source_record_id as _source_record_id,
    stream_id as _stream_id,
    subscriber_id as _subscriber_id,
)

_DISCLAIMER = ("Research Event Bus 데이터 — EVENT ≠ EXECUTION · PUBLISH ≠ DEPLOY · ROUTE ≠ APPROVAL. 내부 "
               "연구 이벤트 통신·기록 전용 — 거래 실행·배포·전략/모델 수정·자본 배분·권한/설정 변경·자동 승인 "
               "없음. 통신 인프라일 뿐이다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchEventBusEngine:
    """내부 연구 이벤트 버스 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/배포/승인/수정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ register_event_type ══════════════
    def register_event_type(self, event_type: str, description: str = "", category: str = "",
                          now: str = "", *, commit: bool = False) -> EventTypeRecord:
        """이벤트 유형 등록(불변). 표준 10유형 외 커스텀 허용. **정의·기록만.**"""
        tid = _event_type_id(event_type)
        existing = ledger.get_type(tid)
        if existing is not None:
            if existing.get("description") != description:
                raise ImmutableTypeError(f"{tid} 이벤트 유형 불변 — 변경 불가")
            return EventTypeRecord(**{k: v for k, v in existing.items()
                                      if k in EventTypeRecord.__dataclass_fields__})
        rec = EventTypeRecord(event_type_id=tid, event_type=event_type, description=description,
                              category=category, created_at=now,
                              input_hash=input_digest(event_type),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.type_exists(tid):
            head = ledger.types_head()
            ledger.append_type(_seal(rec, head["record_hash"] if head else GENESIS))
        return EventTypeRecord(**rec)

    def _require_type(self, event_type: str) -> None:
        if not ledger.type_exists(_event_type_id(event_type)):
            raise InvalidEventType(f"미등록 이벤트 유형 {event_type}")

    # ══════════════ register_source ══════════════
    def register_source(self, source_layer: str, source_id: str, note: str = "", now: str = "",
                      *, commit: bool = False) -> SourceRecord:
        """인가 이벤트 소스 등록(불변). 발행 소스 권한 검증에 사용. **등록·기록만.**"""
        sid = _source_record_id(source_layer, source_id)
        existing = ledger.get_source(sid)
        if existing is not None:
            return SourceRecord(**{k: v for k, v in existing.items()
                                   if k in SourceRecord.__dataclass_fields__})
        rec = SourceRecord(source_record_id=sid, source_layer=source_layer, source_id=source_id,
                           note=note, registered_at=now,
                           input_hash=input_digest(source_layer, source_id),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.source_exists(sid):
            head = ledger.sources_head()
            ledger.append_source(_seal(rec, head["record_hash"] if head else GENESIS))
        return SourceRecord(**rec)

    def _is_authorized(self, source_layer: str, source_id: str) -> bool:
        return (source_layer in ledger.SOURCE_LEDGERS
                or ledger.source_registered(source_layer, source_id))

    # ══════════════ build_event_stream ══════════════
    def build_event_stream(self, name: str, event_type_filter: str = "", description: str = "",
                         now: str = "", *, commit: bool = False) -> StreamRecord:
        """이벤트 스트림 정의(불변, 유형 필터). **정의·기록만.**"""
        sid = _stream_id(name)
        existing = ledger.get_stream(sid)
        if existing is not None:
            if existing.get("event_type_filter") != event_type_filter:
                raise ImmutableStreamError(f"{sid} 스트림 불변 — 변경 불가")
            return StreamRecord(**{k: v for k, v in existing.items()
                                   if k in StreamRecord.__dataclass_fields__})
        rec = StreamRecord(stream_id=sid, name=name, event_type_filter=event_type_filter,
                           description=description, created_at=now, input_hash=input_digest(name),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.stream_exists(sid):
            head = ledger.streams_head()
            ledger.append_stream(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_STREAM, sid, "", now, commit=commit)
        return StreamRecord(**rec)

    def stream_events(self, name: str) -> list[str]:
        """스트림 필터에 해당하는 이벤트 id(append 순, 결정적)."""
        s = ledger.get_stream(_stream_id(name))
        if s is None:
            raise UnknownStreamError(f"미등록 스트림 {name}")
        flt = s.get("event_type_filter") or ""
        seen: list = []
        for r in ledger.read_events():
            if r.get("from_state") == GENESIS:
                if not flt or r.get("event_type") == flt:
                    seen.append(r.get("event_id"))
        return seen

    # ══════════════ 이벤트 생애주기(event-sourced) ══════════════
    def _event_lifecycle(self, event: str, event_type: str, source_layer: str, source_id: str,
                       payload_hash: str, parent_event: str, metadata: dict, authorized: bool,
                       frm: str, to: str, note: str, now: str, *, commit: bool) -> EventLifecycleRecord:
        seq = len(ledger.event_records(event))
        eid = _event_lifecycle_id(event, to, seq)
        rec = EventLifecycleRecord(
            event_lifecycle_id=eid, event_id=event, event_type=event_type, source_layer=source_layer,
            source_id=source_id, payload_hash=payload_hash, parent_event=parent_event,
            metadata=dict(sorted((metadata or {}).items())), authorized=authorized, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(event, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_lifecycle_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return EventLifecycleRecord(**rec)

    def _event_meta(self, event: str) -> dict:
        evs = ledger.event_records(event)
        if not evs:
            raise UnknownEventError(f"미등록 이벤트 {event}")
        g = evs[0]
        return {"event_id": event, "event_type": g.get("event_type"),
                "source_layer": g.get("source_layer"), "source_id": g.get("source_id"),
                "payload_hash": g.get("payload_hash"), "parent_event": g.get("parent_event"),
                "metadata": g.get("metadata", {}), "authorized": g.get("authorized"),
                "state": evs[-1].get("to_state")}

    def current_state(self, event: str) -> str | None:
        evs = ledger.event_records(event)
        return evs[-1].get("to_state") if evs else None

    def _require_event(self, event: str) -> str:
        st = self.current_state(event)
        if st is None:
            raise UnknownEventError(f"미등록 이벤트 {event}")
        return st

    def _transition(self, event: str, to: str, note: str, now: str,
                  *, commit: bool) -> EventLifecycleRecord:
        frm = self._require_event(event)
        if not can_transition(frm, to):
            raise IllegalEventTransition(f"{event} {frm}→{to} 불가")
        m = self._event_meta(event)
        return self._event_lifecycle(event, m["event_type"], m["source_layer"], m["source_id"],
                                     m["payload_hash"], m["parent_event"], m["metadata"],
                                     m["authorized"], frm, to, note, now, commit=commit)

    # ══════════════ publish_event ══════════════
    def _lineage_edges(self) -> list:
        return [(r.get("event_id"), r.get("parent_event")) for r in ledger.read_lineage()
                if r.get("parent_event")]

    def publish_event(self, event_type: str, source_layer: str, source_id: str, payload=None,
                    parent_event: str = "", metadata: dict = None, now: str = "",
                    *, commit: bool = False, require_source: bool = False) -> EventLifecycleRecord:
        """이벤트 발행(CREATED→PUBLISHED). 페이로드는 해시만 저장. 부모 dangling/순환 거부. **발행·기록만.**"""
        self._require_type(event_type)
        authorized = self._is_authorized(source_layer, source_id)
        if require_source and not authorized:
            raise UnauthorizedSourceError(f"미인가 소스 {source_layer}:{source_id}")
        phash = payload_digest(payload)
        eid = _event_id(source_layer, source_id, event_type, phash)
        existing = ledger.event_records(eid)
        if existing:
            g = existing[0]
            if g.get("payload_hash") != phash:
                raise ImmutableEventError(f"{eid} 이벤트 불변 — 페이로드 변경 거부")
            return EventLifecycleRecord(**{k: v for k, v in existing[0].items()
                                           if k in EventLifecycleRecord.__dataclass_fields__})
        if parent_event:
            if not ledger.event_records(parent_event):
                raise MissingParentError(f"부모 이벤트 없음 {parent_event}")
            edges = self._lineage_edges() + [(eid, parent_event)]
            if detect_cycle(edges):
                raise CircularLineageError(f"순환 이벤트 계보 — 거부 {eid}->{parent_event}")
        md = dict(sorted((metadata or {}).items()))
        # 계보 기록
        lid = _lineage_id(eid)
        lrec = LineageRecord(lineage_id=lid, event_id=eid, parent_event=parent_event, created_at=now,
                             input_hash=input_digest(eid), previous_hash=GENESIS).to_dict()
        lrec["record_hash"] = content_hash(lrec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage(_seal(lrec, head["record_hash"] if head else GENESIS))
        # 생애주기: CREATED → PUBLISHED
        self._event_lifecycle(eid, event_type, source_layer, source_id, phash, parent_event, md,
                              authorized, GENESIS, E_CREATED, "created", now, commit=commit)
        parent_art = _artifact_id(ART_EVENT, parent_event) if parent_event else ""
        self._artifact(ART_EVENT, eid,
                       parent_art if parent_event and ledger.artifact_exists(parent_art) else "",
                       now, commit=commit)
        return self._event_lifecycle(eid, event_type, source_layer, source_id, phash, parent_event,
                                     md, authorized, E_CREATED, E_PUBLISHED, "published", now,
                                     commit=commit)

    def trace_event_lineage(self, event: str) -> list:
        return ancestors(self._lineage_edges(), event)

    # ══════════════ register_subscriber ══════════════
    def register_subscriber(self, name: str, event_type: str, source_layer_filter: str = "",
                          now: str = "", *, commit: bool = False) -> SubscriberRecord:
        """구독자 등록(불변, 유형별). **등록·기록만.**"""
        self._require_type(event_type)
        sid = _subscriber_id(name, event_type)
        existing = ledger.get_subscriber(sid)
        if existing is not None:
            if existing.get("source_layer_filter") != source_layer_filter:
                raise ImmutableSubscriberError(f"{sid} 구독자 불변 — 변경 불가")
            return SubscriberRecord(**{k: v for k, v in existing.items()
                                       if k in SubscriberRecord.__dataclass_fields__})
        rec = SubscriberRecord(subscriber_id=sid, name=name, event_type=event_type,
                               source_layer_filter=source_layer_filter, registered_at=now,
                               input_hash=input_digest(name, event_type),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.subscriber_exists(sid):
            head = ledger.subscribers_head()
            ledger.append_subscriber(_seal(rec, head["record_hash"] if head else GENESIS))
        return SubscriberRecord(**rec)

    def _require_subscriber(self, subscriber: str) -> dict:
        rec = ledger.get_subscriber(subscriber)
        if rec is None:
            raise UnknownSubscriberError(f"미등록 구독자 {subscriber}")
        return rec

    # ══════════════ register_route (routing rule) ══════════════
    def register_route(self, event_type: str, target_subscriber: str, condition: str = "",
                     now: str = "", *, commit: bool = False) -> RouteRecord:
        """라우팅 규칙 등록(불변). 유형·구독자 미등록 시 거부(invalid routing). **정의·기록만.**"""
        self._require_type(event_type)
        sub = ledger.get_subscriber(target_subscriber)
        if sub is None:
            raise InvalidRoutingError(f"미등록 라우팅 대상 구독자 {target_subscriber}")
        if sub.get("event_type") != event_type:
            raise InvalidRoutingError(
                f"구독자 유형 불일치 {target_subscriber}:{sub.get('event_type')}≠{event_type}")
        rid = _route_id(event_type, target_subscriber)
        existing = ledger.route_exists(rid)
        rec = RouteRecord(route_id=rid, event_type=event_type, target_subscriber=target_subscriber,
                          condition=condition, created_at=now,
                          input_hash=input_digest(event_type, target_subscriber),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not existing:
            head = ledger.routes_head()
            ledger.append_route(_seal(rec, head["record_hash"] if head else GENESIS))
        return RouteRecord(**rec)

    # ══════════════ track_delivery ══════════════
    def track_delivery(self, event: str, subscriber: str, note: str = "", now: str = "",
                     *, commit: bool = False) -> ConsumerRecord:
        """전달 추적(PUBLISHED/ROUTED→ROUTED). 구독자·이벤트 검증. **기록만.**"""
        st = self._require_event(event)
        self._require_subscriber(subscriber)
        if st in (E_PUBLISHED, E_ROUTED):
            self._transition(event, E_ROUTED, "routed", now, commit=commit)
        return self._consumer_record(event, subscriber, ACT_DELIVERED, note or "delivered", now,
                                     commit=commit)

    def _consumer_record(self, event: str, subscriber: str, activity: str, note: str, now: str,
                       *, commit: bool) -> ConsumerRecord:
        seq = len([r for r in ledger.event_consumers(event)
                   if r.get("subscriber") == subscriber and r.get("activity") == activity])
        cid = _consumer_record_id(event, subscriber, activity, seq)
        rec = ConsumerRecord(consumer_record_id=cid, event_id=event, subscriber=subscriber,
                             activity=activity, note=note, recorded_at=now,
                             input_hash=input_digest(event, subscriber, activity, seq),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.consumer_exists(cid):
            head = ledger.consumers_head()
            ledger.append_consumer(_seal(rec, head["record_hash"] if head else GENESIS))
        return ConsumerRecord(**rec)

    # ══════════════ consume_event ══════════════
    def consume_event(self, event: str, subscriber: str, note: str = "", now: str = "",
                    *, commit: bool = False) -> ConsumerRecord:
        """이벤트 소비(→CONSUMED). 구독자·이벤트 검증. **소비 기록만 — 실행 아님.**"""
        st = self._require_event(event)
        self._require_subscriber(subscriber)
        if st in (E_PUBLISHED, E_ROUTED, E_CONSUMED):
            self._transition(event, E_CONSUMED, "consumed", now, commit=commit)
        else:
            raise IllegalEventTransition(f"{event} {st} 상태에서 소비 불가")
        return self._consumer_record(event, subscriber, ACT_CONSUMED, note or "consumed", now,
                                     commit=commit)

    def archive_event(self, event: str, now: str = "", *, commit: bool = False) -> EventLifecycleRecord:
        return self._transition(event, E_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ snapshot_events ══════════════
    def snapshot_events(self, scope: str = "ALL", now: str = "",
                      *, commit: bool = False) -> SnapshotRecord:
        """이벤트 상태·유형 분포 스냅샷(결정적). **관찰·기록만.**"""
        state_dist: dict = {}
        type_dist: dict = {}
        for eid in ledger.event_ids():
            st = self.current_state(eid)
            state_dist[st] = state_dist.get(st, 0) + 1
            et = self._event_meta(eid)["event_type"]
            type_dist[et] = type_dist.get(et, 0) + 1
        sid = _snapshot_id(scope, now)
        rec = SnapshotRecord(snapshot_id=sid, scope=scope, event_count=len(ledger.event_ids()),
                             state_distribution=dict(sorted(state_dist.items())),
                             type_distribution=dict(sorted(type_dist.items())), taken_at=now,
                             input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope: str = "ALL", now: str = "",
                      *, commit: bool = False) -> EventReportRecord:
        """이벤트 버스 리포트(발행·소비·아카이브·구독·라우팅·유형 분포). **is_binding=False, 관찰만.**"""
        eids = ledger.event_ids()
        pub = con = arc = 0
        type_dist: dict = {}
        for eid in eids:
            st = self.current_state(eid)
            if st in (E_PUBLISHED, E_ROUTED, E_CONSUMED, E_ARCHIVED):
                pub += 1
            if st in (E_CONSUMED, E_ARCHIVED):
                con += 1
            if st == E_ARCHIVED:
                arc += 1
            et = self._event_meta(eid)["event_type"]
            type_dist[et] = type_dist.get(et, 0) + 1
        rid = _report_id(scope, now)
        rec = EventReportRecord(
            report_id=rid, scope=scope, event_count=len(eids), published_count=pub,
            consumed_count=con, archived_count=arc,
            subscriber_count=len(ledger.read_subscribers()), route_count=len(ledger.read_routes()),
            type_distribution=dict(sorted(type_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_REPORT, rid, "", now, commit=commit)
        return EventReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_event_bus.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_events(self, event_type: str = "") -> list:
        if event_type:
            return ledger.type_events(event_type)
        return ledger.event_ids()

    def events_in_state(self, state: str) -> list:
        return sorted(e for e in ledger.event_ids() if self.current_state(e) == state)

    def event_meta(self, event: str) -> dict:
        return self._event_meta(event)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> EventBusSummary:
        return EventBusSummary(
            timestamp=now, type_count=len(ledger.read_types()),
            source_count=len(ledger.read_sources()), stream_count=len(ledger.read_streams()),
            event_lifecycle_count=len(ledger.read_events()),
            subscriber_count=len(ledger.read_subscribers()),
            consumer_count=len(ledger.read_consumers()), route_count=len(ledger.read_routes()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()), lineage_count=len(ledger.read_lineage()))
