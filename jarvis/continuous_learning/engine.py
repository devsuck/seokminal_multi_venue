"""Continuous Learning Engine (P20) — 연구 기억·검색·유사도·학습 지표. **기억·분석 전용, 실행 없음.**

**거래·라이브 신호·모델 수정·전략 배포·자본 배분·자동 승인을 하지 않는다.** execution/broker/portfolio/permission/
deployment/live import·호출 없음. REMEMBER ≠ EXECUTE · RETRIEVE ≠ RECOMMEND · CONFIDENCE ≠ APPROVAL. 결정적·불변·
append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.continuous_learning import ledger
from jarvis.continuous_learning import models as M
from jarvis.continuous_learning.models import (
    GENESIS,
    ArtifactRecord,
    ExperimentMemoryRecord,
    FailureRecord,
    IllegalTransition,
    ImmutableRecordError,
    LearningMetricRecord,
    LessonEventRecord,
    MemoryEventRecord,
    MemorySummary,
    RetrievalEventRecord,
    ReviewerRequired,
    SuccessPatternRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
    metadata_hash,
)

_DISCLAIMER = ("Research Memory & Continuous Learning 데이터 — REMEMBER ≠ EXECUTE · RETRIEVE ≠ RECOMMEND · "
               "CONFIDENCE ≠ APPROVAL. 기억·검색·분석 전용 — 거래·라이브 신호·모델 수정·전략 배포·자본 배분·자동 승인 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ContinuousLearningEngine:
    """연구 기억·지속 학습 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/학습적용/거래/승인 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, source_ref, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             source_reference=source_ref, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ 기억 생애주기(event-sourced) ══════════════
    def _memory_event(self, mem, mtype, layer, sref, summary, mhash, tags, frm, to, note, now,
                      *, commit) -> MemoryEventRecord:
        seq = len(ledger.memory_events(mem))
        eid = M.memory_event_id(mem, to, seq)
        rec = MemoryEventRecord(memory_event_id=eid, memory_id=mem, memory_type=mtype,
                                source_layer=layer, source_reference=sref, summary=summary,
                                metadata_hash=mhash, tags=list(tags or []), from_state=frm,
                                to_state=to, note=note, created_at=now,
                                input_hash=input_digest(mem, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.memory_event_exists, ledger.memories_head,
                         ledger.append_memory_event, eid, rec, commit=commit)
        return MemoryEventRecord(**rec)

    def _memory_meta(self, mem) -> dict:
        evs = ledger.memory_events(mem)
        if not evs:
            raise UnknownEntityError(f"미등록 기억 {mem}")
        g = evs[0]
        return {"memory_type": g.get("memory_type"), "source_layer": g.get("source_layer"),
                "source_reference": g.get("source_reference"), "summary": g.get("summary"),
                "metadata_hash": g.get("metadata_hash"), "tags": g.get("tags", []),
                "state": evs[-1].get("to_state")}

    def memory_state(self, mem) -> str | None:
        evs = ledger.memory_events(mem)
        return evs[-1].get("to_state") if evs else None

    def _memory_transition(self, mem, to, note, now, *, commit) -> MemoryEventRecord:
        st = self.memory_state(mem)
        if st is None:
            raise UnknownEntityError(f"미등록 기억 {mem}")
        if not M.can_memory_transition(st, to):
            raise IllegalTransition(f"기억 {mem} {st}→{to} 불가")
        m = self._memory_meta(mem)
        return self._memory_event(mem, m["memory_type"], m["source_layer"], m["source_reference"],
                                  m["summary"], m["metadata_hash"], m["tags"], st, to, note, now,
                                  commit=commit)

    def register_memory(self, memory_type, source_layer, source_reference, summary="",
                        metadata=None, tags=None, now="", *, commit=False) -> MemoryEventRecord:
        """연구 기억 등록(genesis CREATED). **기록·색인 대상 선언만 — 자동 재사용 없음.**"""
        if memory_type not in M.MEMORY_TYPES:
            raise ValueError(f"미지원 memory_type {memory_type}")
        mem = M.memory_id(source_layer, source_reference)
        evs = ledger.memory_events(mem)
        if evs:
            g = evs[0]
            if g.get("summary") != summary:
                raise ImmutableRecordError(f"{mem} 기억 불변")
            return MemoryEventRecord(**{k: v for k, v in g.items()
                                        if k in MemoryEventRecord.__dataclass_fields__})
        mhash = metadata_hash(metadata)
        ev = self._memory_event(mem, memory_type, source_layer, source_reference, summary, mhash,
                                tags or [], GENESIS, M.M_CREATED, "created", now, commit=commit)
        self._artifact(M.ART_MEMORY, mem, "", source_reference, now, commit=commit)
        return ev

    def index_memory(self, mem, now="", *, commit=False):
        return self._memory_transition(mem, M.M_INDEXED, "indexed", now, commit=commit)

    def mark_retrievable(self, mem, now="", *, commit=False):
        return self._memory_transition(mem, M.M_RETRIEVABLE, "retrievable", now, commit=commit)

    def reference_memory(self, mem, now="", *, commit=False):
        return self._memory_transition(mem, M.M_REFERENCED, "referenced", now, commit=commit)

    def archive_memory(self, mem, now="", *, commit=False):
        return self._memory_transition(mem, M.M_ARCHIVED, "archived", now, commit=commit)

    def publish_kg_reference(self, mem, kg_reference, now="", *, commit=False) -> ArtifactRecord:
        """기억을 KG 로 '참조 레코드'로만 발행(상위 미변경). REFERENCED 상태로 표기. **상위 원장 미변경.**"""
        st = self.memory_state(mem)
        if st is None:
            raise UnknownEntityError(f"미등록 기억 {mem}")
        if M.can_memory_transition(st, M.M_REFERENCED):
            self._memory_transition(mem, M.M_REFERENCED, f"kg_ref:{kg_reference}", now, commit=commit)
        parent = M.artifact_id(M.ART_MEMORY, mem)
        return self._artifact(M.ART_REFERENCE, f"{mem}:{kg_reference}",
                              parent if ledger.artifact_exists(parent) else "", kg_reference, now,
                              commit=commit)

    # ══════════════ 실험 기억(불변) ══════════════
    def record_experiment_memory(self, experiment_reference, hypothesis="", dataset="",
                                 parameters=None, result_summary="", validation_status="UNKNOWN",
                                 failure_reason="", source_layer="research_operations", now="",
                                 *, commit=False) -> ExperimentMemoryRecord:
        """과거 실험 정보 기억(불변). 무엇이 되고 무엇이 실패했는지 — **자동 재사용 없음.**"""
        eid = M.experiment_memory_id(experiment_reference)
        existing = [r for r in ledger.read_experiments() if r.get("experiment_memory_id") == eid]
        if existing:
            return ExperimentMemoryRecord(**{k: v for k, v in existing[0].items()
                                             if k in ExperimentMemoryRecord.__dataclass_fields__})
        rec = ExperimentMemoryRecord(
            experiment_memory_id=eid, experiment_reference=experiment_reference,
            source_layer=source_layer, source_reference=experiment_reference, hypothesis=hypothesis,
            dataset=dataset, parameters=dict(parameters or {}), result_summary=result_summary,
            validation_status=validation_status, failure_reason=failure_reason, created_at=now,
            input_hash=input_digest(experiment_reference), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.experiment_exists, ledger.experiments_head, ledger.append_experiment,
                         eid, rec, commit=commit)
        self._artifact(M.ART_EXPERIMENT, eid, "", experiment_reference, now, commit=commit)
        return ExperimentMemoryRecord(**rec)

    # ══════════════ 실패 기억(불변, 음성 지식 보존) ══════════════
    def record_failure(self, failure_type, cause, evidence=None, affected_research="",
                       source_layer="research_operations", now="", *, commit=False) -> FailureRecord:
        """명시적 실패 기록(불변). **음성 지식 보존 — 무엇이 왜 실패했는가.**"""
        if failure_type not in M.FAILURE_TYPES:
            raise ValueError(f"미지원 failure_type {failure_type}")
        seq = len([r for r in ledger.read_failures()
                   if r.get("failure_type") == failure_type
                   and r.get("affected_research") == affected_research])
        fid = M.failure_id(failure_type, affected_research, seq)
        rec = FailureRecord(failure_id=fid, failure_type=failure_type, source_layer=source_layer,
                            source_reference=affected_research, cause=cause,
                            evidence=list(evidence or []), affected_research=affected_research,
                            created_at=now, input_hash=input_digest(failure_type, affected_research, seq),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.failure_exists, ledger.failures_head, ledger.append_failure, fid,
                         rec, commit=commit)
        return FailureRecord(**rec)

    # ══════════════ 성공 패턴(불변) ══════════════
    def record_success_pattern(self, pattern_type, description, supporting_records=None,
                              confidence=0.0, source_layer="research_operations", now="",
                              *, commit=False) -> SuccessPatternRecord:
        """성공 연구 패턴 저장(불변). **confidence 는 메타데이터 — 승인 아님.**"""
        pid = M.pattern_id(pattern_type, description)
        existing = [r for r in ledger.read_patterns() if r.get("pattern_id") == pid]
        if existing:
            return SuccessPatternRecord(**{k: v for k, v in existing[0].items()
                                           if k in SuccessPatternRecord.__dataclass_fields__})
        rec = SuccessPatternRecord(
            pattern_id=pid, pattern_type=pattern_type, source_layer=source_layer,
            source_reference=pattern_type, description=description,
            supporting_records=list(supporting_records or []), confidence=float(confidence),
            created_at=now, input_hash=input_digest(pattern_type, description),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.pattern_exists, ledger.patterns_head, ledger.append_pattern, pid,
                         rec, commit=commit)
        return SuccessPatternRecord(**rec)

    # ══════════════ 교훈 생애주기(event-sourced, 사람 검토 필요) ══════════════
    def _lesson_event(self, les, layer, sref, lesson, context, evidence, related, created_by,
                      reviewer, frm, to, note, now, *, commit) -> LessonEventRecord:
        seq = len(ledger.lesson_events(les))
        eid = M.lesson_event_id(les, to, seq)
        rec = LessonEventRecord(lesson_event_id=eid, lesson_id=les, source_layer=layer,
                                source_reference=sref, lesson=lesson, context=context,
                                evidence=list(evidence or []), related_experiments=list(related or []),
                                created_by=created_by, reviewer=reviewer, from_state=frm, to_state=to,
                                note=note, created_at=now, input_hash=input_digest(les, to, seq),
                                previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.lesson_event_exists, ledger.lessons_head, ledger.append_lesson_event,
                         eid, rec, commit=commit)
        return LessonEventRecord(**rec)

    def _lesson_meta(self, les) -> dict:
        evs = ledger.lesson_events(les)
        if not evs:
            raise UnknownEntityError(f"미등록 교훈 {les}")
        g = evs[0]
        return {"source_layer": g.get("source_layer"), "source_reference": g.get("source_reference"),
                "lesson": g.get("lesson"), "context": g.get("context"), "evidence": g.get("evidence", []),
                "related_experiments": g.get("related_experiments", []),
                "created_by": g.get("created_by"), "reviewer": evs[-1].get("reviewer"),
                "state": evs[-1].get("to_state")}

    def lesson_state(self, les) -> str | None:
        evs = ledger.lesson_events(les)
        return evs[-1].get("to_state") if evs else None

    def draft_lesson(self, lesson, context="", evidence=None, related_experiments=None,
                     created_by="", source_layer="research_operations", source_reference="",
                     now="", *, commit=False) -> LessonEventRecord:
        """연구 교훈 초안(genesis DRAFT)."""
        les = M.lesson_id(lesson, context)
        evs = ledger.lesson_events(les)
        if evs:
            return LessonEventRecord(**{k: v for k, v in evs[0].items()
                                        if k in LessonEventRecord.__dataclass_fields__})
        ev = self._lesson_event(les, source_layer, source_reference, lesson, context, evidence,
                                related_experiments, created_by, "", GENESIS, M.L_DRAFT, "draft",
                                now, commit=commit)
        self._artifact(M.ART_LESSON, les, "", source_reference, now, commit=commit)
        return ev

    def review_lesson(self, les, reviewer, now="", *, commit=False) -> LessonEventRecord:
        """교훈 검토(DRAFT→REVIEWED). **검토자 신원 필수.**"""
        if not reviewer or not str(reviewer).strip():
            raise ReviewerRequired("검토자 신원 필수 — 익명 검토 불가")
        st = self.lesson_state(les)
        if st is None:
            raise UnknownEntityError(f"미등록 교훈 {les}")
        if not M.can_lesson_transition(st, M.L_REVIEWED):
            raise IllegalTransition(f"교훈 {les} {st}→REVIEWED 불가")
        m = self._lesson_meta(les)
        return self._lesson_event(les, m["source_layer"], m["source_reference"], m["lesson"],
                                  m["context"], m["evidence"], m["related_experiments"],
                                  m["created_by"], reviewer, st, M.L_REVIEWED, "reviewed", now,
                                  commit=commit)

    def record_lesson(self, les, now="", *, commit=False) -> LessonEventRecord:
        """교훈 확정(REVIEWED→RECORDED). **사람 검토(검토자) 필수 — 자동 확정 없음.**"""
        st = self.lesson_state(les)
        if st is None:
            raise UnknownEntityError(f"미등록 교훈 {les}")
        if not M.can_lesson_transition(st, M.L_RECORDED):
            raise IllegalTransition(f"교훈 {les} {st}→RECORDED 불가")
        m = self._lesson_meta(les)
        if not m.get("reviewer"):
            raise ReviewerRequired(f"{les} 확정 불가 — 사람 검토자 필요")
        return self._lesson_event(les, m["source_layer"], m["source_reference"], m["lesson"],
                                  m["context"], m["evidence"], m["related_experiments"],
                                  m["created_by"], m["reviewer"], st, M.L_RECORDED, "recorded", now,
                                  commit=commit)

    # ══════════════ 검색(결정적) ══════════════
    def _record_retrieval(self, query_kind, query, result_refs, now, *, commit):
        seq = len(ledger.read_retrievals())
        qh = input_digest(query_kind, query, seq)
        rid = M.retrieval_id(query_kind, qh, seq)
        rec = RetrievalEventRecord(retrieval_id=rid, query_kind=query_kind, query=dict(query or {}),
                                   result_refs=list(result_refs), result_count=len(result_refs),
                                   source_layer="continuous_learning", source_reference=query_kind,
                                   created_at=now, input_hash=qh, previous_hash=GENESIS).to_dict()
        self._emit(ledger.retrieval_exists, ledger.retrievals_head, ledger.append_retrieval, rid,
                   rec, commit=commit)
        return result_refs

    def search_memory(self, memory_type=None, source=None, tags=None, similarity_hash=None,
                      since=None, until=None, now="", *, commit=False) -> list:
        """결정적 기억 검색(유형·소스·태그·metadata_hash·기간). 반환: memory_id 정렬 목록."""
        results = []
        for mem in ledger.memory_ids():
            m = self._memory_meta(mem)
            g0 = ledger.memory_events(mem)[0]
            if memory_type and m["memory_type"] != memory_type:
                continue
            if source and m["source_layer"] != source:
                continue
            if tags and not set(tags) <= set(m["tags"]):
                continue
            if similarity_hash and m["metadata_hash"] != similarity_hash:
                continue
            created = g0.get("created_at", "")
            if since and created < since:
                continue
            if until and created > until:
                continue
            results.append(mem)
        results = sorted(results)
        self._record_retrieval("search_memory", {"memory_type": memory_type, "source": source,
                               "tags": sorted(tags or [])}, results, now, commit=commit)
        return results

    def find_similar_experiments(self, parameters=None, dataset=None, top=5, now="",
                                 *, commit=False) -> list:
        """실험 유사 검색(파라미터·데이터셋 유사도, 결정적). 반환: [(experiment_memory_id, score)]."""
        target_keys = list((parameters or {}).keys())
        scored = []
        for r in ledger.read_experiments():
            pscore = M.metadata_similarity(parameters or {}, r.get("parameters") or {})
            dscore = 1.0 if dataset and r.get("dataset") == dataset else 0.0
            score = round((pscore + dscore) / 2, 6) if dataset else pscore
            scored.append((r.get("experiment_memory_id"), score))
        scored.sort(key=lambda x: (-x[1], x[0]))
        out = scored[:top]
        self._record_retrieval("find_similar_experiments", {"keys": sorted(target_keys)},
                               [e for e, _ in out], now, commit=commit)
        return out

    def find_related_failures(self, failure_type=None, affected_research=None, tags=None, now="",
                              *, commit=False) -> list:
        """관련 실패 검색(유형·영향 연구). 반환: failure_id 정렬 목록."""
        out = []
        for r in ledger.read_failures():
            if failure_type and r.get("failure_type") != failure_type:
                continue
            if affected_research and r.get("affected_research") != affected_research:
                continue
            out.append(r.get("failure_id"))
        out = sorted(out)
        self._record_retrieval("find_related_failures",
                               {"failure_type": failure_type, "affected": affected_research}, out,
                               now, commit=commit)
        return out

    def retrieve_lessons(self, state=None, created_by=None, now="", *, commit=False) -> list:
        """교훈 검색(상태·작성자). 반환: lesson_id 정렬 목록."""
        out = []
        for les in ledger.lesson_ids():
            m = self._lesson_meta(les)
            if state and m["state"] != state:
                continue
            if created_by and m["created_by"] != created_by:
                continue
            out.append(les)
        out = sorted(out)
        self._record_retrieval("retrieve_lessons", {"state": state, "created_by": created_by}, out,
                               now, commit=commit)
        return out

    # ══════════════ 유사도(점수만) ══════════════
    def memory_similarity(self, mem_a, mem_b) -> float:
        """두 기억 유사도(유형 일치 + 태그 자카드 + metadata_hash 일치). 점수만, 추천 없음."""
        a, b = self._memory_meta(mem_a), self._memory_meta(mem_b)
        type_s = 1.0 if a["memory_type"] == b["memory_type"] else 0.0
        tag_s = M.jaccard(a["tags"], b["tags"])
        meta_s = 1.0 if a["metadata_hash"] == b["metadata_hash"] else 0.0
        return round((type_s + tag_s + meta_s) / 3, 6)

    def experiment_similarity(self, exp_a, exp_b) -> float:
        ra = next((r for r in ledger.read_experiments() if r.get("experiment_memory_id") == exp_a), None)
        rb = next((r for r in ledger.read_experiments() if r.get("experiment_memory_id") == exp_b), None)
        if not ra or not rb:
            raise UnknownEntityError("미등록 실험 기억")
        return M.metadata_similarity(ra.get("parameters") or {}, rb.get("parameters") or {})

    def failure_similarity(self, fail_a, fail_b) -> float:
        ra = next((r for r in ledger.read_failures() if r.get("failure_id") == fail_a), None)
        rb = next((r for r in ledger.read_failures() if r.get("failure_id") == fail_b), None)
        if not ra or not rb:
            raise UnknownEntityError("미등록 실패 기억")
        type_s = 1.0 if ra.get("failure_type") == rb.get("failure_type") else 0.0
        ev_s = M.jaccard(ra.get("evidence") or [], rb.get("evidence") or [])
        return round((type_s + ev_s) / 2, 6)

    # ══════════════ 학습 지표(관찰) ══════════════
    def record_metric(self, name, value, metadata=None, source_layer="continuous_learning",
                      source_reference="", now="", *, commit=False) -> LearningMetricRecord:
        """연구 개선 지표 기록(불변). **관찰일 뿐.**"""
        seq = len([r for r in ledger.read_metrics() if r.get("name") == name])
        mid = M.metric_id(name, seq)
        rec = LearningMetricRecord(metric_id=mid, name=name, value=float(value),
                                   source_layer=source_layer, source_reference=source_reference,
                                   metadata=dict(metadata or {}), is_observation=True, created_at=now,
                                   input_hash=input_digest(name, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.metric_exists, ledger.metrics_head, ledger.append_metric, mid, rec,
                         commit=commit)
        return LearningMetricRecord(**rec)

    def repeated_failure_count(self, failure_type) -> int:
        return len([r for r in ledger.read_failures() if r.get("failure_type") == failure_type])

    def reused_knowledge_count(self) -> int:
        """참조 발행(REFERENCE) 아티팩트 수 — 재사용 지식 관찰."""
        return len([a for a in ledger.read_artifacts() if a.get("artifact_type") == M.ART_REFERENCE])

    def learning_stats(self) -> dict:
        """학습 통계 집계(결정적, 관찰)."""
        fails: dict = {}
        for r in ledger.read_failures():
            fails[r.get("failure_type")] = fails.get(r.get("failure_type"), 0) + 1
        return {"total_memories": len(ledger.memory_ids()),
                "total_experiments": len(ledger.read_experiments()),
                "total_failures": len(ledger.read_failures()),
                "failures_by_type": dict(sorted(fails.items())),
                "total_patterns": len(ledger.read_patterns()),
                "recorded_lessons": len([les for les in ledger.lesson_ids()
                                         if self.lesson_state(les) == M.L_RECORDED]),
                "reused_knowledge": self.reused_knowledge_count(),
                "retrievals": len(ledger.read_retrievals())}

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.continuous_learning.verify import verify_chain
        return verify_chain()

    def list_memories(self) -> list:
        return ledger.memory_ids()

    def memories_in_state(self, state) -> list:
        return sorted(m for m in ledger.memory_ids() if self.memory_state(m) == state)

    def summary(self, now="") -> MemorySummary:
        return MemorySummary(
            timestamp=now, memory_event_count=len(ledger.read_memory_events()),
            experiment_memory_count=len(ledger.read_experiments()),
            failure_count=len(ledger.read_failures()), pattern_count=len(ledger.read_patterns()),
            lesson_event_count=len(ledger.read_lesson_events()),
            retrieval_count=len(ledger.read_retrievals()), metric_count=len(ledger.read_metrics()),
            artifact_count=len(ledger.read_artifacts()))
