"""Research Memory Engine (P10.14) — 장기 연구 기억 보존·검색·연결. **보존·검색·기록 전용.**

P10.5/7/8/11/12/13 을 READ ONLY 로 소비해 기억·교훈·패턴·연결·검색·클러스터·리포트를 남긴다.
**연구 실행·trading signal 생성·strategy 선택·model 수정·deploy·자동 학습 갱신·자동 의사결정 없음.**
execution/broker/portfolio execution/risk execution/permission/capital allocation import·호출 없음.
MEMORY ≠ DECISION · RECALL ≠ APPROVAL · SIMILARITY ≠ VALIDATION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_memory import ledger
from jarvis.research_memory.models import (
    ARCHIVED,
    GENESIS,
    ART_CLUSTER,
    ART_CONNECTION,
    ART_LESSON,
    ART_MEMORY,
    ART_PATTERN,
    ART_REPORT,
    ART_RETRIEVAL,
    ART_SOURCE,
    CONNECTED,
    DIRECTED_RELATIONS,
    RELATIONS,
    RETRIEVED,
    STORED,
    UNDIRECTED_RELATIONS,
    IllegalTransition,
    ImmutableLessonError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidConnection,
    MemoryArtifact,
    MemoryCluster,
    MemoryConnection,
    MemoryEvent,
    MemoryPattern,
    MemoryReport,
    MemorySummary,
    ResearchLesson,
    RetrievalRecord,
    UnknownMemory,
    artifact_id as _artifact_id,
    can_transition_memory,
    cluster_id as _cluster_id,
    connected_components,
    connection_id as _connection_id,
    content_hash,
    detect_cycle,
    input_digest,
    lesson_id as _lesson_id,
    memory_confidence,
    memory_event_id,
    memory_id as _memory_id,
    memory_score,
    pattern_id as _pattern_id,
    payload_hash,
    report_id as _report_id,
    retrieval_id as _retrieval_id,
    similarity,
)

_DISCLAIMER = ("연구 기억 — MEMORY ≠ DECISION · RECALL ≠ APPROVAL · SIMILARITY ≠ VALIDATION. "
               "실행/선택/배포/모델수정 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchMemoryEngine:
    """연구 기억 엔진. 불변·append-only·결정적. 실행/거래/배포/선택/모델수정/학습갱신 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = MemoryArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Memory Registry (이벤트 소싱, 불변) ──
    def memory_state(self, memory_id: str) -> str:
        evs = ledger.memory_events_for(memory_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _memory_meta(self, memory_id: str) -> dict | None:
        evs = ledger.memory_events_for(memory_id)
        return evs[0] if evs else None

    def _emit_memory_event(self, meta: dict, frm: str, to: str, now: str,
                           *, commit: bool) -> dict:
        if not can_transition_memory(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(memory)")
        mid = meta["memory_id"]
        eid = memory_event_id(mid, frm, to)
        rec = MemoryEvent(
            event_id=eid, memory_id=mid, mem_type=meta["mem_type"],
            source_reference=meta["source_reference"], content_hash=meta["content_hash"],
            searchable_text=meta["searchable_text"], importance=meta["importance"],
            confidence=meta["confidence"], embedding_dim=meta["embedding_dim"],
            embedding_tag=meta["embedding_tag"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(mid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.memory_event_exists(eid):
            head = ledger.memories_head()
            ledger.append_memory_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def store_memory(self, mem_type: str, source_reference: str, content: str,
                     searchable_text: str = "", importance: float = 0.0, confidence: float = 0.0,
                     embedding_dim: int = 0, embedding_tag: str = "", now: str = "",
                     *, commit: bool = False) -> MemoryEvent:
        """연구 기억을 불변 저장(STORED). **자동 학습 갱신 없음 — 기록만.**"""
        ch = payload_hash(content)
        mid = _memory_id(mem_type, source_reference, ch)
        existing = ledger.memory_events_for(mid)
        if existing:
            first = existing[0]
            if first.get("content_hash") != ch:
                raise ImmutableMemoryError(f"{mid} 기억 불변 — 변경 불가")
            return MemoryEvent(**existing[-1])
        meta = {"memory_id": mid, "mem_type": mem_type, "source_reference": source_reference,
                "content_hash": ch, "searchable_text": searchable_text or content,
                "importance": round(float(importance), 8),
                "confidence": round(float(confidence), 8), "embedding_dim": int(embedding_dim),
                "embedding_tag": embedding_tag}
        rec = self._emit_memory_event(meta, "", STORED, now, commit=commit)
        self._record_artifact(ART_SOURCE, source_reference or f"mem:{mid}", "", now,
                              commit=commit)
        self._record_artifact(ART_MEMORY, mid,
                              _artifact_id(ART_SOURCE, source_reference or f"mem:{mid}"), now,
                              commit=commit)
        return MemoryEvent(**rec)

    def transition_memory(self, memory_id: str, to: str, now: str = "", *,
                          commit: bool = False) -> dict:
        meta = self._memory_meta(memory_id)
        if meta is None:
            raise UnknownMemory(f"미존재 기억 {memory_id}")
        return self._emit_memory_event(meta, self.memory_state(memory_id), to, now,
                                       commit=commit)

    def _safe_advance_memory(self, memory_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._memory_meta(memory_id)
        if meta is None:
            return
        cur = self.memory_state(memory_id)
        if cur != to and can_transition_memory(cur, to):
            self._emit_memory_event(meta, cur, to, now, commit=commit)

    def _searchable(self, memory_id: str) -> str:
        meta = self._memory_meta(memory_id)
        if not meta:
            return ""
        return f"{meta.get('mem_type', '')} {meta.get('source_reference', '')} " \
               f"{meta.get('searchable_text', '')}"

    # ── Research Lesson (불변) ──
    def record_lesson(self, observation: str, cause: str = "", impact: str = "",
                      evidence_refs: list | None = None, confidence: float = 0.0, now: str = "",
                      *, commit: bool = False) -> ResearchLesson:
        lid = _lesson_id(observation, cause)
        for l in ledger.read_lessons():
            if l.get("lesson_id") == lid:
                if l.get("impact") != impact:
                    raise ImmutableLessonError(f"{lid} 교훈 불변 — 변경 불가")
                return ResearchLesson(**{k: v for k, v in l.items()
                                         if k in ResearchLesson.__dataclass_fields__})
        rec = ResearchLesson(
            lesson_id=lid, observation=observation, cause=cause, impact=impact,
            evidence_refs=list(evidence_refs or []), confidence=round(float(confidence), 8),
            created_at=now, input_hash=input_digest(observation, cause),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lesson_exists(lid):
            head = ledger.lessons_head()
            ledger.append_lesson(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_LESSON, lid, "", now, commit=commit)
        return ResearchLesson(**rec)

    def compare_lessons(self, lesson_a: str, lesson_b: str) -> dict:
        """두 교훈의 서술적 유사도(자동 결론 없음)."""
        la = ledger.get_lesson(lesson_a)
        lb = ledger.get_lesson(lesson_b)
        if la is None or lb is None:
            raise ImmutableLessonError("미존재 교훈 참조")
        text_a = f"{la.get('observation', '')} {la.get('cause', '')} {la.get('impact', '')}"
        text_b = f"{lb.get('observation', '')} {lb.get('cause', '')} {lb.get('impact', '')}"
        return {"lesson_a": lesson_a, "lesson_b": lesson_b,
                "similarity": similarity(text_a, text_b),
                "note": "서술적 비교만 — SIMILARITY ≠ VALIDATION"}

    # ── Memory Pattern (불변) ──
    def record_pattern(self, name: str, description: str = "", usage_refs: list | None = None,
                       confidence: float = 0.0, now: str = "",
                       *, commit: bool = False) -> MemoryPattern:
        pid = _pattern_id(name)
        for p in ledger.read_patterns():
            if p.get("pattern_id") == pid:
                if p.get("description") != description:
                    raise ImmutablePatternError(f"{pid} 패턴 불변 — 변경 불가")
                return MemoryPattern(**{k: v for k, v in p.items()
                                        if k in MemoryPattern.__dataclass_fields__})
        rec = MemoryPattern(
            pattern_id=pid, name=name, description=description,
            usage_refs=list(usage_refs or []), confidence=round(float(confidence), 8),
            created_at=now, input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PATTERN, pid, "", now, commit=commit)
        return MemoryPattern(**rec)

    # ── Memory Connection (그래프 검증·순환 차단) ──
    def connect_memory(self, from_memory: str, relation: str, to_memory: str,
                       weight: float = 0.0, now: str = "",
                       *, commit: bool = False) -> MemoryConnection:
        if relation not in RELATIONS:
            raise InvalidConnection(f"미등록 관계 {relation}")
        if not ledger.memory_exists(from_memory):
            raise UnknownMemory(f"미등록 from 기억 {from_memory}")
        if not ledger.memory_exists(to_memory):
            raise UnknownMemory(f"미등록 to 기억 {to_memory}")
        cid = _connection_id(from_memory, relation, to_memory)
        # 방향성 관계 순환 차단(DERIVED_FROM 등).
        if relation in DIRECTED_RELATIONS and not ledger.connection_exists(cid):
            directed = [(c.get("from_memory"), c.get("to_memory"))
                        for c in ledger.read_connections()
                        if c.get("relation") in DIRECTED_RELATIONS]
            cyc = detect_cycle(directed + [(from_memory, to_memory)])
            if cyc:
                raise InvalidConnection("기억 순환 차단: " + "->".join(cyc))
        rec = MemoryConnection(
            connection_id=cid, from_memory=from_memory, relation=relation, to_memory=to_memory,
            weight=round(float(weight), 8), created_at=now,
            input_hash=input_digest(from_memory, relation, to_memory),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.connection_exists(cid):
            head = ledger.connections_head()
            ledger.append_connection(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_CONNECTION, cid, _artifact_id(ART_MEMORY, from_memory), now,
                              commit=commit)
        self._safe_advance_memory(from_memory, CONNECTED, now, commit=commit)
        self._safe_advance_memory(to_memory, CONNECTED, now, commit=commit)
        return MemoryConnection(**rec)

    def connection_cycle(self) -> list:
        directed = [(c.get("from_memory"), c.get("to_memory")) for c in ledger.read_connections()
                    if c.get("relation") in DIRECTED_RELATIONS]
        return detect_cycle(directed)

    # ── Retrieval (검색 — 결정적) ──
    def search_memory(self, query: str, threshold: float = 0.1, top_k: int = 5, now: str = "",
                      *, commit: bool = False) -> RetrievalRecord:
        """쿼리와 기억의 토큰 유사도로 검색(결정적). **RECALL ≠ APPROVAL — 기록·조회만.**"""
        scored: list = []
        for m in ledger.distinct_memories():
            mid = m.get("memory_id")
            sim = similarity(query, self._searchable(mid))
            if sim >= threshold:
                scored.append((mid, sim))
        scored.sort(key=lambda x: (-x[1], x[0]))
        scored = scored[:top_k]
        matched = [mid for mid, _ in scored]
        scores = {mid: sim for mid, sim in scored}
        top = scored[0][1] if scored else 0.0
        rid = _retrieval_id(query, matched)
        rec = RetrievalRecord(
            retrieval_id=rid, query=query, matched_memories=matched, similarity_scores=scores,
            top_similarity=round(top, 8), created_at=now, input_hash=input_digest(query),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.retrieval_exists(rid):
            head = ledger.retrievals_head()
            ledger.append_retrieval(_seal(rec, head["record_hash"] if head else GENESIS))
        for mid in matched:
            self._safe_advance_memory(mid, RETRIEVED, now, commit=commit)
        return RetrievalRecord(**rec)

    # ── Clustering (대칭 연결 기반 연결요소) ──
    def cluster_memories(self, now: str = "", *, commit: bool = False) -> list:
        """대칭 관계(SIMILAR_TO/SUPPORTS/REPEATS)로 기억을 클러스터링. 기록만."""
        nodes = [m.get("memory_id") for m in ledger.distinct_memories()]
        edges = [(c.get("from_memory"), c.get("to_memory")) for c in ledger.read_connections()
                 if c.get("relation") in UNDIRECTED_RELATIONS]
        comps = connected_components(nodes, edges)
        out: list = []
        for comp in comps:
            if len(comp) < 2:
                continue
            sig = "|".join(comp)
            n = len(comp)
            internal = sum(1 for a, b in edges if a in comp and b in comp)
            cohesion = round(internal / (n * (n - 1) / 2), 8) if n > 1 else 0.0
            cid = _cluster_id(sig)
            rec = MemoryCluster(
                cluster_id=cid, name=f"cluster_{comp[0]}", member_memories=comp, size=n,
                cohesion=cohesion, created_at=now, input_hash=input_digest(sig),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.cluster_exists(cid):
                head = ledger.clusters_head()
                ledger.append_cluster(_seal(rec, head["record_hash"] if head else GENESIS))
            self._record_artifact(ART_CLUSTER, cid, "", now, commit=commit)
            out.append(MemoryCluster(**rec))
        return out

    # ── Memory Analysis ──
    def analyze(self, metrics: dict) -> dict:
        """기억 지표 → MEMORY_CONFIDENCE. **자동 의사결정 없음.**"""
        return {"memory_score": memory_score(metrics),
                "memory_confidence": memory_confidence(metrics)}

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        seen: set = set()
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref and ref not in seen:
                seen.add(ref)
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Memory Report ──
    def generate_memory_report(self, scope: str = "GLOBAL", metrics: dict | None = None,
                               now: str = "", *, commit: bool = False) -> MemoryReport:
        m = dict(metrics or {})
        mems = ledger.distinct_memories()
        tdist: dict = {}
        sdist: dict = {}
        for mm in mems:
            tdist[mm.get("mem_type")] = tdist.get(mm.get("mem_type"), 0) + 1
            st = self.memory_state(mm.get("memory_id"))
            sdist[st] = sdist.get(st, 0) + 1
        conns = ledger.read_connections()
        rdist: dict = {}
        for c in conns:
            rdist[c.get("relation")] = rdist.get(c.get("relation"), 0) + 1
        rid = _report_id(scope)
        rec = MemoryReport(
            report_id=rid, scope=scope, memory_count=len(mems),
            memory_type_distribution=dict(sorted(tdist.items())),
            memory_state_distribution=dict(sorted(sdist.items())),
            lesson_count=len(ledger.read_lessons()), pattern_count=len(ledger.read_patterns()),
            connection_count=len(conns), relation_distribution=dict(sorted(rdist.items())),
            retrieval_count=len(ledger.read_retrievals()),
            cluster_count=len(ledger.read_clusters()), metrics=m, memory_score=memory_score(m),
            memory_confidence=memory_confidence(m), disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return MemoryReport(**rec)

    # ── Summary ──
    def summary(self, now: str = "") -> MemorySummary:
        mems = ledger.distinct_memories()
        tdist: dict = {}
        sdist: dict = {}
        for mm in mems:
            tdist[mm.get("mem_type")] = tdist.get(mm.get("mem_type"), 0) + 1
            st = self.memory_state(mm.get("memory_id"))
            sdist[st] = sdist.get(st, 0) + 1
        conns = ledger.read_connections()
        rdist: dict = {}
        for c in conns:
            rdist[c.get("relation")] = rdist.get(c.get("relation"), 0) + 1
        return MemorySummary(
            timestamp=now, memory_count=len(mems),
            memory_type_distribution=dict(sorted(tdist.items())),
            memory_state_distribution=dict(sorted(sdist.items())),
            lesson_count=len(ledger.read_lessons()), pattern_count=len(ledger.read_patterns()),
            connection_count=len(conns), relation_distribution=dict(sorted(rdist.items())),
            retrieval_count=len(ledger.read_retrievals()),
            cluster_count=len(ledger.read_clusters()), report_count=len(ledger.read_reports()))

