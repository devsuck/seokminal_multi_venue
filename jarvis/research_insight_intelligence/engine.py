"""Research Insight Engine (P28) — 연구 메모리를 통찰·해석·관계·공백으로 변환. **해석 지능 전용, 동작 없음.**

**전략 선택·가설 승인·모델 배포·실험 실행·거래·자본 배분을 하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. INSIGHT ≠ DECISION · INSIGHT ≠ RECOMMENDATION · INSIGHT ≠ STRATEGY.
결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_insight_intelligence import ledger
from jarvis.research_insight_intelligence import models as M
from jarvis.research_insight_intelligence.models import (
    GENESIS,
    ArtifactRecord,
    ContextRecord,
    EvidenceLinkRecord,
    IllegalInsightTransition,
    InsightEventRecord,
    InsightSummary,
    InterpretationRecord,
    InterpretationReportRecord,
    RelationshipRecord,
    ResearchGapRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Insight Intelligence & Interpretation 데이터 — INSIGHT ≠ DECISION · INSIGHT ≠ "
               "RECOMMENDATION · INSIGHT ≠ STRATEGY. 연구 통찰·맥락·증거 해석·연구 공백·관계 기록 전용 — 전략 선택·가설 "
               "승인·모델 배포·실험 실행·거래·자본 배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchInsightEngine:
    """연구 통찰·해석 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/거래/배포/승인/선택 권한 없음."""

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

    # ══════════════ create_context ══════════════
    def create_context(self, domain, references=None, description="", now="",
                       *, commit=False) -> ContextRecord:
        """연구 맥락 생성(불변). **맥락 구축만.**"""
        cid = M.context_id(domain, description)
        existing = next((c for c in ledger.read_contexts() if c.get("context_id") == cid), None)
        if existing:
            return ContextRecord(**{k: v for k, v in existing.items()
                                    if k in ContextRecord.__dataclass_fields__})
        rec = ContextRecord(context_id=cid, domain=domain, references=list(references or []),
                            description=description, created_at=now,
                            input_hash=input_digest(domain, description),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.context_exists, ledger.contexts_head, ledger.append_context, cid,
                         rec, commit=commit)
        self._artifact(M.ART_CONTEXT, cid, "", now, commit=commit)
        return ContextRecord(**rec)

    # ══════════════ 통찰 생애주기(event-sourced) ══════════════
    def _insight_event(self, ins, refs, category, statement, confidence, ctx, frm, to, note, now,
                       *, commit):
        seq = len(ledger.insight_events(ins))
        eid = M.insight_event_id(ins, to, seq)
        rec = InsightEventRecord(
            insight_event_id=eid, insight_id=ins, source_refs=list(refs), category=category,
            statement=statement, confidence=float(confidence), context_id=ctx, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(ins, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.insight_event_exists, ledger.insights_head,
                         ledger.append_insight_event, eid, rec, commit=commit)
        return InsightEventRecord(**rec)

    def insight_state(self, ins) -> str | None:
        evs = ledger.insight_events(ins)
        return evs[-1].get("to_state") if evs else None

    def _insight_meta(self, ins) -> dict:
        evs = ledger.insight_events(ins)
        if not evs:
            raise UnknownEntityError(f"미등록 통찰 {ins}")
        g = evs[0]
        return {"source_refs": g.get("source_refs", []), "category": g.get("category"),
                "statement": g.get("statement"), "confidence": g.get("confidence"),
                "context_id": g.get("context_id"), "state": evs[-1].get("to_state")}

    def _insight_transition(self, ins, to, note, now, *, commit):
        m = self._insight_meta(ins)
        frm = m["state"]
        if not M.can_insight_transition(frm, to):
            raise IllegalInsightTransition(f"통찰 {ins} {frm}→{to} 불가")
        return self._insight_event(ins, m["source_refs"], m["category"], m["statement"],
                                   m["confidence"], m["context_id"], frm, to, note, now,
                                   commit=commit)

    def extract_insight(self, source_refs, category, statement, confidence=0.5, context_id="",
                        now="", *, commit=False) -> InsightEventRecord:
        """통찰 추출(genesis CREATED, 이벤트 소싱). **이해·설명만 — 결정/추천/전략 아님.**"""
        if category not in M.INSIGHT_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        ins = M.insight_id(category, statement)
        evs = ledger.insight_events(ins)
        if evs:
            return InsightEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in InsightEventRecord.__dataclass_fields__})
        ev = self._insight_event(ins, source_refs or [], category, statement, M.clamp01(confidence),
                                 context_id, GENESIS, M.I_CREATED, "created", now, commit=commit)
        parent = M.artifact_id(M.ART_CONTEXT, context_id) if context_id else ""
        # context 아티팩트가 없으면 부모 없이(무결성 유지) — 존재할 때만 연결
        if context_id and not ledger.context_exists(context_id):
            parent = ""
        self._artifact(M.ART_INSIGHT, ins, parent, now, commit=commit)
        return ev

    def support_insight(self, ins, note="supported", now="", *, commit=False):
        return self._insight_transition(ins, M.I_SUPPORTED, note, now, commit=commit)

    def review_insight(self, ins, note="reviewed", now="", *, commit=False):
        return self._insight_transition(ins, M.I_REVIEWED, note, now, commit=commit)

    def archive_insight(self, ins, note="archived", now="", *, commit=False):
        return self._insight_transition(ins, M.I_ARCHIVED, note, now, commit=commit)

    # ══════════════ interpret_evidence (증거 해석 + 증거 연결) ══════════════
    def _link_evidence(self, ins, evidence_ref, evidence_type, source_layer, now, *, commit):
        seq = len(ledger.evidence_for(ins))
        lid = M.evidence_link_id(ins, evidence_ref, seq)
        rec = EvidenceLinkRecord(
            evidence_link_id=lid, insight_id=ins, evidence_ref=evidence_ref,
            evidence_type=evidence_type, source_layer=source_layer, created_at=now,
            input_hash=input_digest(ins, evidence_ref, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.evidence_link_exists, ledger.evidence_links_head,
                         ledger.append_evidence_link, lid, rec, commit=commit)
        return EvidenceLinkRecord(**rec)

    def interpret_evidence(self, ins, explanation, supporting_refs=None, conflicting_refs=None,
                           source_layer="", now="", *, commit=False) -> InterpretationRecord:
        """증거 해석(불변): 지지/상충 증거·역사적 빈도·검증 품질 분석 → 해석 기록 + 증거 연결. 통찰 SUPPORTED 전이.

        **해석·설명만 — 결정/추천 없음.**
        """
        self._insight_meta(ins)  # 존재 검증
        sup = list(supporting_refs or [])
        con = list(conflicting_refs or [])
        for ref in sup:
            self._link_evidence(ins, ref, "SUPPORTING", source_layer, now, commit=commit)
        for ref in con:
            self._link_evidence(ins, ref, "CONFLICTING", source_layer, now, commit=commit)
        conf = M.interpret_confidence(len(sup), len(con))
        seq = len(ledger.interpretations_for(ins))
        iid = M.interpretation_id(ins, seq)
        rec = InterpretationRecord(
            interpretation_id=iid, insight_id=ins, evidence={"supporting": sup, "conflicting": con},
            explanation=explanation, supporting_count=len(sup), conflicting_count=len(con),
            confidence=conf, created_at=now, input_hash=input_digest(ins, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.interpretation_exists, ledger.interpretations_head,
                         ledger.append_interpretation, iid, rec, commit=commit)
        self._artifact(M.ART_INTERPRETATION, iid, M.artifact_id(M.ART_INSIGHT, ins), now,
                       commit=commit)
        if self.insight_state(ins) == M.I_CREATED:
            self._insight_transition(ins, M.I_SUPPORTED, "evidence interpreted", now, commit=commit)
        return InterpretationRecord(**rec)

    # ══════════════ detect_gap (연구 공백 탐지) ══════════════
    def detect_gap(self, gap_type, description, missing_information="", related_insights=None,
                   now="", *, commit=False) -> ResearchGapRecord:
        """연구 공백 탐지·기록(불변): 검증 부족·표본 부족·상충 결과·미탐색 영역. **탐지·기록만.**"""
        if gap_type not in M.GAP_TYPES:
            raise ValueError(f"미지원 gap_type {gap_type}")
        gid = M.gap_id(gap_type, description)
        rec = ResearchGapRecord(
            gap_id=gid, gap_type=gap_type, description=description,
            missing_information=missing_information, related_insights=list(related_insights or []),
            created_at=now, input_hash=input_digest(gap_type, description),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.gap_exists, ledger.gaps_head, ledger.append_gap, gid, rec,
                         commit=commit)
        self._artifact(M.ART_GAP, gid, "", now, commit=commit)
        return ResearchGapRecord(**rec)

    # ══════════════ connect_insights (관계 매핑 + 생애주기) ══════════════
    def connect_insights(self, source, target, relation_type, now="",
                         *, commit=False) -> RelationshipRecord:
        """두 통찰 연결(관계 기록 + CONNECTED 전이). **관계·계보만.**"""
        self._insight_meta(source)
        self._insight_meta(target)  # 양쪽 존재 검증
        if relation_type not in M.RELATION_TYPES:
            raise ValueError(f"미지원 relation_type {relation_type}")
        rid = M.relationship_id(source, target, relation_type)
        rec = RelationshipRecord(relationship_id=rid, source=source, target=target,
                                 relation_type=relation_type, created_at=now,
                                 input_hash=input_digest(source, target, relation_type),
                                 previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.relationship_exists, ledger.relationships_head,
                         ledger.append_relationship, rid, rec, commit=commit)
        self._artifact(M.ART_RELATIONSHIP, rid, M.artifact_id(M.ART_INSIGHT, source), now,
                       commit=commit)
        if self.insight_state(source) == M.I_SUPPORTED:
            self._insight_transition(source, M.I_CONNECTED, "connected", now, commit=commit)
        return RelationshipRecord(**rec)

    # ══════════════ summarize (결정적 지식 요약) ══════════════
    def summarize(self, scope="SYSTEM") -> dict:
        """지식 요약(결정적 집계, READ ONLY). 통찰 범주·상태·공백 유형·관계 유형 분포. **요약만 — 결정 없음.**"""
        insights = ledger.insight_ids()
        cat: dict = {}
        state: dict = {}
        for ins in insights:
            m = self._insight_meta(ins)
            cat[m["category"]] = cat.get(m["category"], 0) + 1
            st = self.insight_state(ins)
            state[st] = state.get(st, 0) + 1
        gap: dict = {}
        for g in ledger.read_research_gaps():
            gap[g.get("gap_type")] = gap.get(g.get("gap_type"), 0) + 1
        rel: dict = {}
        for r in ledger.read_relationships():
            rel[r.get("relation_type")] = rel.get(r.get("relation_type"), 0) + 1
        return {"scope": scope, "insight_count": len(insights),
                "category_distribution": dict(sorted(cat.items())),
                "state_distribution": dict(sorted(state.items())),
                "gap_distribution": dict(sorted(gap.items())),
                "relation_distribution": dict(sorted(rel.items()))}

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> InterpretationReportRecord:
        """해석 리포트(통찰·맥락·해석·증거·공백·관계 집계 + 지식 요약). **is_binding=False, INSIGHT ≠ DECISION.**"""
        summary = self.summarize(scope)
        insights = ledger.insight_ids()
        states = {i: self.insight_state(i) for i in insights}
        rid = M.report_id(scope, now)
        rec = InterpretationReportRecord(
            report_id=rid, scope=scope, insight_count=len(insights),
            active_insight_count=sum(1 for st in states.values() if st != M.I_ARCHIVED),
            reviewed_insight_count=sum(1 for st in states.values()
                                       if st in (M.I_REVIEWED, M.I_ARCHIVED)),
            context_count=len(ledger.read_contexts()),
            interpretation_count=len(ledger.read_interpretations()),
            evidence_link_count=len(ledger.read_evidence_links()),
            gap_count=len(ledger.read_research_gaps()),
            relationship_count=len(ledger.read_relationships()),
            category_distribution=summary["category_distribution"],
            relation_distribution=summary["relation_distribution"],
            gap_distribution=summary["gap_distribution"], summary=summary, is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return InterpretationReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_insight_intelligence.verify import verify_chain
        return verify_chain()

    def list_insights(self) -> list:
        return ledger.insight_ids()

    def insights_in_state(self, state) -> list:
        return sorted(i for i in ledger.insight_ids() if self.insight_state(i) == state)

    def summary(self, now="") -> InsightSummary:
        return InsightSummary(
            timestamp=now, insight_event_count=len(ledger.read_insight_events()),
            insight_count=len(ledger.insight_ids()), context_count=len(ledger.read_contexts()),
            interpretation_count=len(ledger.read_interpretations()),
            evidence_link_count=len(ledger.read_evidence_links()),
            gap_count=len(ledger.read_research_gaps()),
            relationship_count=len(ledger.read_relationships()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
