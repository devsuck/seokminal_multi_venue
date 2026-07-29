"""Research Meta Intelligence Engine (P10.12) — 연구 과정 자체를 연구하는 메타 분석. **분석·기록 전용.**

P10.2~P10.11 연구 이력을 READ ONLY 로 소비해 패턴·방법·결과 이력·실패 패턴·연구 품질·메타 인사이트를
남긴다. **연구 이력 분석만 수행한다.** execution/broker/portfolio execution/live trading/permission/
capital allocation import·호출 없음. strategy 선택·model 승인·capital 결정·deploy 없음. META SCORE ≠
TRADING SCORE · RESEARCH QUALITY ≠ PERFORMANCE GUARANTEE · INSIGHT ≠ DECISION. 상위 파일은 읽기만.
결정적·append-only.
"""
from __future__ import annotations

from jarvis.meta_intelligence import ledger
from jarvis.meta_intelligence.models import (
    ANALYZED,
    ARCHIVED,
    ART_EDGE,
    ART_FAILURE,
    ART_INSIGHT,
    ART_OUTCOME,
    ART_PATTERN,
    ART_QUALITY,
    ART_REPORT,
    ART_SOURCE,
    CLASSIFIED,
    CONFIRMED,
    DISCOVERED,
    EDGE_TYPES,
    FAILED,
    GENERATED,
    GENESIS,
    NODE_TYPES,
    RECORDED,
    REVIEWED,
    SUCCESS,
    FailurePattern,
    IllegalTransition,
    ImmutableFailureError,
    ImmutableMethodError,
    ImmutablePatternError,
    InsightEvent,
    InvalidEvolutionLink,
    MetaArtifact,
    MetaReport,
    MetaSummary,
    OutcomeEvent,
    PatternEvent,
    ResearchMethod,
    ResearchQualityScore,
    UnknownInsight,
    UnknownOutcome,
    UnknownPattern,
    artifact_id as _artifact_id,
    can_transition_insight,
    can_transition_outcome,
    can_transition_pattern,
    compute_quality,
    content_hash,
    detect_cycle,
    edge_id as _edge_id,
    failure_id as _failure_id,
    input_digest,
    insight_event_id,
    insight_id as _insight_id,
    metadata_hash as _metadata_hash,
    meta_insight,
    meta_score,
    method_id as _method_id,
    outcome_event_id,
    outcome_id as _outcome_id,
    pattern_event_id,
    pattern_id as _pattern_id,
    quality_grade,
    quality_score_id as _quality_score_id,
    report_id as _report_id,
)

_DISCLAIMER = ("메타 연구 분석 — META SCORE ≠ TRADING SCORE · RESEARCH QUALITY ≠ PERFORMANCE "
               "GUARANTEE · INSIGHT ≠ DECISION. 전략 선택/배포/자본 결정 아님.")


def _ratio(num: float, den: float) -> float:
    if abs(den) < 1e-9:
        return 0.0
    return round(float(num) / float(den), 8)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchMetaEngine:
    """연구 메타 분석 엔진. 불변·append-only·결정적. 실행/거래/배포/선택/자본배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool, from_ref: str = "", to_ref: str = "",
                         edge_type: str = "") -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = MetaArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, from_ref=from_ref, to_ref=to_ref,
            edge_type=edge_type, created_at=now, input_hash=input_digest(artifact_type, ref_id),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Research Pattern (이벤트 소싱, 불변) ──
    def pattern_state(self, pattern_id: str) -> str:
        evs = ledger.pattern_events_for(pattern_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _pattern_meta(self, pattern_id: str) -> dict | None:
        evs = ledger.pattern_events_for(pattern_id)
        return evs[0] if evs else None

    def _emit_pattern_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_pattern(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(pattern)")
        pid = meta["pattern_id"]
        eid = pattern_event_id(pid, frm, to)
        rec = PatternEvent(
            event_id=eid, pattern_id=pid, category=meta["category"],
            description=meta["description"], frequency=meta["frequency"],
            source_references=meta["source_references"], confidence=meta["confidence"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(pid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_event_exists(eid):
            head = ledger.patterns_head()
            ledger.append_pattern_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_pattern(self, category: str, description: str, frequency: int = 1,
                         source_references: list | None = None, confidence: float = 0.0,
                         now: str = "", *, commit: bool = False) -> PatternEvent:
        pid = _pattern_id(category, description)
        existing = ledger.pattern_events_for(pid)
        if existing:
            first = existing[0]
            if first.get("frequency") != frequency or first.get("confidence") != round(
                    float(confidence), 8):
                raise ImmutablePatternError(f"{pid} 패턴 불변 — 변경 불가")
            return PatternEvent(**existing[-1])
        meta = {"pattern_id": pid, "category": category, "description": description,
                "frequency": int(frequency), "source_references": list(source_references or []),
                "confidence": round(float(confidence), 8)}
        rec = self._emit_pattern_event(meta, "", DISCOVERED, now, commit=commit)
        self._record_artifact(ART_PATTERN, pid, "", now, commit=commit)
        return PatternEvent(**rec)

    def transition_pattern(self, pattern_id: str, to: str, now: str = "", *,
                           commit: bool = False) -> dict:
        meta = self._pattern_meta(pattern_id)
        if meta is None:
            raise UnknownPattern(f"미존재 패턴 {pattern_id}")
        return self._emit_pattern_event(meta, self.pattern_state(pattern_id), to, now,
                                        commit=commit)

    # ── Research Method (불변) ──
    def register_method(self, name: str, version: str, category: str = "",
                        usage_count: int = 0, success_rate: float = 0.0,
                        metadata: dict | None = None, now: str = "",
                        *, commit: bool = False) -> ResearchMethod:
        mid = _method_id(name, version)
        mh = _metadata_hash(metadata or {})
        for m in ledger.read_methods():
            if m.get("method_id") == mid:
                if m.get("metadata_hash") != mh:
                    raise ImmutableMethodError(f"{mid} 방법 불변 — 변경 불가")
                return ResearchMethod(**{k: v for k, v in m.items()
                                         if k in ResearchMethod.__dataclass_fields__})
        rec = ResearchMethod(
            method_id=mid, name=name, version=version, category=category,
            usage_count=int(usage_count), success_rate=round(float(success_rate), 8),
            metadata_hash=mh, created_at=now, input_hash=input_digest(name, version),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.method_exists(mid):
            head = ledger.methods_head()
            ledger.append_method(_seal(rec, head["record_hash"] if head else GENESIS))
        return ResearchMethod(**rec)

    def method_effectiveness(self, method_id: str) -> dict:
        """방법 참조 결과로부터 사용·성공률 계산(READ 자기 원장). 이력 통계."""
        outs = [o for o in ledger.distinct_outcomes() if o.get("method_reference") == method_id]
        total = len(outs)
        ok = sum(1 for o in outs if o.get("result_type") == SUCCESS)
        return {"method_id": method_id, "usage_count": total, "success_rate": _ratio(ok, total)}

    # ── Research Outcome (이벤트 소싱) ──
    def outcome_state(self, outcome_id: str) -> str:
        evs = ledger.outcome_events_for(outcome_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _outcome_meta(self, outcome_id: str) -> dict | None:
        evs = ledger.outcome_events_for(outcome_id)
        return evs[0] if evs else None

    def _emit_outcome_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_outcome(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(outcome)")
        oid = meta["outcome_id"]
        eid = outcome_event_id(oid, frm, to)
        rec = OutcomeEvent(
            event_id=eid, outcome_id=oid, source_layer=meta["source_layer"],
            research_object=meta["research_object"], result_type=meta["result_type"],
            metrics=meta["metrics"], validation_reference=meta["validation_reference"],
            method_reference=meta["method_reference"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(oid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.outcome_event_exists(eid):
            head = ledger.outcomes_head()
            ledger.append_outcome_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def record_outcome(self, source_layer: str, research_object: str, result_type: str,
                       metrics: dict | None = None, validation_reference: str = "",
                       method_reference: str = "", now: str = "",
                       *, commit: bool = False) -> OutcomeEvent:
        """과거 연구 결과를 기록(RECORDED). **자동 판단 없음 — 이력일 뿐.**"""
        oid = _outcome_id(source_layer, research_object)
        existing = ledger.outcome_events_for(oid)
        if existing:
            return OutcomeEvent(**existing[-1])
        meta = {"outcome_id": oid, "source_layer": source_layer,
                "research_object": research_object, "result_type": result_type,
                "metrics": dict(metrics or {}), "validation_reference": validation_reference,
                "method_reference": method_reference}
        rec = self._emit_outcome_event(meta, "", RECORDED, now, commit=commit)
        self._record_artifact(ART_SOURCE, f"{source_layer}:{research_object}", "", now,
                              commit=commit)
        self._record_artifact(ART_OUTCOME, oid,
                              _artifact_id(ART_SOURCE, f"{source_layer}:{research_object}"), now,
                              commit=commit)
        return OutcomeEvent(**rec)

    def transition_outcome(self, outcome_id: str, to: str, now: str = "", *,
                           commit: bool = False) -> dict:
        meta = self._outcome_meta(outcome_id)
        if meta is None:
            raise UnknownOutcome(f"미존재 결과 {outcome_id}")
        return self._emit_outcome_event(meta, self.outcome_state(outcome_id), to, now,
                                        commit=commit)

    def classify_outcome(self, outcome_id: str, now: str = "", *, commit: bool = False) -> dict:
        """RECORDED→REVIEWED→CLASSIFIED 진행."""
        meta = self._outcome_meta(outcome_id)
        if meta is None:
            raise UnknownOutcome(f"미존재 결과 {outcome_id}")
        cur = self.outcome_state(outcome_id)
        if cur == RECORDED:
            self._emit_outcome_event(meta, RECORDED, REVIEWED, now, commit=commit)
        self._emit_outcome_event(meta, REVIEWED, CLASSIFIED, now, commit=commit)
        return {"outcome_id": outcome_id, "state": self.outcome_state(outcome_id)}

    # ── Failure Pattern (불변) ──
    def record_failure(self, category: str, occurrences: int = 1, examples: list | None = None,
                       confidence: float = 0.0, now: str = "",
                       *, commit: bool = False) -> FailurePattern:
        fid = _failure_id(category)
        mh = _metadata_hash({"examples": list(examples or []), "occurrences": int(occurrences)})
        for f in ledger.read_failures():
            if f.get("failure_id") == fid:
                if f.get("metadata_hash") != mh:
                    raise ImmutableFailureError(f"{fid} 실패 패턴 불변 — 변경 불가")
                return FailurePattern(**{k: v for k, v in f.items()
                                         if k in FailurePattern.__dataclass_fields__})
        rec = FailurePattern(
            failure_id=fid, category=category, occurrences=int(occurrences),
            examples=list(examples or []), confidence=round(float(confidence), 8),
            metadata_hash=mh, created_at=now, input_hash=input_digest(category),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.failure_exists(fid):
            head = ledger.failures_head()
            ledger.append_failure(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_FAILURE, fid, "", now, commit=commit)
        return FailurePattern(**rec)

    # ── Research Quality Score ──
    def calculate_quality(self, research_object: str, components: dict, now: str = "",
                          *, commit: bool = False) -> ResearchQualityScore:
        """연구 품질 점수(0~100) 계산·기록. **quality_score ≠ strategy ranking · ≠ performance.**"""
        overall = compute_quality(components)
        grade = quality_grade(overall)
        sid = _quality_score_id(research_object)
        rec = ResearchQualityScore(
            score_id=sid, research_object=research_object, components=dict(components),
            overall_score=overall, grade=grade, created_at=now,
            input_hash=input_digest(research_object), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.quality_score_exists(sid):
            head = ledger.quality_head()
            ledger.append_quality_score(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_QUALITY, sid,
                              _artifact_id(ART_OUTCOME, research_object)
                              if ledger.artifact_exists(_artifact_id(ART_OUTCOME,
                                                                     research_object)) else "",
                              now, commit=commit)
        return ResearchQualityScore(**rec)

    # ── Meta Insight (이벤트 소싱) ──
    def insight_state(self, insight_id: str) -> str:
        evs = ledger.insight_events_for(insight_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _insight_meta(self, insight_id: str) -> dict | None:
        evs = ledger.insight_events_for(insight_id)
        return evs[0] if evs else None

    def _emit_insight_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_insight(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(insight)")
        iid = meta["insight_id"]
        eid = insight_event_id(iid, frm, to)
        rec = InsightEvent(
            event_id=eid, insight_id=iid, topic=meta["topic"], statement=meta["statement"],
            metrics=meta["metrics"], meta_confidence=meta["meta_confidence"],
            evidence_references=meta["evidence_references"], from_state=frm, to_state=to,
            status=to, created_at=now, input_hash=input_digest(iid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.insight_event_exists(eid):
            head = ledger.insights_head()
            ledger.append_insight_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def generate_insight(self, topic: str, statement: str, metrics: dict | None = None,
                         evidence_references: list | None = None, now: str = "",
                         *, commit: bool = False) -> InsightEvent:
        """메타 인사이트 생성(GENERATED). meta_confidence 는 지표에서 파생. **자동 조치 없음.**"""
        m = dict(metrics or {})
        conf = meta_insight(m)
        iid = _insight_id(topic, statement)
        existing = ledger.insight_events_for(iid)
        if existing:
            return InsightEvent(**existing[-1])
        meta = {"insight_id": iid, "topic": topic, "statement": statement, "metrics": m,
                "meta_confidence": conf, "evidence_references": list(evidence_references or [])}
        rec = self._emit_insight_event(meta, "", GENERATED, now, commit=commit)
        self._record_artifact(ART_INSIGHT, iid, "", now, commit=commit)
        return InsightEvent(**rec)

    def transition_insight(self, insight_id: str, to: str, now: str = "", *,
                           commit: bool = False) -> dict:
        meta = self._insight_meta(insight_id)
        if meta is None:
            raise UnknownInsight(f"미존재 인사이트 {insight_id}")
        return self._emit_insight_event(meta, self.insight_state(insight_id), to, now,
                                        commit=commit)

    # ── Research Evolution Graph (진화 그래프 엣지) ──
    def record_evolution_edge(self, from_ref: str, from_type: str, to_ref: str, to_type: str,
                              edge_type: str, now: str = "", *, commit: bool = False) -> dict:
        """진화 그래프 엣지 기록. 노드 유형·엣지 유형 검증 + 순환 차단."""
        if from_type not in NODE_TYPES or to_type not in NODE_TYPES:
            raise InvalidEvolutionLink(f"미등록 노드 유형 {from_type}/{to_type}")
        if edge_type not in EDGE_TYPES:
            raise InvalidEvolutionLink(f"미등록 엣지 유형 {edge_type}")
        eid = _edge_id(from_ref, edge_type, to_ref)
        # 순환 차단(방향성 엣지).
        if not ledger.artifact_exists(_artifact_id(ART_EDGE, eid)):
            edges = [(a.get("from_ref"), a.get("to_ref")) for a in ledger.read_artifacts()
                     if a.get("artifact_type") == ART_EDGE]
            cyc = detect_cycle(edges + [(from_ref, to_ref)])
            if cyc:
                raise InvalidEvolutionLink("진화 그래프 순환 차단: " + "->".join(cyc))
        return self._record_artifact(ART_EDGE, eid, "", now, commit=commit, from_ref=from_ref,
                                     to_ref=to_ref, edge_type=edge_type)

    def evolution_cycle(self) -> list:
        edges = [(a.get("from_ref"), a.get("to_ref")) for a in ledger.read_artifacts()
                 if a.get("artifact_type") == ART_EDGE]
        return detect_cycle(edges)

    # ── analyze_research_history ──
    def analyze_research_history(self) -> dict:
        """연구 이력에서 메타 평가 지표 산출(결정적). READ 자기 원장."""
        outs = ledger.distinct_outcomes()
        total = len(outs)
        ok = sum(1 for o in outs if o.get("result_type") == SUCCESS)
        failed = sum(1 for o in outs if o.get("result_type") == FAILED)
        with_val = sum(1 for o in outs if o.get("validation_reference"))
        with_metrics = sum(1 for o in outs if o.get("metrics"))
        methods = ledger.read_methods()
        if methods:
            eff = sum(self.method_effectiveness(m.get("method_id"))["success_rate"]
                      for m in methods) / len(methods)
        else:
            eff = 0.0
        return {
            "research_reliability": _ratio(ok, total),
            "validation_consistency": _ratio(with_val, total),
            "failure_recurrence": _ratio(failed, total),
            "method_effectiveness": round(eff, 8),
            "evidence_completeness": _ratio(with_metrics, total),
        }

    def analyze(self) -> dict:
        """메타 지표 + META_INSIGHT 라벨."""
        metrics = self.analyze_research_history()
        return {"metrics": metrics, "meta_score": meta_score(metrics),
                "meta_insight": meta_insight(metrics)}

    # ── generate_meta_report ──
    def generate_meta_report(self, scope: str = "GLOBAL", now: str = "",
                             *, commit: bool = False) -> MetaReport:
        outs = ledger.distinct_outcomes()
        rdist: dict = {}
        for o in outs:
            rdist[o.get("result_type")] = rdist.get(o.get("result_type"), 0) + 1
        scores = ledger.read_quality_scores()
        mean_q = round(sum(s.get("overall_score", 0.0) for s in scores) / len(scores), 6) \
            if scores else 0.0
        insights = ledger.distinct_insights()
        cdist: dict = {}
        for i in insights:
            evs = ledger.insight_events_for(i.get("insight_id"))
            conf = evs[0].get("meta_confidence") if evs else ""
            cdist[conf] = cdist.get(conf, 0) + 1
        rid = _report_id(scope)
        rec = MetaReport(
            report_id=rid, scope=scope, outcome_count=len(outs),
            result_distribution=dict(sorted(rdist.items())),
            pattern_count=len(ledger.distinct_patterns()),
            failure_count=len(ledger.read_failures()), method_count=len(ledger.read_methods()),
            mean_quality=mean_q, insight_count=len(insights),
            meta_confidence_distribution=dict(sorted(cdist.items())), disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return MetaReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_objects(self, layer: str, limit: int = 0) -> list:
        spec = ledger.SOURCE_LEDGERS.get(layer)
        if not spec:
            return []
        filename, id_field = spec
        out: list = []
        for r in ledger.read_source(filename):
            ref = r.get(id_field)
            if ref:
                out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Summary ──
    def summary(self, now: str = "") -> MetaSummary:
        patterns = ledger.distinct_patterns()
        pstate: dict = {}
        for p in patterns:
            pstate[self.pattern_state(p.get("pattern_id"))] = pstate.get(
                self.pattern_state(p.get("pattern_id")), 0) + 1
        outs = ledger.distinct_outcomes()
        ostate: dict = {}
        rdist: dict = {}
        for o in outs:
            st = self.outcome_state(o.get("outcome_id"))
            ostate[st] = ostate.get(st, 0) + 1
            rdist[o.get("result_type")] = rdist.get(o.get("result_type"), 0) + 1
        scores = ledger.read_quality_scores()
        mean_q = round(sum(s.get("overall_score", 0.0) for s in scores) / len(scores), 6) \
            if scores else 0.0
        insights = ledger.distinct_insights()
        cdist: dict = {}
        for i in insights:
            evs = ledger.insight_events_for(i.get("insight_id"))
            conf = evs[0].get("meta_confidence") if evs else ""
            cdist[conf] = cdist.get(conf, 0) + 1
        return MetaSummary(
            timestamp=now, pattern_count=len(patterns),
            pattern_state_distribution=dict(sorted(pstate.items())),
            method_count=len(ledger.read_methods()), outcome_count=len(outs),
            outcome_state_distribution=dict(sorted(ostate.items())),
            result_distribution=dict(sorted(rdist.items())),
            failure_count=len(ledger.read_failures()), quality_score_count=len(scores),
            mean_quality=mean_q, insight_count=len(insights),
            insight_confidence_distribution=dict(sorted(cdist.items())),
            report_count=len(ledger.read_reports()))
