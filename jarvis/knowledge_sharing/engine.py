"""Knowledge Sharing Engine (P11.8) — 연구 에이전트 간 지식 공유. **공유·기록 전용.**

연구 지식·발견·교훈·재사용 아티팩트·구조화된 경험을 교환한다. **실행하지 않는다. 연구 결과를 바꾸지 않는다.
상위 원장을 수정하지 않는다. 배포를 승인하지 않는다.** execution/broker/portfolio/risk/permission/deployment/
live import·호출 없음. SHARING ≠ EXECUTION · TRANSFER ≠ DEPLOYMENT · REUSE ≠ APPROVAL. 중복 불변·순환·dangling·
잘못된 계보 거부. 결정적 ID·재현. 불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.knowledge_sharing import ledger
from jarvis.knowledge_sharing.models import (
    ART_ENTRY,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_TOPIC,
    DIRECTIONAL_LINKS,
    GENESIS,
    K_ARCHIVED,
    K_CONSUMED,
    K_CREATED,
    K_PUBLISHED,
    K_REUSED,
    K_SHARED,
    KNOWLEDGE_TYPES,
    LINK_ENTRY_RELATED,
    LINK_ENTRY_TOPIC,
    LINK_TOPIC_PARENT,
    LINK_TOPIC_RELATED,
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
    ancestors,
    artifact_id as _artifact_id,
    can_transition,
    consumer_id as _consumer_id,
    content_hash,
    detect_cycle,
    entry_event_id as _entry_event_id,
    entry_id as _entry_id,
    input_digest,
    lineage_id as _lineage_id,
    link_id as _link_id,
    rating_id as _rating_id,
    registry_id as _registry_id,
    report_id as _report_id,
    reuse_score,
    snapshot_id as _snapshot_id,
    source_id as _source_id,
    topic_id as _topic_id,
    transfer_id as _transfer_id,
)

_DISCLAIMER = ("Knowledge Sharing 데이터 — SHARING ≠ EXECUTION · TRANSFER ≠ DEPLOYMENT · REUSE ≠ APPROVAL. "
               "에이전트 간 지식 공유 전용 — 실행/연구결과변경/상위원장수정/배포승인/승격 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class KnowledgeSharingEngine:
    """에이전트 간 지식 공유 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/승인/상위수정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str, *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ Registry ══════════════
    def register_registry(self, name: str, mandate: str = "", now: str = "",
                        *, commit: bool = False) -> RegistryRecord:
        """지식 레지스트리 등록(불변). **등록만.**"""
        rid = _registry_id(name)
        existing = ledger.get_registry(rid)
        if existing is not None:
            return RegistryRecord(**{k: v for k, v in existing.items()
                                     if k in RegistryRecord.__dataclass_fields__})
        rec = RegistryRecord(registry_id=rid, name=name, mandate=mandate, created_at=now,
                             input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.registry_exists(rid):
            head = ledger.registry_head()
            ledger.append_registry(_seal(rec, head["record_hash"] if head else GENESIS))
        return RegistryRecord(**rec)

    def _require_registry(self, rid: str) -> dict:
        rec = ledger.get_registry(rid)
        if rec is None:
            raise UnknownRegistryError(f"미등록 레지스트리 {rid}")
        return rec

    # ══════════════ register_topic (topic graph) ══════════════
    def register_topic(self, registry: str, name: str, description: str = "", parent_topic: str = "",
                     now: str = "", *, commit: bool = False) -> TopicRecord:
        """지식 토픽 등록(불변). parent_topic 은 토픽 그래프 간선(순환 거부)."""
        self._require_registry(registry)
        tid = _topic_id(name)
        existing = ledger.get_topic(tid)
        if existing is not None:
            if existing.get("parent_topic") != parent_topic:
                raise ImmutableTopicError(f"{tid} 토픽 불변 — 변경 불가")
            return TopicRecord(**{k: v for k, v in existing.items()
                                  if k in TopicRecord.__dataclass_fields__})
        if parent_topic:
            if not ledger.topic_exists(parent_topic):
                raise DanglingReferenceError(f"미등록 부모 토픽 {parent_topic}")
            edges = self._topic_parent_edges() + [(tid, parent_topic)]
            if detect_cycle(edges):
                raise CircularReferenceError(f"토픽 순환 — 거부 {tid}->{parent_topic}")
        rec = TopicRecord(topic_id=tid, registry_id=registry, name=name, description=description,
                          parent_topic=parent_topic, created_at=now, input_hash=input_digest(name),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.topic_exists(tid):
            head = ledger.topics_head()
            ledger.append_topic(_seal(rec, head["record_hash"] if head else GENESIS))
        if parent_topic:
            self._link(LINK_TOPIC_PARENT, tid, parent_topic, "child_of", now, commit=commit)
        self._artifact(ART_TOPIC, tid, "", now, commit=commit)
        return TopicRecord(**rec)

    def _topic_parent_edges(self) -> list:
        return [(t.get("topic_id"), t.get("parent_topic")) for t in ledger.read_topics()
                if t.get("parent_topic")]

    def _require_topic(self, tid: str) -> dict:
        rec = ledger.get_topic(tid)
        if rec is None:
            raise UnknownTopicError(f"미등록 토픽 {tid}")
        return rec

    # ══════════════ register_source (READ ONLY 상위 참조) ══════════════
    def register_source(self, layer: str, ref: str, description: str = "", now: str = "",
                      *, commit: bool = False, verify_ref: bool = False) -> SourceRecord:
        """지식 소스(상위 계층 READ ONLY 참조) 등록(불변). **참조만 — 상위 무수정.**"""
        if verify_ref and not ledger.source_ref_exists(layer, ref):
            raise DanglingReferenceError(f"상위 소스 없음 {layer}:{ref}")
        sid = _source_id(layer, ref)
        existing = ledger.get_source(sid)
        if existing is not None:
            return SourceRecord(**{k: v for k, v in existing.items()
                                   if k in SourceRecord.__dataclass_fields__})
        rec = SourceRecord(source_id=sid, layer=layer, ref=ref, description=description,
                           read_only=True, created_at=now, input_hash=input_digest(layer, ref),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.source_exists(sid):
            head = ledger.sources_head()
            ledger.append_source(_seal(rec, head["record_hash"] if head else GENESIS))
        return SourceRecord(**rec)

    # ══════════════ publish_knowledge (CREATED→PUBLISHED) ══════════════
    def _entry_event(self, entry: str, topic: str, title: str, ktype: str, content: str, author: str,
                   source: str, frm: str, to: str, note: str, now: str, *, commit: bool) -> EntryEventRecord:
        seq = len(ledger.entry_events(entry))
        eeid = _entry_event_id(entry, to, seq)
        rec = EntryEventRecord(
            entry_event_id=eeid, entry_id=entry, topic_id=topic, title=title, knowledge_type=ktype,
            content=content, author=author, source_id=source, from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(entry, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.entry_event_exists(eeid):
            head = ledger.entries_head()
            ledger.append_entry_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return EntryEventRecord(**rec)

    def current_entry(self, entry: str) -> dict | None:
        evs = ledger.entry_events(entry)
        return evs[-1] if evs else None

    def entry_state(self, entry: str) -> str | None:
        cur = self.current_entry(entry)
        return cur.get("to_state") if cur else None

    def entry_meta(self, entry: str) -> dict:
        evs = ledger.entry_events(entry)
        if not evs:
            raise UnknownEntryError(f"미등록 엔트리 {entry}")
        g = evs[0]
        return {"entry_id": entry, "topic_id": g.get("topic_id"), "title": g.get("title"),
                "knowledge_type": g.get("knowledge_type"), "author": g.get("author"),
                "state": evs[-1].get("to_state")}

    def publish_knowledge(self, topic: str, title: str, knowledge_type: str, content: str,
                        author: str, source: str = "", parent_entry: str = "", now: str = "",
                        *, commit: bool = False) -> EntryEventRecord:
        """지식 엔트리 발행(CREATED→PUBLISHED). 중복 불변·계보(parent) 검증. **발행·기록만.**"""
        self._require_topic(topic)
        if knowledge_type not in KNOWLEDGE_TYPES:
            raise InvalidKnowledgeType(f"미등록 지식 유형 {knowledge_type}")
        entry = _entry_id(topic, title, author)
        evs = ledger.entry_events(entry)
        if evs:
            g = evs[0]
            if g.get("content") != content or g.get("knowledge_type") != knowledge_type:
                raise ImmutableEntryError(f"{entry} 지식 엔트리 불변 — 중복 변경 거부")
            return EntryEventRecord(**{k: v for k, v in g.items()
                                       if k in EntryEventRecord.__dataclass_fields__})
        if parent_entry:
            if self.current_entry(parent_entry) is None:
                raise DanglingReferenceError(f"미등록 부모 엔트리 {parent_entry}")
            edges = self._lineage_edges() + [(entry, parent_entry)]
            if detect_cycle(edges):
                raise InvalidLineageError(f"계보 순환 — 거부 {entry}->{parent_entry}")
        self._entry_event(entry, topic, title, knowledge_type, content, author, source, GENESIS,
                        K_CREATED, "created", now, commit=commit)
        pub = self._entry_event(entry, topic, title, knowledge_type, content, author, source,
                              K_CREATED, K_PUBLISHED, "published", now, commit=commit)
        # 계보 기록
        if parent_entry:
            self._record_lineage(entry, parent_entry, now, commit=commit)
        parent_art = _artifact_id(ART_TOPIC, topic)
        self._artifact(ART_ENTRY, entry, parent_art if ledger.artifact_exists(parent_art) else "",
                       now, commit=commit)
        return pub

    def _lineage_edges(self) -> list:
        return [(r.get("child_entry"), r.get("parent_entry")) for r in ledger.read_lineage()]

    def _record_lineage(self, child: str, parent: str, now: str, *, commit: bool) -> LineageRecord:
        lid = _lineage_id(child, parent)
        rec = LineageRecord(lineage_id=lid, child_entry=child, parent_entry=parent, created_at=now,
                            input_hash=input_digest(child, parent), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage(_seal(rec, head["record_hash"] if head else GENESIS))
        return LineageRecord(**rec)

    def _require_entry(self, entry: str) -> str:
        st = self.entry_state(entry)
        if st is None:
            raise UnknownEntryError(f"미등록 엔트리 {entry}")
        return st

    def _transition_entry(self, entry: str, to: str, note: str, now: str, *, commit: bool) -> EntryEventRecord:
        frm = self._require_entry(entry)
        if frm == to:
            cur = self.current_entry(entry)
            return EntryEventRecord(**{k: v for k, v in cur.items()
                                       if k in EntryEventRecord.__dataclass_fields__})
        if not can_transition(frm, to):
            raise IllegalEntryTransition(f"{entry} {frm}→{to} 불가")
        m = self.entry_meta(entry)
        cur = self.current_entry(entry)
        return self._entry_event(entry, m["topic_id"], m["title"], m["knowledge_type"],
                               cur.get("content"), m["author"], cur.get("source_id"), frm, to,
                               note, now, commit=commit)

    def archive_knowledge(self, entry: str, now: str = "", *, commit: bool = False) -> EntryEventRecord:
        return self._transition_entry(entry, K_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ link_knowledge ══════════════
    def _link(self, ltype: str, source: str, target: str, relation: str, now: str,
            *, commit: bool) -> LinkRecord:
        lid = _link_id(ltype, source, target)
        if ledger.link_exists(lid):
            for r in ledger.read_links():
                if r.get("link_id") == lid:
                    return LinkRecord(**{k: v for k, v in r.items()
                                         if k in LinkRecord.__dataclass_fields__})
        rec = LinkRecord(link_id=lid, link_type=ltype, source_id=source, target_id=target,
                         relation=relation, created_at=now,
                         input_hash=input_digest(ltype, source, target),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.link_exists(lid):
            head = ledger.links_head()
            ledger.append_link(_seal(rec, head["record_hash"] if head else GENESIS))
        return LinkRecord(**rec)

    def link_knowledge(self, link_type: str, source: str, target: str, relation: str = "relates",
                     now: str = "", *, commit: bool = False) -> LinkRecord:
        """지식 링크 추가. 자기참조·dangling·순환(방향성 링크) 거부. **연결만.**"""
        if link_type not in LINK_TYPES:
            raise InvalidLinkType(f"미등록 링크 종류 {link_type}")
        if source == target:
            raise SelfReferenceError(f"자기 참조 {source}")
        self._check_ref_exists(link_type, source, target)
        if link_type in DIRECTIONAL_LINKS:
            existing = [(l.get("source_id"), l.get("target_id"))
                        for l in ledger.links_of_type(link_type)]
            if detect_cycle(existing + [(source, target)]):
                raise CircularReferenceError(f"순환 참조 — 거부 {source}->{target}")
        return self._link(link_type, source, target, relation, now, commit=commit)

    def _check_ref_exists(self, ltype: str, source: str, target: str) -> None:
        def topic_ok(x):
            return ledger.topic_exists(x)

        def entry_ok(x):
            return self.current_entry(x) is not None
        if ltype in (LINK_TOPIC_PARENT, LINK_TOPIC_RELATED):
            if not topic_ok(source) or not topic_ok(target):
                raise DanglingReferenceError(f"미등록 토픽 참조 {source}/{target}")
        elif ltype == LINK_ENTRY_RELATED:
            if not entry_ok(source) or not entry_ok(target):
                raise DanglingReferenceError(f"미등록 엔트리 참조 {source}/{target}")
        elif ltype == LINK_ENTRY_TOPIC:
            if not entry_ok(source) or not topic_ok(target):
                raise DanglingReferenceError(f"미등록 참조 {source}/{target}")

    # ══════════════ share_with_agent (PUBLISHED→SHARED) ══════════════
    def share_with_agent(self, entry: str, from_agent: str, to_agent: str, note: str = "",
                       now: str = "", *, commit: bool = False) -> TransferRecord:
        """지식을 다른 에이전트에게 공유(전달 기록 + PUBLISHED→SHARED). **공유·기록만.**"""
        st = self._require_entry(entry)
        tid = _transfer_id(entry, from_agent, to_agent)
        existing = None
        for r in ledger.entry_transfers(entry):
            if r.get("transfer_id") == tid:
                existing = r
                break
        if existing is None:
            rec = TransferRecord(transfer_id=tid, entry_id=entry, from_agent=from_agent,
                                 to_agent=to_agent, note=note, created_at=now,
                                 input_hash=input_digest(entry, from_agent, to_agent),
                                 previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.transfer_exists(tid):
                head = ledger.transfers_head()
                ledger.append_transfer(_seal(rec, head["record_hash"] if head else GENESIS))
            out = TransferRecord(**rec)
        else:
            out = TransferRecord(**{k: v for k, v in existing.items()
                                    if k in TransferRecord.__dataclass_fields__})
        if st == K_PUBLISHED:
            self._transition_entry(entry, K_SHARED, "shared", now, commit=commit)
        return out

    # ══════════════ record_consumption (SHARED→CONSUMED) ══════════════
    def record_consumption(self, entry: str, agent: str, reused: bool = False, note: str = "",
                         now: str = "", *, commit: bool = False) -> ConsumerRecord:
        """지식 소비 기록(+ SHARED→CONSUMED). **소비 기록만 — 결과 무변경.**"""
        st = self._require_entry(entry)
        cid = _consumer_id(entry, agent)
        existing = None
        for r in ledger.entry_consumers(entry):
            if r.get("consumer_id") == cid:
                existing = r
                break
        if existing is None:
            rec = ConsumerRecord(consumer_id=cid, entry_id=entry, agent=agent, reused=bool(reused),
                                 note=note, created_at=now, input_hash=input_digest(entry, agent),
                                 previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.consumer_exists(cid):
                head = ledger.consumers_head()
                ledger.append_consumer(_seal(rec, head["record_hash"] if head else GENESIS))
            out = ConsumerRecord(**rec)
        else:
            out = ConsumerRecord(**{k: v for k, v in existing.items()
                                    if k in ConsumerRecord.__dataclass_fields__})
        if st == K_SHARED:
            self._transition_entry(entry, K_CONSUMED, "consumed", now, commit=commit)
        return out

    # ══════════════ record_feedback (Rating) ══════════════
    def record_feedback(self, entry: str, agent: str, score: int, comment: str = "", now: str = "",
                      *, commit: bool = False) -> RatingRecord:
        """지식 평가(1~5) 기록(불변). **피드백 기록만.**"""
        self._require_entry(entry)
        if int(score) < 1 or int(score) > 5:
            raise InvalidRating(f"평가 범위 위반 {score}")
        rid = _rating_id(entry, agent)
        existing = ledger.get_rating(rid)
        if existing is not None:
            if existing.get("score") != int(score):
                raise ImmutableRatingError(f"{rid} 평가 불변 — 변경 불가")
            return RatingRecord(**{k: v for k, v in existing.items()
                                   if k in RatingRecord.__dataclass_fields__})
        rec = RatingRecord(rating_id=rid, entry_id=entry, agent=agent, score=int(score),
                           comment=comment, created_at=now, input_hash=input_digest(entry, agent),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.rating_exists(rid):
            head = ledger.ratings_head()
            ledger.append_rating(_seal(rec, head["record_hash"] if head else GENESIS))
        return RatingRecord(**rec)

    # ══════════════ calculate_reuse_score (CONSUMED→REUSED) ══════════════
    def calculate_reuse_score(self, entry: str, now: str = "", *, commit: bool = False) -> dict:
        """재사용 점수 계산(결정적). 재사용 시 CONSUMED→REUSED. **REUSE ≠ APPROVAL.**"""
        st = self._require_entry(entry)
        consumers = ledger.entry_consumers(entry)
        transfers = ledger.entry_transfers(entry)
        ratings = ledger.entry_ratings(entry)
        derived = sum(1 for r in ledger.read_lineage() if r.get("parent_entry") == entry)
        avg = (sum(int(r.get("score", 0)) for r in ratings) / len(ratings)) if ratings else 0.0
        reused_flag = any(c.get("reused") for c in consumers) or derived > 0
        score = reuse_score(len(consumers), len(transfers), avg, derived)
        if commit and reused_flag and st == K_CONSUMED:
            self._transition_entry(entry, K_REUSED, "reused", now, commit=commit)
        return {"entry_id": entry, "reuse_score": score, "consumers": len(consumers),
                "transfers": len(transfers), "ratings_avg": round(avg, 8), "derived": derived,
                "reused": reused_flag}

    # ══════════════ snapshot_knowledge (deterministic) ══════════════
    def snapshot_knowledge(self, scope: str = "GLOBAL", now: str = "",
                         *, commit: bool = False) -> SnapshotRecord:
        """지식 상태 스냅샷(결정적: 동일 상태 → 동일 content_digest). **관측 스냅샷.**"""
        entries = ledger.entry_ids()
        state_dist: dict = {}
        type_dist: dict = {}
        for e in entries:
            m = self.entry_meta(e)
            state_dist[m["state"]] = state_dist.get(m["state"], 0) + 1
            type_dist[m["knowledge_type"]] = type_dist.get(m["knowledge_type"], 0) + 1
        digest_input = sorted((e, self.entry_meta(e)["state"]) for e in entries)
        content_digest = input_digest("snapshot", digest_input)
        sid = _snapshot_id(scope, now)
        existing = ledger.get_snapshot(sid)
        if existing is not None:
            return SnapshotRecord(**{k: v for k, v in existing.items()
                                     if k in SnapshotRecord.__dataclass_fields__})
        rec = SnapshotRecord(
            snapshot_id=sid, scope=scope, entry_count=len(entries),
            topic_count=len(ledger.read_topics()), transfer_count=len(ledger.read_transfers()),
            consumer_count=len(ledger.read_consumers()),
            state_distribution=dict(sorted(state_dist.items())),
            type_distribution=dict(sorted(type_dist.items())), content_digest=content_digest,
            taken_at=now, input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope: str = "GLOBAL", now: str = "",
                      *, commit: bool = False) -> KnowledgeReportRecord:
        """지식 공유 리포트(엔트리·전달·소비·평가·평균 재사용). **관측 리포트 — is_binding=False.**"""
        entries = ledger.entry_ids()
        type_dist: dict = {}
        scores: list = []
        for e in entries:
            type_dist[self.entry_meta(e)["knowledge_type"]] = \
                type_dist.get(self.entry_meta(e)["knowledge_type"], 0) + 1
            scores.append(self.calculate_reuse_score(e)["reuse_score"])
        avg_reuse = round(sum(scores) / len(scores), 8) if scores else 0.0
        rid = _report_id(scope, now)
        rec = KnowledgeReportRecord(
            report_id=rid, scope=scope, entry_count=len(entries),
            topic_count=len(ledger.read_topics()), transfer_count=len(ledger.read_transfers()),
            consumer_count=len(ledger.read_consumers()), rating_count=len(ledger.read_ratings()),
            avg_reuse_score=avg_reuse, type_distribution=dict(sorted(type_dist.items())),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_REPORT, rid, "", now, commit=commit)
        return KnowledgeReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.knowledge_sharing.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def trace_lineage(self, entry: str) -> list:
        return ancestors(self._lineage_edges(), entry)

    def list_entries(self, topic: str = "") -> list:
        eids = ledger.entry_ids()
        if topic:
            eids = [e for e in eids if self.entry_meta(e)["topic_id"] == topic]
        return sorted(eids)

    def list_topics(self) -> list:
        return sorted(t.get("topic_id") for t in ledger.read_topics())

    def topic_children(self, topic: str) -> list:
        return sorted(t.get("topic_id") for t in ledger.read_topics()
                      if t.get("parent_topic") == topic)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> SharingSummary:
        return SharingSummary(
            timestamp=now, registry_count=len(ledger.read_registry()),
            topic_count=len(ledger.read_topics()),
            entry_event_count=len(ledger.read_entry_events()),
            source_count=len(ledger.read_sources()), link_count=len(ledger.read_links()),
            transfer_count=len(ledger.read_transfers()), consumer_count=len(ledger.read_consumers()),
            rating_count=len(ledger.read_ratings()), snapshot_count=len(ledger.read_snapshots()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()),
            lineage_count=len(ledger.read_lineage()))
