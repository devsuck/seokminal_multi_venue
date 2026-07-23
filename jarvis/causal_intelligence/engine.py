"""Research Causal Intelligence Engine (P10.11) — 연구 객체 간 인과 관계 분석. **연구 증거·기록 전용.**

P10.2~P10.8 연구 계층을 READ ONLY 로 소비해 변수·가설·관계연구·실험·증거·인과 그래프·리포트를 남긴다.
**모든 산출은 연구 증거일 뿐이다.** execution/broker/portfolio execution/risk governor/permission
manager/live trading import·호출 없음. trading 실행·signal 생성·portfolio 배분·model 배포·자동 전략
선택·자본 영향 없음. VALIDATED ≠ CAUSALITY PROVEN · CAUSAL SCORE ≠ TRADING PERMISSION ·
RELATIONSHIP ≠ ACTION. 상위 레이어 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.causal_intelligence import ledger
from jarvis.causal_intelligence.models import (
    ANALYZED,
    ARCHIVED,
    ART_EVIDENCE,
    ART_EXPERIMENT,
    ART_GRAPH,
    ART_HYPOTHESIS,
    ART_REPORT,
    ART_SOURCE,
    ART_VARIABLE,
    COMPLETED,
    CONNECTED,
    CREATED,
    DIRECTED_EDGES,
    DRAFT,
    EDGE_TYPES,
    EVIDENCED,
    GENESIS,
    NODE_VARIABLE,
    REGISTERED,
    RUNNING,
    SNAPSHOTTED,
    TESTING,
    CausalArtifact,
    CausalCycleError,
    CausalReport,
    CausalSummary,
    Evidence,
    ExperimentEvent,
    GraphEvent,
    HypothesisEvent,
    IllegalTransition,
    ImmutableHypothesisError,
    ImmutableVariableError,
    RelationshipStudy,
    UnknownExperiment,
    UnknownHypothesis,
    UnknownVariable,
    Variable,
    artifact_id as _artifact_id,
    can_transition_experiment,
    can_transition_graph,
    can_transition_hypothesis,
    causal_score,
    causal_support,
    content_hash,
    detect_cycle,
    evidence_id as _evidence_id,
    experiment_event_id,
    experiment_id as _experiment_id,
    graph_event_id,
    graph_hash as _graph_hash,
    graph_id as _graph_id,
    hypothesis_event_id,
    hypothesis_id as _hypothesis_id,
    input_digest,
    metadata_hash as _metadata_hash,
    report_id as _report_id,
    study_id as _study_id,
    variable_id as _variable_id,
)

_DISCLAIMER = ("연구 증거 — VALIDATED ≠ CAUSALITY PROVEN · CAUSAL SCORE ≠ TRADING PERMISSION · "
               "RELATIONSHIP ≠ ACTION. BUY/SELL/DEPLOY/ENABLE/ALLOCATE 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchCausalEngine:
    """연구 인과 분석 엔진. 불변·append-only·결정적. 실행/거래/배포/선택/자본배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = CausalArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Variable Registry (불변) ──
    def register_variable(self, name: str, var_type: str, source_reference: str = "",
                          node_type: str = NODE_VARIABLE, metadata: dict | None = None,
                          now: str = "", *, commit: bool = False) -> Variable:
        vid = _variable_id(name, var_type, source_reference)
        mh = _metadata_hash(metadata or {})
        for v in ledger.read_variables():
            if v.get("variable_id") == vid:
                if v.get("metadata_hash") != mh:
                    raise ImmutableVariableError(f"{vid} 변수 불변 — 변경 불가")
                return Variable(**{k: val for k, val in v.items()
                                   if k in Variable.__dataclass_fields__})
        rec = Variable(
            variable_id=vid, name=name, var_type=var_type, source_reference=source_reference,
            node_type=node_type, metadata_hash=mh, created_at=now,
            input_hash=input_digest(name, var_type, source_reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.variable_exists(vid):
            head = ledger.variables_head()
            ledger.append_variable(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_SOURCE, source_reference or f"var:{vid}", "", now, commit=commit)
        self._record_artifact(ART_VARIABLE, vid,
                              _artifact_id(ART_SOURCE, source_reference or f"var:{vid}"), now,
                              commit=commit)
        return Variable(**rec)

    def _variable_type(self, variable_id: str) -> str | None:
        for v in ledger.read_variables():
            if v.get("variable_id") == variable_id:
                return v.get("node_type")
        return None

    # ── Causal Hypothesis (이벤트 소싱, 불변) ──
    def hypothesis_state(self, hypothesis_id: str) -> str:
        evs = ledger.hypothesis_events_for(hypothesis_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _hypothesis_meta(self, hypothesis_id: str) -> dict | None:
        evs = ledger.hypothesis_events_for(hypothesis_id)
        return evs[0] if evs else None

    def _emit_hypothesis_event(self, meta: dict, frm: str, to: str, now: str,
                               *, commit: bool) -> dict:
        if not can_transition_hypothesis(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(hypothesis)")
        hid = meta["hypothesis_id"]
        eid = hypothesis_event_id(hid, frm, to)
        rec = HypothesisEvent(
            event_id=eid, hypothesis_id=hid, cause_variable=meta["cause_variable"],
            effect_variable=meta["effect_variable"], statement=meta["statement"],
            mechanism=meta["mechanism"], confidence=meta["confidence"], from_state=frm,
            to_state=to, status=to, created_at=now, input_hash=input_digest(hid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.hypothesis_event_exists(eid):
            head = ledger.hypotheses_head()
            ledger.append_hypothesis_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_hypothesis(self, cause_variable: str, effect_variable: str, statement: str,
                          mechanism: str = "", confidence: float = 0.0, now: str = "",
                          *, commit: bool = False) -> HypothesisEvent:
        """인과 가설을 불변 등록(DRAFT). cause/effect 는 등록된 변수여야 한다."""
        if ledger.read_variables() and not ledger.variable_exists(cause_variable):
            raise UnknownVariable(f"미등록 cause 변수 {cause_variable}")
        if ledger.read_variables() and not ledger.variable_exists(effect_variable):
            raise UnknownVariable(f"미등록 effect 변수 {effect_variable}")
        hid = _hypothesis_id(cause_variable, effect_variable, statement)
        existing = ledger.hypothesis_events_for(hid)
        if existing:
            first = existing[0]
            if first.get("mechanism") != mechanism:
                raise ImmutableHypothesisError(f"{hid} 가설 불변 — 변경 불가")
            return HypothesisEvent(**existing[-1])
        meta = {"hypothesis_id": hid, "cause_variable": cause_variable,
                "effect_variable": effect_variable, "statement": statement,
                "mechanism": mechanism, "confidence": round(float(confidence), 8)}
        rec = self._emit_hypothesis_event(meta, "", DRAFT, now, commit=commit)
        self._record_artifact(ART_HYPOTHESIS, hid, _artifact_id(ART_VARIABLE, cause_variable),
                              now, commit=commit)
        return HypothesisEvent(**rec)

    def transition_hypothesis(self, hypothesis_id: str, to: str, now: str = "", *,
                              commit: bool = False) -> dict:
        meta = self._hypothesis_meta(hypothesis_id)
        if meta is None:
            raise UnknownHypothesis(f"미존재 가설 {hypothesis_id}")
        return self._emit_hypothesis_event(meta, self.hypothesis_state(hypothesis_id), to, now,
                                           commit=commit)

    def _safe_advance_hypothesis(self, hypothesis_id: str, to: str, now: str,
                                 *, commit: bool) -> None:
        meta = self._hypothesis_meta(hypothesis_id)
        if meta is None:
            return
        cur = self.hypothesis_state(hypothesis_id)
        if cur != to and can_transition_hypothesis(cur, to):
            self._emit_hypothesis_event(meta, cur, to, now, commit=commit)

    # ── Relationship Study / 그래프 엣지 (노드 존재 검증·순환 차단) ──
    def record_relationship(self, cause: str, edge_type: str, effect: str,
                            methodology: str = "", dataset_reference: str = "", period: str = "",
                            controls: list | None = None, result: str = "", now: str = "",
                            *, commit: bool = False) -> RelationshipStudy:
        if edge_type not in EDGE_TYPES:
            raise ValueError(f"알 수 없는 엣지 유형 {edge_type}")
        if ledger.read_variables():
            if not ledger.variable_exists(cause):
                raise UnknownVariable(f"미등록 cause 노드 {cause}")
            if not ledger.variable_exists(effect):
                raise UnknownVariable(f"미등록 effect 노드 {effect}")
        sid = _study_id(cause, edge_type, effect)
        # 방향성 엣지 순환 차단(CORRELATED_WITH 는 대칭 → 제외).
        if edge_type in DIRECTED_EDGES and not ledger.relationship_exists(sid):
            directed = [(r.get("cause"), r.get("effect")) for r in ledger.read_relationships()
                        if r.get("edge_type") in DIRECTED_EDGES]
            cyc = detect_cycle(directed + [(cause, effect)])
            if cyc:
                raise CausalCycleError("인과 순환 차단: " + "->".join(cyc))
        rec = RelationshipStudy(
            study_id=sid, cause=cause, effect=effect, edge_type=edge_type,
            methodology=methodology, dataset_reference=dataset_reference, period=period,
            controls=list(controls or []), result=result, created_at=now,
            input_hash=input_digest(cause, edge_type, effect), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.relationship_exists(sid):
            head = ledger.relationships_head()
            ledger.append_relationship(_seal(rec, head["record_hash"] if head else GENESIS))
        return RelationshipStudy(**rec)

    # ── Causal Experiment (이벤트 소싱) ──
    def experiment_state(self, experiment_id: str) -> str:
        evs = ledger.experiment_events_for(experiment_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _experiment_meta(self, experiment_id: str) -> dict | None:
        evs = ledger.experiment_events_for(experiment_id)
        return evs[0] if evs else None

    def _emit_experiment_event(self, meta: dict, frm: str, to: str, now: str,
                               *, commit: bool) -> dict:
        if not can_transition_experiment(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(experiment)")
        xid = meta["experiment_id"]
        eid = experiment_event_id(xid, frm, to)
        rec = ExperimentEvent(
            event_id=eid, experiment_id=xid, hypothesis_id=meta["hypothesis_id"],
            method=meta["method"], inputs=meta["inputs"], controls=meta["controls"],
            results=meta["results"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(xid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experiment_event_exists(eid):
            head = ledger.experiments_head()
            ledger.append_experiment_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_experiment(self, hypothesis_id: str, method: str, inputs: dict | None = None,
                          controls: list | None = None, now: str = "",
                          *, commit: bool = False) -> ExperimentEvent:
        if self._hypothesis_meta(hypothesis_id) is None:
            raise UnknownHypothesis(f"미존재 가설 {hypothesis_id}")
        inp = dict(inputs or {})
        ih = input_digest(sorted(inp.items()))
        xid = _experiment_id(hypothesis_id, method, ih)
        existing = ledger.experiment_events_for(xid)
        if existing:
            return ExperimentEvent(**existing[-1])
        meta = {"experiment_id": xid, "hypothesis_id": hypothesis_id, "method": method,
                "inputs": inp, "controls": list(controls or []), "results": {}}
        rec = self._emit_experiment_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_EXPERIMENT, xid, _artifact_id(ART_HYPOTHESIS, hypothesis_id),
                              now, commit=commit)
        # 가설 DRAFT→TESTING.
        self._safe_advance_hypothesis(hypothesis_id, TESTING, now, commit=commit)
        return ExperimentEvent(**rec)

    def run_experiment(self, experiment_id: str, now: str = "", *,
                       commit: bool = False) -> dict:
        """실험을 진행 기록(CREATED→RUNNING→COMPLETED). **실제 개입 없음 — 기록만.**"""
        if self._experiment_meta(experiment_id) is None:
            raise UnknownExperiment(f"미존재 실험 {experiment_id}")
        meta = self._experiment_meta(experiment_id)
        cur = self.experiment_state(experiment_id)
        if cur == CREATED:
            self._emit_experiment_event(meta, CREATED, RUNNING, now, commit=commit)
        cur = self.experiment_state(experiment_id) if commit else RUNNING
        if can_transition_experiment(RUNNING, COMPLETED):
            self._emit_experiment_event(meta, RUNNING, COMPLETED, now, commit=commit)
        return {"experiment_id": experiment_id, "state": self.experiment_state(experiment_id)}

    def transition_experiment(self, experiment_id: str, to: str, now: str = "", *,
                              commit: bool = False) -> dict:
        meta = self._experiment_meta(experiment_id)
        if meta is None:
            raise UnknownExperiment(f"미존재 실험 {experiment_id}")
        return self._emit_experiment_event(meta, self.experiment_state(experiment_id), to, now,
                                           commit=commit)

    def _safe_advance_experiment(self, experiment_id: str, to: str, now: str,
                                 *, commit: bool) -> None:
        meta = self._experiment_meta(experiment_id)
        if meta is None:
            return
        cur = self.experiment_state(experiment_id)
        if cur != to and can_transition_experiment(cur, to):
            self._emit_experiment_event(meta, cur, to, now, commit=commit)

    # ── Evidence (서술 기록) ──
    def record_evidence(self, experiment_id: str, metric: str, value: float,
                        interpretation: str = "", confidence: float = 0.0, now: str = "",
                        *, commit: bool = False) -> Evidence:
        meta = self._experiment_meta(experiment_id)
        if meta is None:
            raise UnknownExperiment(f"미존재 실험 {experiment_id}")
        eid = _evidence_id(experiment_id, metric)
        rec = Evidence(
            evidence_id=eid, experiment_id=experiment_id, metric=metric,
            value=round(float(value), 8), interpretation=interpretation,
            confidence=round(float(confidence), 8), created_at=now,
            input_hash=input_digest(experiment_id, metric), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidences_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EVIDENCE, eid, _artifact_id(ART_EXPERIMENT, experiment_id),
                              now, commit=commit)
        # 실험 COMPLETED→ANALYZED, 가설 TESTING→EVIDENCED.
        self._safe_advance_experiment(experiment_id, RUNNING, now, commit=commit)
        self._safe_advance_experiment(experiment_id, COMPLETED, now, commit=commit)
        self._safe_advance_experiment(experiment_id, ANALYZED, now, commit=commit)
        self._safe_advance_hypothesis(meta.get("hypothesis_id"), EVIDENCED, now, commit=commit)
        return Evidence(**rec)

    # ── Causal Graph Snapshot (이벤트 소싱) ──
    def graph_state(self, graph_id: str) -> str:
        evs = ledger.graph_events_for(graph_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _emit_graph_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_graph(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(graph)")
        gid = meta["graph_id"]
        eid = graph_event_id(gid, frm, to)
        rec = GraphEvent(
            event_id=eid, graph_id=gid, name=meta["name"], node_count=meta["node_count"],
            edge_count=meta["edge_count"], node_distribution=meta["node_distribution"],
            edge_distribution=meta["edge_distribution"], graph_hash=meta["graph_hash"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(gid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.graph_event_exists(eid):
            head = ledger.graphs_head()
            ledger.append_graph_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def snapshot_graph(self, name: str, now: str = "", *, commit: bool = False) -> GraphEvent:
        """변수(노드) + 관계(엣지)로 인과 그래프를 스냅샷. REGISTERED→CONNECTED→SNAPSHOTTED."""
        variables = ledger.read_variables()
        rels = ledger.read_relationships()
        node_ids = [v.get("variable_id") for v in variables]
        edges = [(r.get("cause"), r.get("effect")) for r in rels]
        node_dist: dict = {}
        for v in variables:
            node_dist[v.get("node_type")] = node_dist.get(v.get("node_type"), 0) + 1
        edge_dist: dict = {}
        for r in rels:
            edge_dist[r.get("edge_type")] = edge_dist.get(r.get("edge_type"), 0) + 1
        gh = _graph_hash(node_ids, edges)
        gid = _graph_id(name)
        meta = {"graph_id": gid, "name": name, "node_count": len(node_ids),
                "edge_count": len(rels), "node_distribution": dict(sorted(node_dist.items())),
                "edge_distribution": dict(sorted(edge_dist.items())), "graph_hash": gh}
        existing = ledger.graph_events_for(gid)
        if not existing:
            self._emit_graph_event(meta, "", REGISTERED, now, commit=commit)
        self._emit_graph_event(meta, REGISTERED, CONNECTED, now, commit=commit)
        rec = self._emit_graph_event(meta, CONNECTED, SNAPSHOTTED, now, commit=commit)
        self._record_artifact(ART_GRAPH, gid, "", now, commit=commit)
        return GraphEvent(**rec)

    def graph_cycle(self) -> list:
        """방향성 인과 엣지 순환 탐지(연구 무결성)."""
        directed = [(r.get("cause"), r.get("effect")) for r in ledger.read_relationships()
                    if r.get("edge_type") in DIRECTED_EDGES]
        return detect_cycle(directed)

    def orphan_variables(self) -> list:
        """어떤 관계에도 참여하지 않는 고아 변수(정보용)."""
        used: set = set()
        for r in ledger.read_relationships():
            used.add(r.get("cause"))
            used.add(r.get("effect"))
        return sorted(v.get("variable_id") for v in ledger.read_variables()
                      if v.get("variable_id") not in used)

    # ── Causal Analysis Framework ──
    def analyze_causality(self, metrics: dict) -> dict:
        """인과 지표 → CAUSAL_SUPPORT. **CAUSAL SCORE ≠ TRADING PERMISSION.**"""
        return {"causal_score": causal_score(metrics), "causal_support": causal_support(metrics)}

    # ── Causal Report ──
    def generate_report(self, hypothesis_id: str, metrics: dict | None = None, now: str = "",
                        *, commit: bool = False) -> CausalReport:
        meta = self._hypothesis_meta(hypothesis_id)
        if meta is None:
            raise UnknownHypothesis(f"미존재 가설 {hypothesis_id}")
        m = dict(metrics or {})
        # 실험 증거로부터 관측 근거 수 집계.
        ev_count = 0
        for x in ledger.distinct_experiments():
            if x.get("hypothesis_id") == hypothesis_id:
                ev_count += len(ledger.evidences_for_experiment(x.get("experiment_id")))
        score = causal_score(m)
        support = causal_support(m)
        alt_warn = bool(m.get("alternative_explanation_warning", False))
        rid = _report_id(hypothesis_id)
        rec = CausalReport(
            report_id=rid, hypothesis_id=hypothesis_id, cause_variable=meta["cause_variable"],
            effect_variable=meta["effect_variable"], metrics=m, causal_score=score,
            causal_support=support, evidence_count=ev_count,
            alternative_explanation_warning=alt_warn, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(hypothesis_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, _artifact_id(ART_HYPOTHESIS, hypothesis_id), now,
                              commit=commit)
        return CausalReport(**rec)

    # ── 상위 레이어 READ ONLY 조회 ──
    def list_source_references(self, layer: str, limit: int = 0) -> list:
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
    def summary(self, now: str = "") -> CausalSummary:
        hyps = ledger.distinct_hypotheses()
        hstate: dict = {}
        for h in hyps:
            st = self.hypothesis_state(h.get("hypothesis_id"))
            hstate[st] = hstate.get(st, 0) + 1
        rels = ledger.read_relationships()
        edist: dict = {}
        for r in rels:
            edist[r.get("edge_type")] = edist.get(r.get("edge_type"), 0) + 1
        exps = ledger.distinct_experiments()
        xstate: dict = {}
        for x in exps:
            st = self.experiment_state(x.get("experiment_id"))
            xstate[st] = xstate.get(st, 0) + 1
        reports = ledger.read_reports()
        sup: dict = {}
        for rp in reports:
            sup[rp.get("causal_support")] = sup.get(rp.get("causal_support"), 0) + 1
        return CausalSummary(
            timestamp=now, variable_count=len(ledger.read_variables()),
            hypothesis_count=len(hyps), hypothesis_state_distribution=dict(sorted(hstate.items())),
            relationship_count=len(rels), edge_type_distribution=dict(sorted(edist.items())),
            experiment_count=len(exps),
            experiment_state_distribution=dict(sorted(xstate.items())),
            evidence_count=len(ledger.read_evidences()),
            graph_count=len(ledger.distinct_graphs()), report_count=len(reports),
            support_distribution=dict(sorted(sup.items())))
