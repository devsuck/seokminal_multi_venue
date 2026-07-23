"""Research Evolution Governance Engine (P10.16) — 연구 결과를 학습 기록으로 전환. **저장·분석·기록 전용.**

P9.8~P10.15 연구 이력을 READ ONLY 로 소비해 연구 객체 등록·실패 패턴 분석·개선 제안·이터레이션 기록·학습
기록·지식 이전·진화 사이클을 남긴다. **strategy/signal/model/parameter 수정 없음·배포 없음·실행 트리거
없음·자본 배분 없음.** execution/broker/order/portfolio execution/capital allocation/live trading/
permission/risk controller import·호출 없음. LEARNING ≠ MODIFICATION · PROPOSAL ≠ APPROVAL · ACCEPTED ≠
DEPLOYMENT · IMPLEMENTED(record) ≠ PRODUCTION CHANGE. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_evolution import ledger
from jarvis.research_evolution.models import (
    ACCEPTED,
    ANALYZED,
    ARCHIVED,
    ART_CYCLE,
    ART_FAILURE,
    ART_ITERATION,
    ART_LEARNING,
    ART_OBJECT,
    ART_PROPOSAL,
    ART_REPORT,
    ART_TRANSFER,
    CREATED,
    DRAFT,
    EDGE_TYPES,
    FAILURE_CATEGORIES,
    GENESIS,
    IMPLEMENTED,
    LEARNING_CAPTURED,
    NODE_TYPES,
    REVIEWING,
    EvolutionArtifact,
    EvolutionCycleEvent,
    EvolutionReport,
    EvolutionSummary,
    FailurePattern,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableLearningError,
    ImmutableResearchObjectError,
    ImmutableTransferError,
    ImprovementProposalEvent,
    InvalidFailureCategory,
    InvalidLineageLink,
    IterationRecord,
    KnowledgeTransferRecord,
    LearningRecord,
    UnknownCycle,
    UnknownProposal,
    UnknownResearchObject,
    artifact_id as _artifact_id,
    can_transition_cycle,
    can_transition_proposal,
    content_hash,
    cycle_event_id,
    cycle_id as _cycle_id,
    detect_cycle,
    failure_id as _failure_id,
    input_digest,
    iteration_id as _iteration_id,
    learning_confidence,
    learning_id as _learning_id,
    learning_score,
    metadata_hash as _metadata_hash,
    proposal_event_id,
    proposal_id as _proposal_id,
    report_id as _report_id,
    research_object_id as _research_object_id,
    transfer_id as _transfer_id,
)

_DISCLAIMER = ("연구 진화 학습 데이터 — LEARNING ≠ MODIFICATION · PROPOSAL ≠ APPROVAL · ACCEPTED ≠ "
               "DEPLOYMENT · IMPLEMENTED(record) ≠ PRODUCTION CHANGE. 실행/거래/배포/수정/배분 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchEvolutionEngine:
    """연구 진화 거버넌스 엔진. 불변·append-only·결정적. 실행/거래/배포/수정/배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = EvolutionArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Research Object (불변) ──
    def register_research_object(self, source_layer: str, source_reference: str,
                                 research_type: str, metadata: dict | None = None, now: str = "",
                                 *, commit: bool = False) -> ResearchObject:  # noqa: F821
        """이전 연구 산출물을 학습 대상 객체로 등록. **읽기·기록만 — 원본 수정 없음.**"""
        oid = _research_object_id(source_layer, source_reference)
        mh = _metadata_hash({"research_type": research_type, "metadata": dict(metadata or {})})
        existing = ledger.get_research_object(oid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutableResearchObjectError(f"{oid} 연구 객체 불변 — 변경 불가")
            from jarvis.research_evolution.models import ResearchObject as _RO
            return _RO(**{k: v for k, v in existing.items()
                          if k in _RO.__dataclass_fields__})
        from jarvis.research_evolution.models import ResearchObject as _RO
        rec = _RO(
            object_id=oid, source_layer=source_layer, source_reference=source_reference,
            research_type=research_type, metadata_hash=mh, created_at=now,
            input_hash=input_digest(source_layer, source_reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.research_object_exists(oid):
            head = ledger.research_objects_head()
            ledger.append_research_object(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_OBJECT, oid, "", now, commit=commit)
        return _RO(**rec)

    # ── Failure Pattern (불변) ──
    def record_failure(self, category: str, pattern: str, severity: str = "MEDIUM",
                       evidence: list | None = None, related_objects: list | None = None,
                       frequency: int = 1, now: str = "", *,
                       commit: bool = False) -> FailurePattern:
        """실패 패턴을 불변 기록. category 는 정의된 범주만 허용. **분석·기록만.**"""
        if category not in FAILURE_CATEGORIES:
            raise InvalidFailureCategory(f"미등록 실패 범주 {category}")
        fid = _failure_id(category, pattern)
        mh = _metadata_hash({"severity": severity, "evidence": list(evidence or []),
                             "related_objects": list(related_objects or []),
                             "frequency": int(frequency)})
        existing = ledger.get_failure(fid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutableFailureError(f"{fid} 실패 패턴 불변 — 변경 불가")
            return FailurePattern(**{k: v for k, v in existing.items()
                                     if k in FailurePattern.__dataclass_fields__})
        rec = FailurePattern(
            failure_id=fid, category=category, pattern=pattern, severity=severity,
            evidence=list(evidence or []), related_objects=list(related_objects or []),
            frequency=int(frequency), metadata_hash=mh, created_at=now,
            input_hash=input_digest(category, pattern), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.failure_exists(fid):
            head = ledger.failures_head()
            ledger.append_failure(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for ref in list(related_objects or []):
            cand = _artifact_id(ART_OBJECT, ref)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_FAILURE, fid, parent, now, commit=commit)
        return FailurePattern(**rec)

    # ── Evolution Cycle (이벤트 소싱) ──
    def cycle_state(self, cycle_id: str) -> str:
        evs = ledger.cycle_events_for(cycle_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _cycle_meta(self, cycle_id: str) -> dict | None:
        evs = ledger.cycle_events_for(cycle_id)
        return evs[0] if evs else None

    def _emit_cycle_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_cycle(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(cycle)")
        cid = meta["cycle_id"]
        eid = cycle_event_id(cid, frm, to)
        rec = EvolutionCycleEvent(
            event_id=eid, cycle_id=cid, name=meta["name"], source_objects=meta["source_objects"],
            observations=meta["observations"], lessons=meta["lessons"],
            future_questions=meta["future_questions"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(cid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.cycle_event_exists(eid):
            head = ledger.cycles_head()
            ledger.append_cycle_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_evolution_cycle(self, name: str, source_objects: list | None = None,
                               observations: list | None = None, lessons: list | None = None,
                               future_questions: list | None = None, now: str = "",
                               *, commit: bool = False) -> EvolutionCycleEvent:
        """이전 연구 결과들을 하나의 진화 사이클로 묶어 관찰·교훈·후속질문을 기록(CREATED)."""
        cid = _cycle_id(name)
        existing = ledger.cycle_events_for(cid)
        if existing:
            return EvolutionCycleEvent(**existing[-1])
        meta = {"cycle_id": cid, "name": name, "source_objects": list(source_objects or []),
                "observations": list(observations or []), "lessons": list(lessons or []),
                "future_questions": list(future_questions or [])}
        rec = self._emit_cycle_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_CYCLE, cid, "", now, commit=commit)
        return EvolutionCycleEvent(**rec)

    def transition_cycle(self, cycle_id: str, to: str, now: str = "", *,
                         commit: bool = False) -> dict:
        meta = self._cycle_meta(cycle_id)
        if meta is None:
            raise UnknownCycle(f"미존재 진화 사이클 {cycle_id}")
        return self._emit_cycle_event(meta, self.cycle_state(cycle_id), to, now, commit=commit)

    def advance_cycle(self, cycle_id: str, now: str = "", *, commit: bool = False) -> dict:
        """CREATED→ANALYZED→LEARNING_CAPTURED 로 한 단계 진행(정보용 상태만)."""
        meta = self._cycle_meta(cycle_id)
        if meta is None:
            raise UnknownCycle(f"미존재 진화 사이클 {cycle_id}")
        cur = self.cycle_state(cycle_id)
        nxt = {CREATED: ANALYZED, ANALYZED: LEARNING_CAPTURED, LEARNING_CAPTURED: ARCHIVED}.get(cur)
        if nxt:
            self._emit_cycle_event(meta, cur, nxt, now, commit=commit)
        return {"cycle_id": cycle_id, "state": self.cycle_state(cycle_id)}

    # ── Iteration ──
    def record_iteration(self, cycle_ref: str, iteration_number: int, changes: list | None = None,
                         outcome: str = "INCONCLUSIVE", notes: str = "", now: str = "",
                         *, commit: bool = False) -> IterationRecord:
        """사이클 내 한 이터레이션의 변경·결과를 기록. **연구 시도 서술 — 실행 아님.**"""
        iid = _iteration_id(cycle_ref, iteration_number)
        rec = IterationRecord(
            iteration_id=iid, cycle_ref=cycle_ref, iteration_number=int(iteration_number),
            changes=list(changes or []), outcome=outcome, notes=notes, created_at=now,
            input_hash=input_digest(cycle_ref, int(iteration_number)),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.iteration_exists(iid):
            head = ledger.iterations_head()
            ledger.append_iteration(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CYCLE, cycle_ref) if ledger.artifact_exists(
            _artifact_id(ART_CYCLE, cycle_ref)) else ""
        self._record_artifact(ART_ITERATION, iid, parent, now, commit=commit)
        return IterationRecord(**rec)

    # ── Improvement Proposal (이벤트 소싱) ──
    def proposal_state(self, proposal_id: str) -> str:
        evs = ledger.proposal_events_for(proposal_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _proposal_meta(self, proposal_id: str) -> dict | None:
        evs = ledger.proposal_events_for(proposal_id)
        return evs[0] if evs else None

    def _emit_proposal_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition_proposal(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(proposal)")
        pid = meta["proposal_id"]
        eid = proposal_event_id(pid, frm, to)
        rec = ImprovementProposalEvent(
            event_id=eid, proposal_id=pid, source_failure=meta["source_failure"],
            hypothesis=meta["hypothesis"], expected_improvement=meta["expected_improvement"],
            evidence=meta["evidence"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(pid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.proposal_event_exists(eid):
            head = ledger.proposals_head()
            ledger.append_proposal_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_improvement_proposal(self, source_failure: str, hypothesis: str,
                                    expected_improvement: str = "", evidence: list | None = None,
                                    now: str = "", *,
                                    commit: bool = False) -> ImprovementProposalEvent:
        """실패로부터 개선 가설을 제안(DRAFT). **PROPOSAL ≠ APPROVAL — 자동 적용/배포 없음.**"""
        pid = _proposal_id(source_failure, hypothesis)
        existing = ledger.proposal_events_for(pid)
        if existing:
            return ImprovementProposalEvent(**existing[-1])
        meta = {"proposal_id": pid, "source_failure": source_failure, "hypothesis": hypothesis,
                "expected_improvement": expected_improvement, "evidence": list(evidence or [])}
        rec = self._emit_proposal_event(meta, "", DRAFT, now, commit=commit)
        parent = _artifact_id(ART_FAILURE, source_failure) if ledger.artifact_exists(
            _artifact_id(ART_FAILURE, source_failure)) else ""
        self._record_artifact(ART_PROPOSAL, pid, parent, now, commit=commit)
        return ImprovementProposalEvent(**rec)

    def transition_proposal(self, proposal_id: str, to: str, now: str = "", *,
                            commit: bool = False) -> dict:
        meta = self._proposal_meta(proposal_id)
        if meta is None:
            raise UnknownProposal(f"미존재 개선 제안 {proposal_id}")
        return self._emit_proposal_event(meta, self.proposal_state(proposal_id), to, now,
                                         commit=commit)

    def accept_proposal(self, proposal_id: str, now: str = "", *, commit: bool = False) -> dict:
        """DRAFT→REVIEWING→ACCEPTED. **ACCEPTED ≠ DEPLOYMENT — 사람 인지일 뿐 자동 변경 없음.**"""
        meta = self._proposal_meta(proposal_id)
        if meta is None:
            raise UnknownProposal(f"미존재 개선 제안 {proposal_id}")
        cur = self.proposal_state(proposal_id)
        if cur == DRAFT:
            self._emit_proposal_event(meta, DRAFT, REVIEWING, now, commit=commit)
        self._emit_proposal_event(meta, REVIEWING, ACCEPTED, now, commit=commit)
        return {"proposal_id": proposal_id, "state": self.proposal_state(proposal_id)}

    def mark_proposal_implemented(self, proposal_id: str, now: str = "", *,
                                  commit: bool = False) -> dict:
        """ACCEPTED→IMPLEMENTED. **IMPLEMENTED 는 연구 상태 기록일 뿐 프로덕션 변경·배포가 아니다.**"""
        meta = self._proposal_meta(proposal_id)
        if meta is None:
            raise UnknownProposal(f"미존재 개선 제안 {proposal_id}")
        cur = self.proposal_state(proposal_id)
        if cur != ACCEPTED:
            raise IllegalTransition(f"{cur or 'GENESIS'} -> {IMPLEMENTED} 차단(proposal)")
        self._emit_proposal_event(meta, ACCEPTED, IMPLEMENTED, now, commit=commit)
        return {"proposal_id": proposal_id, "state": self.proposal_state(proposal_id),
                "note": "연구 상태 기록 — 프로덕션 변경/배포 아님"}

    # ── Learning Record (불변) ──
    def create_learning_record(self, source: str, lesson: str, confidence: float = 0.0,
                               applicability: str = "MODERATE", lineage: list | None = None,
                               now: str = "", *, commit: bool = False) -> LearningRecord:
        """무엇을 배웠는가를 불변 학습 기록으로 남긴다. **LEARNING ≠ MODIFICATION.**"""
        lid = _learning_id(source, lesson)
        existing = ledger.get_learning(lid)
        if existing is not None:
            if abs(float(existing.get("confidence", 0.0)) - round(float(confidence), 8)) > 1e-9 \
                    or existing.get("applicability") != applicability:
                raise ImmutableLearningError(f"{lid} 학습 기록 불변 — 변경 불가")
            return LearningRecord(**{k: v for k, v in existing.items()
                                     if k in LearningRecord.__dataclass_fields__})
        rec = LearningRecord(
            learning_id=lid, source=source, lesson=lesson, confidence=round(float(confidence), 8),
            applicability=applicability, lineage=list(lineage or []), created_at=now,
            input_hash=input_digest(source, lesson), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.learning_exists(lid):
            head = ledger.learning_head()
            ledger.append_learning(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for ref in [source] + list(lineage or []):
            for at in (ART_FAILURE, ART_OBJECT, ART_ITERATION):
                cand = _artifact_id(at, ref)
                if ledger.artifact_exists(cand):
                    parent = cand
                    break
            if parent:
                break
        self._record_artifact(ART_LEARNING, lid, parent, now, commit=commit)
        return LearningRecord(**rec)

    # ── Knowledge Transfer (불변) ──
    def create_transfer_record(self, from_context: str, to_context: str, knowledge: str,
                               applicability: str = "MODERATE",
                               supporting_learning: list | None = None, now: str = "",
                               *, commit: bool = False) -> KnowledgeTransferRecord:
        """한 연구 맥락의 교훈을 다른 맥락으로 이전 가능성 기록. **제안·기록만 — 자동 적용 없음.**"""
        tid = _transfer_id(from_context, to_context, knowledge)
        for t in ledger.read_transfers():
            if t.get("transfer_id") == tid:
                if t.get("applicability") != applicability:
                    raise ImmutableTransferError(f"{tid} 지식 이전 기록 불변 — 변경 불가")
                return KnowledgeTransferRecord(**{k: v for k, v in t.items()
                                                  if k in KnowledgeTransferRecord.__dataclass_fields__})
        rec = KnowledgeTransferRecord(
            transfer_id=tid, from_context=from_context, to_context=to_context, knowledge=knowledge,
            applicability=applicability, supporting_learning=list(supporting_learning or []),
            created_at=now, input_hash=input_digest(from_context, to_context, knowledge),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.transfer_exists(tid):
            head = ledger.transfers_head()
            ledger.append_transfer(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for ref in list(supporting_learning or []):
            cand = _artifact_id(ART_LEARNING, ref)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_TRANSFER, tid, parent, now, commit=commit)
        return KnowledgeTransferRecord(**rec)

    # ── Learning 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """학습 지표 → LEARNING_SCORE/CONFIDENCE. **LEARNING ≠ MODIFICATION — 거래 신호 아님.**"""
        return {"learning_score": learning_score(metrics),
                "learning_confidence": learning_confidence(metrics)}

    # ── 계보 검증(연구 진화 계보) ──
    def verify_lineage(self) -> dict:
        """연구 진화 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
        issues: list = []
        arts = ledger.read_artifacts()
        ids = {a.get("artifact_id") for a in arts}
        edges: list = []
        for a in arts:
            parent = a.get("parent_artifact")
            if parent:
                if parent not in ids:
                    issues.append(f"dangling:{a.get('artifact_id')}->{parent}")
                edges.append((a.get("artifact_id"), parent))
        cyc = detect_cycle(edges)
        if cyc:
            issues.append("lineage_cycle:" + "->".join(cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
        """artifact 의 상류 계보 조상(parent 체인)."""
        by_id = {a.get("artifact_id"): a for a in ledger.read_artifacts()}
        out: list = []
        seen: set = set()
        cur = by_id.get(artifact_ref)
        while cur:
            parent = cur.get("parent_artifact")
            if not parent or parent in seen:
                break
            seen.add(parent)
            out.append(parent)
            cur = by_id.get(parent)
        return out

    # ── Evolution Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                        *, commit: bool = False) -> EvolutionReport:
        m = dict(metrics or {})
        objs = ledger.read_research_objects()
        rt_dist: dict = {}
        for o in objs:
            rt_dist[o.get("research_type")] = rt_dist.get(o.get("research_type"), 0) + 1
        fails = ledger.read_failures()
        fc_dist: dict = {}
        for f in fails:
            fc_dist[f.get("category")] = fc_dist.get(f.get("category"), 0) + 1
        cycles = ledger.distinct_cycles()
        cstate: dict = {}
        for c in cycles:
            st = self.cycle_state(c.get("cycle_id"))
            cstate[st] = cstate.get(st, 0) + 1
        proposals = ledger.distinct_proposals()
        pstate: dict = {}
        for p in proposals:
            st = self.proposal_state(p.get("proposal_id"))
            pstate[st] = pstate.get(st, 0) + 1
        rid = _report_id(scope)
        rec = EvolutionReport(
            report_id=rid, scope=scope, object_count=len(objs),
            research_type_distribution=dict(sorted(rt_dist.items())), failure_count=len(fails),
            failure_category_distribution=dict(sorted(fc_dist.items())), cycle_count=len(cycles),
            cycle_state_distribution=dict(sorted(cstate.items())), proposal_count=len(proposals),
            proposal_state_distribution=dict(sorted(pstate.items())),
            learning_count=len(ledger.read_learning()),
            transfer_count=len(ledger.read_transfers()), metrics=m,
            learning_score=learning_score(m), learning_confidence=learning_confidence(m),
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return EvolutionReport(**rec)

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

    # ── Summary ──
    def summary(self, now: str = "") -> EvolutionSummary:
        objs = ledger.read_research_objects()
        rt_dist: dict = {}
        for o in objs:
            rt_dist[o.get("research_type")] = rt_dist.get(o.get("research_type"), 0) + 1
        fails = ledger.read_failures()
        fc_dist: dict = {}
        for f in fails:
            fc_dist[f.get("category")] = fc_dist.get(f.get("category"), 0) + 1
        cycles = ledger.distinct_cycles()
        cstate: dict = {}
        for c in cycles:
            st = self.cycle_state(c.get("cycle_id"))
            cstate[st] = cstate.get(st, 0) + 1
        proposals = ledger.distinct_proposals()
        pstate: dict = {}
        for p in proposals:
            st = self.proposal_state(p.get("proposal_id"))
            pstate[st] = pstate.get(st, 0) + 1
        return EvolutionSummary(
            timestamp=now, object_count=len(objs),
            research_type_distribution=dict(sorted(rt_dist.items())), failure_count=len(fails),
            failure_category_distribution=dict(sorted(fc_dist.items())), cycle_count=len(cycles),
            cycle_state_distribution=dict(sorted(cstate.items())), proposal_count=len(proposals),
            proposal_state_distribution=dict(sorted(pstate.items())),
            iteration_count=len(ledger.read_iterations()),
            learning_count=len(ledger.read_learning()),
            transfer_count=len(ledger.read_transfers()), report_count=len(ledger.read_reports()))
