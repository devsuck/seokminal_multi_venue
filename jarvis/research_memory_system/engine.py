"""Research Memory System Engine (P11.12) — 장기 연구 기억. **기억 시스템 전용.**

연구 생태계의 역사적 지식을 저장·조직·검색·분석한다. **전략 실행·연구결과 수정·모델/거래 승인·배포·권한 변경·
상위 데이터 변경을 하지 않는다.** execution/broker/portfolio/risk/permission/deployment/live import·호출 없음.
기억은 삭제·덮어쓰기·재작성이 없고 새 정보는 새 기억 이벤트를 만든다. MEMORY ≠ EXECUTION · RECALL ≠ APPROVAL ·
PATTERN ≠ DEPLOYMENT. 결정적·불변·append-only·이벤트 소싱. 유사도는 결정적·설명가능·기록된다.
"""
from __future__ import annotations

from jarvis.research_memory_system import ledger
from jarvis.research_memory_system.models import (
    ART_MEMORY,
    ART_REPORT,
    ART_SNAPSHOT,
    GENESIS,
    M_ARCHIVED,
    M_CONNECTED,
    M_CREATED,
    M_INDEXED,
    M_RETRIEVABLE,
    MEMORY_TYPES,
    MODE_EXACT,
    MODE_HISTORICAL,
    MODE_LINEAGE,
    MODE_RELATED,
    MODE_SIMILARITY,
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
    ancestors,
    artifact_id as _artifact_id,
    association_id as _association_id,
    can_transition,
    content_hash,
    context_digest,
    context_id as _context_id,
    detect_cycle,
    experiment_memory_id as _experiment_memory_id,
    failure_memory_id as _failure_memory_id,
    input_digest,
    knowledge_id as _knowledge_id,
    memory_event_id as _memory_event_id,
    memory_id as _memory_id,
    neighbors,
    registry_id as _registry_id,
    report_id as _report_id,
    search_id as _search_id,
    similarity,
    snapshot_id as _snapshot_id,
    success_pattern_id as _success_pattern_id,
)

_DISCLAIMER = ("Research Memory System 데이터 — MEMORY ≠ EXECUTION · RECALL ≠ APPROVAL · PATTERN ≠ "
               "DEPLOYMENT. 장기 연구 기억 저장·검색·분석 전용 — 전략 실행·연구결과 수정·모델/거래 승인·배포·"
               "권한/설정 변경·상위 데이터 변경 없음. 기억은 삭제·덮어쓰기·재작성이 없다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchMemorySystemEngine:
    """장기 연구 기억 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/수정/승인/배포 권한 없음."""

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

    # ══════════════ 기억 생애주기(event-sourced) ══════════════
    def _memory_event(self, memory: str, memory_type: str, source_layer: str, source_id: str,
                    title: str, original_context: str, context_hash: str, evidence_ref: str,
                    frm: str, to: str, note: str, now: str, *, commit: bool) -> MemoryEventRecord:
        seq = len(ledger.memory_events(memory))
        eid = _memory_event_id(memory, to, seq)
        rec = MemoryEventRecord(
            memory_event_id=eid, memory_id=memory, memory_type=memory_type, source_layer=source_layer,
            source_id=source_id, title=title, original_context=original_context,
            context_hash=context_hash, evidence_ref=evidence_ref, from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(memory, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.memory_event_exists(eid):
            head = ledger.memories_head()
            ledger.append_memory_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return MemoryEventRecord(**rec)

    def _memory_meta(self, memory: str) -> dict:
        evs = ledger.memory_events(memory)
        if not evs:
            raise UnknownMemoryError(f"미등록 기억 {memory}")
        g = evs[0]
        return {"memory_id": memory, "memory_type": g.get("memory_type"),
                "source_layer": g.get("source_layer"), "source_id": g.get("source_id"),
                "title": g.get("title"), "original_context": g.get("original_context"),
                "context_hash": g.get("context_hash"), "evidence_ref": g.get("evidence_ref"),
                "state": evs[-1].get("to_state")}

    def current_state(self, memory: str) -> str | None:
        evs = ledger.memory_events(memory)
        return evs[-1].get("to_state") if evs else None

    def _require_memory(self, memory: str) -> str:
        st = self.current_state(memory)
        if st is None:
            raise UnknownMemoryError(f"미등록 기억 {memory}")
        return st

    def _transition(self, memory: str, to: str, note: str, now: str,
                  *, commit: bool) -> MemoryEventRecord:
        frm = self._require_memory(memory)
        if not can_transition(frm, to):
            raise IllegalMemoryTransition(f"{memory} {frm}→{to} 불가")
        m = self._memory_meta(memory)
        return self._memory_event(memory, m["memory_type"], m["source_layer"], m["source_id"],
                                 m["title"], m["original_context"], m["context_hash"],
                                 m["evidence_ref"], frm, to, note, now, commit=commit)

    # ══════════════ register_memory ══════════════
    def register_memory(self, source_layer: str, source_id: str, memory_type: str, title: str,
                      original_context: str = "", evidence_ref: str = "", now: str = "",
                      *, commit: bool = False, verify_ref: bool = False) -> MemoryEventRecord:
        """연구 기억 생성(genesis CREATED) + 불변 카탈로그. 소스 계층·id·맥락·증거·관계 이력 보존. **기록만.**"""
        if memory_type not in MEMORY_TYPES:
            raise InvalidMemoryType(f"미등록 기억 유형 {memory_type}")
        if source_layer and not source_id:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} source_id 없음")
        if verify_ref and source_layer and evidence_ref and not ledger.source_ref_exists(
                source_layer, evidence_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{evidence_ref}")
        mem = _memory_id(source_layer, source_id, memory_type, title)
        chash = context_digest(original_context)
        evs = ledger.memory_events(mem)
        if evs:
            g = evs[0]
            if g.get("context_hash") != chash:
                raise ImmutableMemoryError(f"{mem} 기억 불변 — 재작성 금지(새 정보는 새 기억)")
            return MemoryEventRecord(**{k: v for k, v in g.items()
                                        if k in MemoryEventRecord.__dataclass_fields__})
        ev = self._memory_event(mem, memory_type, source_layer, source_id, title, original_context,
                               chash, evidence_ref, GENESIS, M_CREATED, "created", now, commit=commit)
        # 불변 카탈로그(exact lookup)
        rid = _registry_id(mem)
        cat = RegistryRecord(registry_id=rid, memory_id=mem, memory_type=memory_type,
                             source_layer=source_layer, source_id=source_id, title=title,
                             created_at=now, input_hash=input_digest(mem),
                             previous_hash=GENESIS).to_dict()
        cat["record_hash"] = content_hash(cat)
        if commit and not ledger.registry_exists(rid):
            head = ledger.registry_head()
            ledger.append_registry(_seal(cat, head["record_hash"] if head else GENESIS))
        self._artifact(ART_MEMORY, mem, "", now, commit=commit)
        return ev

    def memory_meta(self, memory: str) -> dict:
        return self._memory_meta(memory)

    # ══════════════ store_research_context (→INDEXED) ══════════════
    def store_research_context(self, memory: str, context_key: str, context_data: str = "",
                            now: str = "", *, commit: bool = False) -> ContextRecord:
        """연구 맥락 저장(불변) + 기억 인덱싱(CREATED→INDEXED). 원본 맥락 보존. **기록만.**"""
        st = self._require_memory(memory)
        cid = _context_id(memory, context_key)
        existing = ledger.get_context(cid)
        if existing is not None:
            if existing.get("context_hash") != context_digest(context_data):
                raise ImmutableContextError(f"{cid} 맥락 불변 — 변경 불가")
            return ContextRecord(**{k: v for k, v in existing.items()
                                    if k in ContextRecord.__dataclass_fields__})
        rec = ContextRecord(context_id=cid, memory_id=memory, context_key=context_key,
                            context_data=context_data, context_hash=context_digest(context_data),
                            created_at=now, input_hash=input_digest(memory, context_key),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.context_exists(cid):
            head = ledger.contexts_head()
            ledger.append_context(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == M_CREATED:
            self._transition(memory, M_INDEXED, "indexed", now, commit=commit)
        return ContextRecord(**rec)

    # ══════════════ record_knowledge_entry (reusable knowledge discovery) ══════════════
    def record_knowledge_entry(self, memory: str, summary: str, tags=None, reusable: bool = True,
                            now: str = "", *, commit: bool = False) -> KnowledgeEntryRecord:
        """재사용 지식 엔트리 기록(불변). **발굴·기록만.**"""
        self._require_memory(memory)
        kid = _knowledge_id(memory, summary)
        existing = ledger.get_knowledge(kid)
        if existing is not None:
            if bool(existing.get("reusable")) != bool(reusable):
                raise ImmutableKnowledgeError(f"{kid} 지식 엔트리 불변 — 변경 불가")
            return KnowledgeEntryRecord(**{k: v for k, v in existing.items()
                                           if k in KnowledgeEntryRecord.__dataclass_fields__})
        rec = KnowledgeEntryRecord(knowledge_id=kid, memory_id=memory, summary=summary,
                                   tags=sorted(set(tags or [])), reusable=bool(reusable),
                                   created_at=now, input_hash=input_digest(memory, summary),
                                   previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.knowledge_exists(kid):
            head = ledger.knowledge_head()
            ledger.append_knowledge(_seal(rec, head["record_hash"] if head else GENESIS))
        return KnowledgeEntryRecord(**rec)

    # ══════════════ record_experiment_memory ══════════════
    def record_experiment_memory(self, memory: str, experiment_ref: str, outcome: str = "",
                              metrics: dict = None, source_layer: str = "", source_ref: str = "",
                              now: str = "", *, commit: bool = False,
                              verify_ref: bool = False) -> ExperimentMemoryRecord:
        """실험 기억 기록(불변). 소스 참조 READ ONLY. **기록만.**"""
        self._require_memory(memory)
        if source_layer and not source_ref:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} ref 없음")
        if verify_ref and source_layer and not ledger.source_ref_exists(source_layer, source_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{source_ref}")
        xid = _experiment_memory_id(memory, experiment_ref)
        existing = ledger.get_experiment(xid)
        if existing is not None:
            if existing.get("outcome") != outcome:
                raise ImmutableExperimentError(f"{xid} 실험 기억 불변 — 변경 불가")
            return ExperimentMemoryRecord(**{k: v for k, v in existing.items()
                                             if k in ExperimentMemoryRecord.__dataclass_fields__})
        rec = ExperimentMemoryRecord(
            experiment_memory_id=xid, memory_id=memory, experiment_ref=experiment_ref,
            outcome=outcome, metrics=dict(sorted((metrics or {}).items())), source_layer=source_layer,
            source_ref=source_ref, created_at=now, input_hash=input_digest(memory, experiment_ref),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experiment_exists(xid):
            head = ledger.experiments_head()
            ledger.append_experiment(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExperimentMemoryRecord(**rec)

    # ══════════════ record_failure_memory (failed approach tracking) ══════════════
    def record_failure_memory(self, memory: str, approach: str, reason: str = "", recurrence: int = 1,
                           source_layer: str = "", source_ref: str = "", now: str = "",
                           *, commit: bool = False, verify_ref: bool = False) -> FailureMemoryRecord:
        """실패 접근 기억 기록(불변). **추적·기록만.**"""
        self._require_memory(memory)
        if source_layer and not source_ref:
            raise MissingSourceError(f"소스 참조 누락: layer={source_layer} ref 없음")
        if verify_ref and source_layer and not ledger.source_ref_exists(source_layer, source_ref):
            raise DanglingReferenceError(f"상위 소스 없음 {source_layer}:{source_ref}")
        fid = _failure_memory_id(memory, approach)
        existing = ledger.get_failure(fid)
        if existing is not None:
            if existing.get("recurrence") != int(recurrence):
                raise ImmutableFailureError(f"{fid} 실패 기억 불변 — 변경 불가")
            return FailureMemoryRecord(**{k: v for k, v in existing.items()
                                          if k in FailureMemoryRecord.__dataclass_fields__})
        rec = FailureMemoryRecord(
            failure_memory_id=fid, memory_id=memory, approach=approach, reason=reason,
            recurrence=int(recurrence), source_layer=source_layer, source_ref=source_ref,
            created_at=now, input_hash=input_digest(memory, approach),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.failure_exists(fid):
            head = ledger.failures_head()
            ledger.append_failure(_seal(rec, head["record_hash"] if head else GENESIS))
        return FailureMemoryRecord(**rec)

    # ══════════════ record_success_pattern ══════════════
    def record_success_pattern(self, memory: str, pattern: str, conditions: str = "",
                            confidence: float = 0.0, now: str = "",
                            *, commit: bool = False) -> SuccessPatternRecord:
        """성공 패턴 기억 기록(불변). confidence 는 기록 값(승인 아님). **기록만.**"""
        self._require_memory(memory)
        pid = _success_pattern_id(memory, pattern)
        existing = ledger.get_pattern(pid)
        if existing is not None:
            if abs(float(existing.get("confidence", 0.0)) - float(confidence)) > 1e-9:
                raise ImmutablePatternError(f"{pid} 성공 패턴 불변 — 변경 불가")
            return SuccessPatternRecord(**{k: v for k, v in existing.items()
                                           if k in SuccessPatternRecord.__dataclass_fields__})
        rec = SuccessPatternRecord(success_pattern_id=pid, memory_id=memory, pattern=pattern,
                                   conditions=conditions, confidence=round(float(confidence), 8),
                                   created_at=now, input_hash=input_digest(memory, pattern),
                                   previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        return SuccessPatternRecord(**rec)

    # ══════════════ link_related_memories (→CONNECTED) ══════════════
    def _assoc_edges(self) -> list:
        return [(r.get("memory_a"), r.get("memory_b")) for r in ledger.read_associations()]

    def link_related_memories(self, memory_a: str, memory_b: str, relation: str = "RELATED",
                           note: str = "", now: str = "",
                           *, commit: bool = False) -> AssociationRecord:
        """기억 연관(불변). dangling·순환 거부. 연결 시 CONNECTED 전이. **기록만.**"""
        self._require_memory(memory_a)
        self._require_memory(memory_b)
        if memory_a == memory_b:
            raise CircularAssociationError(f"자기 연관 불가 {memory_a}")
        aid = _association_id(memory_a, memory_b, relation)
        existing = ledger.association_exists(aid)
        if not existing:
            edges = self._assoc_edges() + [(memory_a, memory_b)]
            if detect_cycle(edges):
                raise CircularAssociationError(f"순환 기억 연관 — 거부 {memory_a}->{memory_b}")
        rec = AssociationRecord(association_id=aid, memory_a=memory_a, memory_b=memory_b,
                                relation=relation, note=note, created_at=now,
                                input_hash=input_digest(memory_a, memory_b, relation),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not existing:
            head = ledger.associations_head()
            ledger.append_association(_seal(rec, head["record_hash"] if head else GENESIS))
        for m in (memory_a, memory_b):
            st = self.current_state(m)
            if st in (M_INDEXED, M_CONNECTED):
                self._transition(m, M_CONNECTED, "connected", now, commit=commit)
        return AssociationRecord(**rec)

    def mark_retrievable(self, memory: str, now: str = "", *, commit: bool = False) -> MemoryEventRecord:
        """검색 가능 상태로 표시(INDEXED/CONNECTED→RETRIEVABLE). **상태 기록만.**"""
        return self._transition(memory, M_RETRIEVABLE, "retrievable", now, commit=commit)

    def archive_memory(self, memory: str, now: str = "", *, commit: bool = False) -> MemoryEventRecord:
        return self._transition(memory, M_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ search_memory (deterministic, explainable, recorded) ══════════════
    def _memory_text(self, memory: str) -> str:
        m = self._memory_meta(memory)
        parts = [m["title"], m["original_context"]]
        for c in ledger.memory_contexts(memory):
            parts.append(c.get("context_data", ""))
        for k in ledger.read_knowledge():
            if k.get("memory_id") == memory:
                parts.append(k.get("summary", ""))
                parts.extend(k.get("tags", []))
        return " ".join(p for p in parts if p)

    def search_memory(self, query: str, mode: str = MODE_SIMILARITY, target: str = "",
                    threshold: float = 0.0, now: str = "", *, commit: bool = False) -> SearchRecord:
        """기억 검색(EXACT/SIMILARITY/LINEAGE/RELATED/HISTORICAL). 결정적·설명가능·기록. **조회·기록만.**"""
        if mode not in SEARCH_MODES:
            raise InvalidSearchMode(f"미등록 검색 모드 {mode}")
        results: list = []
        scores: dict = {}
        explanation: dict = {}
        if mode == MODE_EXACT:
            for cat in ledger.read_registry():
                if query and (query == cat.get("memory_id") or query == cat.get("title")):
                    results.append(cat.get("memory_id"))
                    scores[cat.get("memory_id")] = 1.0
                    explanation[cat.get("memory_id")] = "exact_match"
        elif mode == MODE_SIMILARITY:
            for mem in ledger.memory_ids():
                score, shared = similarity(query, self._memory_text(mem))
                if score > threshold or (threshold == 0.0 and score > 0.0):
                    results.append(mem)
                    scores[mem] = score
                    explanation[mem] = "shared:" + ",".join(shared) if shared else "no_shared"
            results = sorted(results, key=lambda m: (-scores[m], m))
        elif mode == MODE_LINEAGE:
            if target:
                for anc in ancestors(self._assoc_edges(), target):
                    results.append(anc)
                    scores[anc] = 1.0
                    explanation[anc] = "ancestor"
        elif mode == MODE_RELATED:
            if target:
                for nb in neighbors(self._assoc_edges(), target):
                    results.append(nb)
                    scores[nb] = 1.0
                    explanation[nb] = "neighbor"
        elif mode == MODE_HISTORICAL:
            mt = query
            for mem in ledger.type_memories(mt):
                results.append(mem)
                scores[mem] = 1.0
                explanation[mem] = "same_type:" + mt
        seq = len(ledger.read_searches())
        sid = _search_id(query, mode, seq)
        rec = SearchRecord(search_id=sid, query=query, mode=mode, result_ids=results,
                           scores=dict(sorted(scores.items())),
                           explanation=dict(sorted(explanation.items())), created_at=now,
                           input_hash=input_digest(query, mode, seq),
                           previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.search_exists(sid):
            head = ledger.searches_head()
            ledger.append_search(_seal(rec, head["record_hash"] if head else GENESIS))
        return SearchRecord(**rec)

    def trace_memory_lineage(self, memory: str) -> list:
        return ancestors(self._assoc_edges(), memory)

    def related_memories(self, memory: str) -> list:
        return neighbors(self._assoc_edges(), memory)

    def compare_memories(self, memory_a: str, memory_b: str) -> dict:
        """역사적 비교(결정적·설명가능). commit 없음."""
        self._require_memory(memory_a)
        self._require_memory(memory_b)
        score, shared = similarity(self._memory_text(memory_a), self._memory_text(memory_b))
        ma, mb = self._memory_meta(memory_a), self._memory_meta(memory_b)
        return {"memory_a": memory_a, "memory_b": memory_b, "similarity": score,
                "shared_tokens": shared, "same_type": ma["memory_type"] == mb["memory_type"],
                "type_a": ma["memory_type"], "type_b": mb["memory_type"]}

    # ══════════════ build_memory_snapshot ══════════════
    def build_memory_snapshot(self, scope: str = "ALL", now: str = "",
                           *, commit: bool = False) -> SnapshotRecord:
        """기억 상태·유형 분포 스냅샷(결정적). **관찰·기록만.**"""
        state_dist: dict = {}
        type_dist: dict = {}
        for mem in ledger.memory_ids():
            st = self.current_state(mem)
            state_dist[st] = state_dist.get(st, 0) + 1
            mt = self._memory_meta(mem)["memory_type"]
            type_dist[mt] = type_dist.get(mt, 0) + 1
        sid = _snapshot_id(scope, now)
        rec = SnapshotRecord(snapshot_id=sid, scope=scope, memory_count=len(ledger.memory_ids()),
                             state_distribution=dict(sorted(state_dist.items())),
                             type_distribution=dict(sorted(type_dist.items())), taken_at=now,
                             input_hash=input_digest(scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotRecord(**rec)

    # ══════════════ generate_memory_report ══════════════
    def generate_memory_report(self, scope: str = "ALL", now: str = "",
                            *, commit: bool = False) -> MemoryReportRecord:
        """기억 리포트(기억·지식·실험·실패·패턴·연관·검색가능·유형 분포). **is_binding=False, 관찰만.**"""
        mems = ledger.memory_ids()
        retr = sum(1 for m in mems if self.current_state(m) in (M_RETRIEVABLE, M_ARCHIVED))
        type_dist: dict = {}
        for m in mems:
            mt = self._memory_meta(m)["memory_type"]
            type_dist[mt] = type_dist.get(mt, 0) + 1
        rid = _report_id(scope, now)
        rec = MemoryReportRecord(
            report_id=rid, scope=scope, memory_count=len(mems),
            knowledge_count=len(ledger.read_knowledge()),
            experiment_count=len(ledger.read_experiments()),
            failure_count=len(ledger.read_failures()), pattern_count=len(ledger.read_patterns()),
            association_count=len(ledger.read_associations()), retrievable_count=retr,
            type_distribution=dict(sorted(type_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_REPORT, rid, "", now, commit=commit)
        return MemoryReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_memory_system.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_memories(self, memory_type: str = "") -> list:
        if memory_type:
            return ledger.type_memories(memory_type)
        return ledger.memory_ids()

    def memories_in_state(self, state: str) -> list:
        return sorted(m for m in ledger.memory_ids() if self.current_state(m) == state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> MemorySummary:
        return MemorySummary(
            timestamp=now, registry_count=len(ledger.read_registry()),
            memory_event_count=len(ledger.read_memory_events()),
            knowledge_count=len(ledger.read_knowledge()),
            context_count=len(ledger.read_contexts()),
            experiment_count=len(ledger.read_experiments()),
            failure_count=len(ledger.read_failures()), pattern_count=len(ledger.read_patterns()),
            association_count=len(ledger.read_associations()),
            snapshot_count=len(ledger.read_snapshots()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()), search_count=len(ledger.read_searches()))
