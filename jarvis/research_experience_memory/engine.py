"""Research Memory & Experience Engine (P12.7) — 장기 연구 기억·경험. **기억·기록·검색 전용.**

성공/실패 실험·연구 교훈·검증 결과·에이전트 경험·의사결정 결과를 저장·검색한다. **실행 능력 없음.** execution/
broker/portfolio/risk/permission/deployment/live import·호출 없음. MEMORY ≠ EXECUTION · SIMILARITY ≠ RECOMMENDATION ·
VALIDATED ≠ DEPLOYED. 유사도는 메타데이터 전용이며 자동 추천을 하지 않는다. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_experience_memory import ledger
from jarvis.research_experience_memory.models import (
    ART_EPISODE,
    ART_MEMORY,
    ART_SUMMARY,
    GENESIS,
    M_ARCHIVED,
    M_CREATED,
    M_INDEXED,
    M_RECORDED,
    M_REFERENCED,
    M_RETRIEVABLE,
    MEMORY_TYPES,
    ArtifactRecord,
    DanglingReferenceError,
    EpisodeRecord,
    ExperienceRecord,
    FailureRecord,
    IllegalMemoryTransition,
    ImmutableEpisodeError,
    ImmutableExperienceError,
    ImmutableFailureError,
    ImmutableMemoryError,
    ImmutablePatternError,
    InvalidMemoryType,
    MemoryEventRecord,
    MemorySummary,
    PatternRecord,
    RetrievalRecord,
    SummaryRecord,
    UnknownEpisodeError,
    UnknownMemoryError,
    ancestors,
    artifact_id as _artifact_id,
    can_transition,
    content_hash,
    context_digest,
    episode_id as _episode_id,
    experience_id as _experience_id,
    failure_id as _failure_id,
    input_digest,
    memory_event_id as _memory_event_id,
    memory_id as _memory_id,
    metadata_similarity,
    pattern_id as _pattern_id,
    retrieval_id as _retrieval_id,
    summary_id as _summary_id,
)

_DISCLAIMER = ("Research Memory & Experience 데이터 — MEMORY ≠ EXECUTION · SIMILARITY ≠ RECOMMENDATION · "
               "VALIDATED ≠ DEPLOYED. 장기 연구 기억·기록·검색 전용 — 실행·거래·배포·자본 배분·권한 변경 없음. "
               "유사도는 메타데이터 전용이며 자동 추천을 하지 않는다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchExperienceMemoryEngine:
    """장기 연구 기억·경험 엔진. 불변·append-only·이벤트 소싱·결정적. 실행 권한 없음."""

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
    def _memory_event(self, memory: str, memory_type: str, source_layer: str, source_ref: str,
                    title: str, context: str, context_hash: str, metadata: dict, frm: str, to: str,
                    note: str, now: str, *, commit: bool) -> MemoryEventRecord:
        seq = len(ledger.memory_events(memory))
        eid = _memory_event_id(memory, to, seq)
        rec = MemoryEventRecord(
            memory_event_id=eid, memory_id=memory, memory_type=memory_type, source_layer=source_layer,
            source_ref=source_ref, title=title, context=context, context_hash=context_hash,
            metadata=dict(sorted((metadata or {}).items())), from_state=frm, to_state=to, note=note,
            occurred_at=now, input_hash=input_digest(memory, to, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.memory_event_exists(eid):
            head = ledger.memories_head()
            ledger.append_memory_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return MemoryEventRecord(**rec)

    def _meta(self, memory: str) -> dict:
        evs = ledger.memory_events(memory)
        if not evs:
            raise UnknownMemoryError(f"미등록 기억 {memory}")
        g = evs[0]
        return {"memory_id": memory, "memory_type": g.get("memory_type"),
                "source_layer": g.get("source_layer"), "source_ref": g.get("source_ref"),
                "title": g.get("title"), "context": g.get("context"),
                "context_hash": g.get("context_hash"), "metadata": g.get("metadata", {}),
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
        m = self._meta(memory)
        return self._memory_event(memory, m["memory_type"], m["source_layer"], m["source_ref"],
                                 m["title"], m["context"], m["context_hash"], m["metadata"], frm, to,
                                 note, now, commit=commit)

    # ══════════════ register_memory (CREATED→RECORDED) ══════════════
    def register_memory(self, source_layer: str, source_ref: str, memory_type: str, title: str,
                     context: str = "", metadata: dict = None, now: str = "",
                     *, commit: bool = False) -> MemoryEventRecord:
        """기억 등록(genesis CREATED→RECORDED). 재작성 금지. **기록만.**"""
        if memory_type not in MEMORY_TYPES:
            raise InvalidMemoryType(f"미등록 기억 유형 {memory_type}")
        mem = _memory_id(source_layer, source_ref, memory_type, title)
        chash = context_digest(context)
        evs = ledger.memory_events(mem)
        if evs:
            g = evs[0]
            if g.get("context_hash") != chash:
                raise ImmutableMemoryError(f"{mem} 기억 불변 — 재작성 금지")
            return MemoryEventRecord(**{k: v for k, v in g.items()
                                        if k in MemoryEventRecord.__dataclass_fields__})
        md = dict(sorted((metadata or {}).items()))
        self._memory_event(mem, memory_type, source_layer, source_ref, title, context, chash, md,
                           GENESIS, M_CREATED, "created", now, commit=commit)
        self._artifact(ART_MEMORY, mem, "", now, commit=commit)
        return self._memory_event(mem, memory_type, source_layer, source_ref, title, context, chash,
                                  md, M_CREATED, M_RECORDED, "recorded", now, commit=commit)

    def memory_meta(self, memory: str) -> dict:
        return self._meta(memory)

    # ══════════════ record_experience (RECORDED→INDEXED) ══════════════
    def record_experience(self, memory: str, subject: str, outcome: str = "", lesson: str = "",
                       agent: str = "", now: str = "", *, commit: bool = False) -> ExperienceRecord:
        """경험 기록(불변) + RECORDED→INDEXED. **기록만.**"""
        st = self._require_memory(memory)
        eid = _experience_id(memory, subject)
        existing = ledger.get_experience(eid)
        if existing is not None:
            if existing.get("outcome") != outcome:
                raise ImmutableExperienceError(f"{eid} 경험 불변 — 변경 불가")
            return ExperienceRecord(**{k: v for k, v in existing.items()
                                       if k in ExperienceRecord.__dataclass_fields__})
        rec = ExperienceRecord(experience_id=eid, memory_id=memory, subject=subject, outcome=outcome,
                               lesson=lesson, agent=agent, recorded_at=now,
                               input_hash=input_digest(memory, subject),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experience_exists(eid):
            head = ledger.experiences_head()
            ledger.append_experience(_seal(rec, head["record_hash"] if head else GENESIS))
        if st == M_RECORDED:
            self._transition(memory, M_INDEXED, "indexed", now, commit=commit)
        return ExperienceRecord(**rec)

    # ══════════════ record_failure ══════════════
    def record_failure(self, memory: str, approach: str, reason: str = "", recurrence: int = 1,
                    now: str = "", *, commit: bool = False) -> FailureRecord:
        """실패 기억 기록(불변). **추적·기록만.**"""
        self._require_memory(memory)
        fid = _failure_id(memory, approach)
        existing = ledger.get_failure(fid)
        if existing is not None:
            if existing.get("recurrence") != int(recurrence):
                raise ImmutableFailureError(f"{fid} 실패 기억 불변 — 변경 불가")
            return FailureRecord(**{k: v for k, v in existing.items()
                                    if k in FailureRecord.__dataclass_fields__})
        rec = FailureRecord(failure_id=fid, memory_id=memory, approach=approach, reason=reason,
                            recurrence=int(recurrence), recorded_at=now,
                            input_hash=input_digest(memory, approach),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.failure_exists(fid):
            head = ledger.failures_head()
            ledger.append_failure(_seal(rec, head["record_hash"] if head else GENESIS))
        return FailureRecord(**rec)

    # ══════════════ record_success_pattern ══════════════
    def record_success_pattern(self, memory: str, pattern: str, conditions: str = "",
                            confidence: float = 0.0, now: str = "",
                            *, commit: bool = False) -> PatternRecord:
        """성공 패턴 기록(불변). confidence 는 기록 값(추천 아님). **기록만.**"""
        self._require_memory(memory)
        pid = _pattern_id(memory, pattern)
        existing = ledger.get_pattern(pid)
        if existing is not None:
            if abs(float(existing.get("confidence", 0.0)) - float(confidence)) > 1e-9:
                raise ImmutablePatternError(f"{pid} 패턴 불변 — 변경 불가")
            return PatternRecord(**{k: v for k, v in existing.items()
                                    if k in PatternRecord.__dataclass_fields__})
        rec = PatternRecord(pattern_id=pid, memory_id=memory, pattern=pattern, conditions=conditions,
                            confidence=round(float(confidence), 8), recorded_at=now,
                            input_hash=input_digest(memory, pattern),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        return PatternRecord(**rec)

    # ══════════════ create_episode (Research Episodes) ══════════════
    def create_episode(self, name: str, description: str = "", memory_refs=None, now: str = "",
                    *, commit: bool = False) -> EpisodeRecord:
        """연구 에피소드 생성(불변, 기억 묶음). dangling 참조 거부. **기록만.**"""
        refs = sorted(set(memory_refs or []))
        for r in refs:
            if not ledger.memory_events(r):
                raise DanglingReferenceError(f"미등록 기억 참조 {r}")
        eid = _episode_id(name)
        existing = ledger.get_episode(eid)
        if existing is not None:
            if sorted(existing.get("memory_refs", [])) != refs:
                raise ImmutableEpisodeError(f"{eid} 에피소드 불변 — 변경 불가")
            return EpisodeRecord(**{k: v for k, v in existing.items()
                                    if k in EpisodeRecord.__dataclass_fields__})
        rec = EpisodeRecord(episode_id=eid, name=name, description=description, memory_refs=refs,
                            created_at=now, input_hash=input_digest(name),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.episode_exists(eid):
            head = ledger.episodes_head()
            ledger.append_episode(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_EPISODE, eid, "", now, commit=commit)
        return EpisodeRecord(**rec)

    # ══════════════ make_retrievable (INDEXED→RETRIEVABLE) ══════════════
    def make_retrievable(self, memory: str, now: str = "",
                      *, commit: bool = False) -> MemoryEventRecord:
        """검색 가능 표시(INDEXED→RETRIEVABLE). **상태 기록만.**"""
        return self._transition(memory, M_RETRIEVABLE, "retrievable", now, commit=commit)

    def archive_memory(self, memory: str, now: str = "",
                    *, commit: bool = False) -> MemoryEventRecord:
        return self._transition(memory, M_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ retrieve_memory (deterministic, recorded) ══════════════
    def _memory_text(self, memory: str) -> str:
        m = self._meta(memory)
        parts = [m["title"], m["context"]]
        for e in ledger.memory_experiences(memory):
            parts.append(e.get("subject", ""))
            parts.append(e.get("lesson", ""))
        return " ".join(p for p in parts if p)

    def retrieve_memory(self, query: str = "", memory_type: str = "", now: str = "",
                     *, commit: bool = False) -> RetrievalRecord:
        """기억 검색(exact/type 필터, 결정적·기록). 매치된 기억을 REFERENCED 로 표시. **조회·기록만.**"""
        results: list = []
        scores: dict = {}
        explanation: dict = {}
        for mem in ledger.memory_ids():
            m = self._meta(mem)
            if memory_type and m["memory_type"] != memory_type:
                continue
            if m["state"] not in (M_RETRIEVABLE, M_REFERENCED):
                continue
            if query and query not in (m["title"] or "") and query not in mem:
                continue
            results.append(mem)
            scores[mem] = 1.0
            explanation[mem] = "match:" + (m["memory_type"] or "")
        for mem in results:
            if commit and self.current_state(mem) == M_RETRIEVABLE:
                self._transition(mem, M_REFERENCED, "referenced", now, commit=commit)
        seq = len(ledger.read_retrievals())
        rid = _retrieval_id(query, "RETRIEVE:" + (memory_type or "ALL"), seq)
        rec = RetrievalRecord(retrieval_id=rid, query=query, mode="RETRIEVE",
                              filters={"memory_type": memory_type}, result_ids=sorted(results),
                              scores=dict(sorted(scores.items())),
                              explanation=dict(sorted(explanation.items())), created_at=now,
                              input_hash=input_digest(query, "RETRIEVE", seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.retrieval_exists(rid):
            head = ledger.retrievals_head()
            ledger.append_retrieval(_seal(rec, head["record_hash"] if head else GENESIS))
        return RetrievalRecord(**rec)

    # ══════════════ find_similar_experience (metadata similarity, recorded) ══════════════
    def find_similar_experience(self, memory: str, threshold: float = 0.0, now: str = "",
                             *, commit: bool = False) -> RetrievalRecord:
        """메타데이터 유사 경험 검색(결정적·설명가능·기록). **유사도는 메타데이터 전용 — 추천 아님.**"""
        base = self._meta(memory)
        results: list = []
        scores: dict = {}
        explanation: dict = {}
        for mem in ledger.memory_ids():
            if mem == memory:
                continue
            score, matched = metadata_similarity(base["metadata"], self._meta(mem)["metadata"])
            if score > threshold or (threshold == 0.0 and score > 0.0):
                results.append(mem)
                scores[mem] = score
                explanation[mem] = "sim_keys:" + ",".join(matched) if matched else "no_match"
        results = sorted(results, key=lambda m: (-scores[m], m))
        seq = len(ledger.read_retrievals())
        rid = _retrieval_id(memory, "SIMILAR", seq)
        rec = RetrievalRecord(retrieval_id=rid, query=memory, mode="SIMILAR",
                              filters={"threshold": threshold}, result_ids=results,
                              scores=dict(sorted(scores.items())),
                              explanation=dict(sorted(explanation.items())), created_at=now,
                              input_hash=input_digest(memory, "SIMILAR", seq),
                              previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.retrieval_exists(rid):
            head = ledger.retrievals_head()
            ledger.append_retrieval(_seal(rec, head["record_hash"] if head else GENESIS))
        return RetrievalRecord(**rec)

    # ══════════════ generate_summary (Memory Summary) ══════════════
    def generate_summary(self, scope: str = "ALL", scope_id: str = "ALL", now: str = "",
                      *, commit: bool = False) -> SummaryRecord:
        """기억 요약(유형·상태 분포). **관찰·기록만.**"""
        mems = ledger.memory_ids()
        if scope == "TYPE":
            mems = [m for m in mems if self._meta(m)["memory_type"] == scope_id]
        type_dist: dict = {}
        state_dist: dict = {}
        for m in mems:
            meta = self._meta(m)
            type_dist[meta["memory_type"]] = type_dist.get(meta["memory_type"], 0) + 1
            state_dist[meta["state"]] = state_dist.get(meta["state"], 0) + 1
        sid = _summary_id(scope, scope_id, now)
        rec = SummaryRecord(
            summary_id=sid, scope=scope, scope_id=scope_id, memory_count=len(mems),
            experience_count=len(ledger.read_experiences()),
            failure_count=len(ledger.read_failures()), pattern_count=len(ledger.read_patterns()),
            type_distribution=dict(sorted(type_dist.items())),
            state_distribution=dict(sorted(state_dist.items())), created_at=now,
            input_hash=input_digest(scope, scope_id, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.summary_exists(sid):
            head = ledger.summaries_head()
            ledger.append_summary(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_SUMMARY, sid, "", now, commit=commit)
        return SummaryRecord(**rec)

    # ══════════════ build_lineage (episode → memory 계보) ══════════════
    def build_lineage(self, episode: str, now: str = "", *, commit: bool = False) -> list:
        """에피소드→기억 아티팩트 계보 생성(불변). 반환 ArtifactRecord 리스트."""
        ep = ledger.get_episode(episode)
        if ep is None:
            raise UnknownEpisodeError(f"미등록 에피소드 {episode}")
        parent = _artifact_id(ART_EPISODE, episode)
        out: list = []
        for mem in ep.get("memory_refs", []):
            # 에피소드→기억 멤버십 링크 아티팩트(복합 ref 로 유일). 기억 아티팩트 불변성 침해 없음.
            out.append(self._artifact(ART_MEMORY, f"{episode}:{mem}",
                                      parent if ledger.artifact_exists(parent) else "", now,
                                      commit=commit))
        return out

    def episode_memories(self, episode: str) -> list:
        ep = ledger.get_episode(episode)
        if ep is None:
            raise UnknownEpisodeError(f"미등록 에피소드 {episode}")
        return sorted(ep.get("memory_refs", []))

    def memory_episodes(self, memory: str) -> list:
        return sorted(ep.get("episode_id") for ep in ledger.read_episodes()
                      if memory in ep.get("memory_refs", []))

    def lineage_ancestors(self, memory: str) -> list:
        """기억의 멤버십 링크 아티팩트 조상(에피소드 아티팩트 포함, 결정적)."""
        arts = ledger.read_artifacts()
        edges = [(a.get("artifact_id"), a.get("parent_artifact")) for a in arts
                 if a.get("parent_artifact")]
        starts = [a.get("artifact_id") for a in arts
                  if a.get("artifact_type") == ART_MEMORY and str(a.get("ref_id", "")).endswith(
                      ":" + memory)]
        out: set = set()
        for s in starts:
            out.update(ancestors(edges, s))
        return sorted(out)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_experience_memory.verify import verify_chain
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
            timestamp=now, memory_event_count=len(ledger.read_memory_events()),
            experience_count=len(ledger.read_experiences()),
            failure_count=len(ledger.read_failures()), pattern_count=len(ledger.read_patterns()),
            episode_count=len(ledger.read_episodes()),
            retrieval_count=len(ledger.read_retrievals()),
            summary_count=len(ledger.read_summaries()), artifact_count=len(ledger.read_artifacts()))
