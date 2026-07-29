"""Research Memory Intelligence Engine (P27) — 장기 연구 메모리 지능. **지식 메모리 전용, 동작 없음.**

**지식 메모리 시스템이다 — 결정하지 않는다.** 거래 결정·전략 배포·실험 실행·모델 수정·연구 산출 승인·자본 배분을 하지
않는다. execution/broker/live_trading/portfolio_execution import·호출 없음. MEMORY ASSISTS RESEARCH · MEMORY
DOES NOT DECIDE. 진화는 과거 메모리 변경이 아니라 새 append 이벤트로만. 결정적·불변·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_memory_intelligence import ledger
from jarvis.research_memory_intelligence import models as M
from jarvis.research_memory_intelligence.models import (
    GENESIS,
    ArtifactRecord,
    EvolutionEventRecord,
    EvolutionReportRecord,
    FailureRecord,
    IllegalMemoryTransition,
    LessonRecord,
    MemoryEventRecord,
    MemoryIntelligenceSummary,
    PatternRecord,
    RetrievalRecord,
    SuccessRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
    value_hash,
)

_DISCLAIMER = ("Research Knowledge Evolution & Memory Intelligence 데이터 — MEMORY ASSISTS RESEARCH · "
               "MEMORY DOES NOT DECIDE. 연구 지식 보존·패턴 추적·교훈 연결·재사용 지식·진화 이력 전용 — 거래 결정·전략 "
               "배포·실험 실행·모델 수정·연구 산출 승인·자본 배분 없음. 진화는 새 append 이벤트로만(과거 메모리 변경 없음).")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchMemoryIntelligenceEngine:
    """연구 메모리 지능 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/거래/배포/승인/선택 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ 메모리 생애주기(event-sourced) ══════════════
    def _memory_event(self, mem, src, category, chash, importance, frm, to, note, now, *, commit):
        seq = len(ledger.memory_events(mem))
        eid = M.memory_event_id(mem, to, seq)
        rec = MemoryEventRecord(
            memory_event_id=eid, memory_id=mem, source_reference=src, category=category,
            content_hash=chash, importance_score=float(importance), from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(mem, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.memory_event_exists, ledger.memories_head,
                         ledger.append_memory_event, eid, rec, commit=commit)
        return MemoryEventRecord(**rec)

    def memory_state(self, mem) -> str | None:
        evs = ledger.memory_events(mem)
        return evs[-1].get("to_state") if evs else None

    def _memory_meta(self, mem) -> dict:
        evs = ledger.memory_events(mem)
        if not evs:
            raise UnknownEntityError(f"미등록 메모리 {mem}")
        g = evs[0]
        return {"source_reference": g.get("source_reference"), "category": g.get("category"),
                "content_hash": g.get("content_hash"), "importance_score": g.get("importance_score"),
                "state": evs[-1].get("to_state")}

    def _memory_transition(self, mem, to, note, now, *, commit):
        m = self._memory_meta(mem)
        frm = m["state"]
        if not M.can_memory_transition(frm, to):
            raise IllegalMemoryTransition(f"메모리 {mem} {frm}→{to} 불가")
        return self._memory_event(mem, m["source_reference"], m["category"], m["content_hash"],
                                  m["importance_score"], frm, to, note, now, commit=commit)

    def register_memory(self, source_reference, category, content, importance_score=0.5, now="",
                        *, commit=False) -> MemoryEventRecord:
        """지식 메모리 등록(genesis CREATED, 이벤트 소싱, content 불변 해시). **보존만.**"""
        if category not in M.MEMORY_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        mem = M.memory_id(source_reference, category, content)
        evs = ledger.memory_events(mem)
        if evs:
            return MemoryEventRecord(**{k: v for k, v in evs[0].items()
                                        if k in MemoryEventRecord.__dataclass_fields__})
        chash = M.memory_content_hash(content)
        ev = self._memory_event(mem, source_reference, category, chash,
                                M.clamp01(importance_score), GENESIS, M.M_CREATED, "created", now,
                                commit=commit)
        self._artifact(M.ART_MEMORY, mem, "", now, commit=commit)
        return ev

    def archive_memory(self, mem, note="archived", now="", *, commit=False):
        return self._memory_transition(mem, M.M_ARCHIVED, note, now, commit=commit)

    def memory_confidence(self, mem) -> float:
        """메모리 신뢰도 = 기저 중요도 + 진화 로그 재생(결정적). **파생값 — 레코드 변경 없음.**"""
        m = self._memory_meta(mem)
        changes = [e.get("change_type") for e in ledger.evolution_for(mem)]
        return M.evolve_confidence(m["importance_score"], changes)

    # ══════════════ record_lesson ══════════════
    def record_lesson(self, origin, lesson, evidence=None, impact="", now="",
                      *, commit=False) -> LessonRecord:
        """연구 교훈 기록(불변). **저장만.**"""
        lid = M.lesson_id(origin, lesson)
        rec = LessonRecord(lesson_id=lid, origin=origin, lesson=lesson, evidence=dict(evidence or {}),
                           impact=impact, created_at=now, input_hash=input_digest(origin, lesson),
                           previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.lesson_exists, ledger.lessons_head, ledger.append_lesson, lid, rec,
                         commit=commit)
        self._artifact(M.ART_LESSON, lid, "", now, commit=commit)
        return LessonRecord(**rec)

    # ══════════════ store_pattern ══════════════
    def store_pattern(self, pattern_type, signature, occurrences=1, confidence=0.5, now="",
                      *, commit=False) -> PatternRecord:
        """패턴 기록(불변). **추적만.**"""
        if pattern_type not in M.PATTERN_TYPES:
            raise ValueError(f"미지원 pattern_type {pattern_type}")
        pid = M.pattern_id(pattern_type, signature)
        rec = PatternRecord(
            pattern_id=pid, pattern_type=pattern_type, signature=signature,
            occurrences=int(occurrences), confidence=M.clamp01(confidence), created_at=now,
            input_hash=input_digest(pattern_type, signature), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.pattern_exists, ledger.patterns_head, ledger.append_pattern, pid,
                         rec, commit=commit)
        self._artifact(M.ART_PATTERN, pid, "", now, commit=commit)
        return PatternRecord(**rec)

    # ══════════════ record_success / record_failure ══════════════
    def record_success(self, origin, summary, evidence=None, now="",
                       *, commit=False) -> SuccessRecord:
        """성공 메모리 기록(불변). **저장만.**"""
        sid = M.success_id(origin, summary)
        rec = SuccessRecord(success_id=sid, origin=origin, summary=summary,
                            evidence=dict(evidence or {}), created_at=now,
                            input_hash=input_digest(origin, summary), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.success_exists, ledger.successes_head, ledger.append_success, sid,
                         rec, commit=commit)
        self._artifact(M.ART_SUCCESS, sid, "", now, commit=commit)
        return SuccessRecord(**rec)

    def record_failure(self, origin, summary, evidence=None, now="",
                       *, commit=False) -> FailureRecord:
        """실패 메모리 기록(불변). **저장만.**"""
        fid = M.failure_id(origin, summary)
        rec = FailureRecord(failure_id=fid, origin=origin, summary=summary,
                            evidence=dict(evidence or {}), created_at=now,
                            input_hash=input_digest(origin, summary), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.failure_exists, ledger.failures_head, ledger.append_failure, fid,
                         rec, commit=commit)
        self._artifact(M.ART_FAILURE, fid, "", now, commit=commit)
        return FailureRecord(**rec)

    # ══════════════ 진화(새 append 이벤트로만) ══════════════
    def _evolution_event(self, mem, change_type, related, reason, now, *, commit):
        seq = len(ledger.evolution_for(mem))
        eid = M.evolution_event_id(mem, change_type, seq)
        rec = EvolutionEventRecord(
            event_id=eid, memory_id=mem, change_type=change_type, related_memory=related,
            reason=reason, timestamp=now, input_hash=input_digest(mem, change_type, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.evolution_exists, ledger.evolution_head, ledger.append_evolution,
                         eid, rec, commit=commit)
        return EvolutionEventRecord(**rec)

    def evolve_memory(self, mem, change_type, reason="", related_memory="", now="",
                      *, commit=False) -> EvolutionEventRecord:
        """지식 진화(불변 append). change_type ∈ CONNECTED/REINFORCED/WEAKENED/DEPRECATED. 생애주기도 함께 전이.

        **과거 메모리 절대 변경 없음 — 새 이벤트만 추가하고 신뢰도는 로그 재생으로 파생.**
        """
        self._memory_meta(mem)  # 존재 검증
        if change_type not in M.CHANGE_TYPES:
            raise ValueError(f"미지원 change_type {change_type}")
        ev = self._evolution_event(mem, change_type, related_memory, reason, now, commit=commit)
        target = M.CHANGE_TO_STATE[change_type]
        frm = self.memory_state(mem)
        if frm != target and M.can_memory_transition(frm, target):
            self._memory_transition(mem, target, f"evolve:{change_type}", now, commit=commit)
        return ev

    def connect_knowledge(self, mem, related_memory, reason="", now="",
                          *, commit=False) -> EvolutionEventRecord:
        """두 메모리 연결(CONNECTED 진화 이벤트 + 계보 간선). **연결·계보만.**"""
        self._memory_meta(mem)
        self._memory_meta(related_memory)  # 양쪽 존재 검증
        ev = self.evolve_memory(mem, "CONNECTED", reason, related_memory, now, commit=commit)
        self._artifact(M.ART_MEMORY, f"{mem}->{related_memory}",
                       M.artifact_id(M.ART_MEMORY, mem), now, commit=commit)
        return ev

    # ══════════════ retrieve_context (결정적 유사도, 참조만) ══════════════
    def retrieve_context(self, query_context, top_k=5, now="", *, commit=False) -> RetrievalRecord:
        """컨텍스트 검색: 유사도·신뢰도 기반 메모리 참조 반환(결정적). **참조만 — 자동 추천/전략 선택 없음.**"""
        scored = []
        for mem in ledger.memory_ids():
            m = self._memory_meta(mem)
            sim = M.jaccard(query_context, f"{m['source_reference']} {m['category']}")
            conf = self.memory_confidence(mem)
            score = round(0.6 * sim + 0.4 * conf, 6)
            scored.append((score, mem))
        scored.sort(key=lambda x: (-x[0], x[1]))
        top = scored[:max(0, int(top_k))]
        refs = [mem for _, mem in top]
        scores = {mem: sc for sc, mem in top}
        seq = len([r for r in ledger.read_retrievals() if r.get("query_context") == query_context])
        rid = M.retrieval_id(query_context, seq)
        rec = RetrievalRecord(
            retrieval_id=rid, query_context=query_context, memory_refs=refs, scores=scores,
            is_recommendation=False, timestamp=now, input_hash=input_digest(query_context, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.retrieval_exists, ledger.retrievals_head, ledger.append_retrieval,
                         rid, rec, commit=commit)
        return RetrievalRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> EvolutionReportRecord:
        """진화 리포트(메모리·교훈·패턴·성공·실패·진화 집계). **is_binding=False, MEMORY DOES NOT DECIDE.**"""
        memories = ledger.memory_ids()
        states = {m: self.memory_state(m) for m in memories}
        cat_dist: dict = {}
        for m in memories:
            cat = self._memory_meta(m)["category"]
            cat_dist[cat] = cat_dist.get(cat, 0) + 1
        change_dist: dict = {}
        for e in ledger.read_evolution_events():
            change_dist[e.get("change_type")] = change_dist.get(e.get("change_type"), 0) + 1
        rid = M.report_id(scope, now)
        rec = EvolutionReportRecord(
            report_id=rid, scope=scope, memory_count=len(memories),
            active_memory_count=sum(1 for st in states.values() if st != M.M_ARCHIVED),
            archived_memory_count=sum(1 for st in states.values() if st == M.M_ARCHIVED),
            lesson_count=len(ledger.read_lessons()), pattern_count=len(ledger.read_patterns()),
            success_count=len(ledger.read_successes()), failure_count=len(ledger.read_failures()),
            evolution_event_count=len(ledger.read_evolution_events()),
            retrieval_count=len(ledger.read_retrievals()),
            category_distribution=dict(sorted(cat_dist.items())),
            change_distribution=dict(sorted(change_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return EvolutionReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_memory_intelligence.verify import verify_chain
        return verify_chain()

    def list_memories(self) -> list:
        return ledger.memory_ids()

    def memories_in_state(self, state) -> list:
        return sorted(m for m in ledger.memory_ids() if self.memory_state(m) == state)

    def summary(self, now="") -> MemoryIntelligenceSummary:
        return MemoryIntelligenceSummary(
            timestamp=now, memory_event_count=len(ledger.read_memory_events()),
            memory_count=len(ledger.memory_ids()), lesson_count=len(ledger.read_lessons()),
            pattern_count=len(ledger.read_patterns()), success_count=len(ledger.read_successes()),
            failure_count=len(ledger.read_failures()),
            evolution_event_count=len(ledger.read_evolution_events()),
            retrieval_count=len(ledger.read_retrievals()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
