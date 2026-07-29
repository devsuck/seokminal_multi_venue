"""Research OS Orchestration Engine (P11) — 전 연구 생태계 관찰·조직. **관찰·조직·기록 전용.**

P9.8~P10.15 전 계층을 READ ONLY 로 소비해 레이어 레지스트리·워크플로 지도·교차계층 이벤트·생태계
스냅샷·건강 리포트·의존 분석·계보 추적을 제공한다. **연구 실행·실험 시작·strategy 선택·model 배포·
config 수정·capital 배분 없음.** execution/broker/portfolio execution/risk execution/permission
mutation/capital allocation import·호출 없음. ORCHESTRATION ≠ EXECUTION · VISIBILITY ≠ CONTROL ·
STATUS ≠ APPROVAL · INSIGHT ≠ ACTION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.research_os import ledger
from jarvis.research_os.models import (
    ACTIVE,
    ARCHIVED,
    ART_DEPENDENCY,
    ART_EVENT,
    ART_HEALTH,
    ART_LAYER,
    ART_LINEAGE,
    ART_SNAPSHOT,
    ART_WORKFLOW,
    COMPLETED,
    CREATED,
    DEPRECATED,
    EDGE_TYPES,
    GENESIS,
    NODE_TYPES,
    REGISTERED,
    TRACKING,
    VERIFIED,
    CrossLayerEvent,
    DependencyEdge,
    HealthReport,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableWorkflowError,
    InvalidWorkflowGraph,
    LayerEvent,
    LineageEdge,
    OrchestrationArtifact,
    OrchestrationSummary,
    SnapshotEvent,
    UnknownLayer,
    UnknownSnapshot,
    UnknownWorkflow,
    WorkflowEvent,
    artifact_id as _artifact_id,
    can_transition_layer,
    can_transition_snapshot,
    can_transition_workflow,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    ecosystem_hash as _ecosystem_hash,
    event_id as _event_id,
    health_report_id as _health_report_id,
    health_score,
    input_digest,
    layer_event_id,
    layer_id as _layer_id,
    lineage_id as _lineage_id,
    snapshot_event_id,
    snapshot_id as _snapshot_id,
    system_health,
    workflow_event_id,
    workflow_id as _workflow_id,
)

_DISCLAIMER = ("연구 OS 관찰 데이터 — ORCHESTRATION ≠ EXECUTION · VISIBILITY ≠ CONTROL · "
               "STATUS ≠ APPROVAL · INSIGHT ≠ ACTION. 실행/선택/배포/config변경/배분 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchOSEngine:
    """연구 OS 오케스트레이션 엔진. 불변·append-only·결정적. 실행/거래/배포/선택/config변경 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = OrchestrationArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Layer Registry (이벤트 소싱, 불변) ──
    def layer_state(self, layer_id: str) -> str:
        evs = ledger.layer_events_for(layer_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _layer_meta(self, layer_id: str) -> dict | None:
        evs = ledger.layer_events_for(layer_id)
        return evs[0] if evs else None

    def _emit_layer_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_layer(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(layer)")
        lid = meta["layer_id"]
        eid = layer_event_id(lid, frm, to)
        rec = LayerEvent(
            event_id=eid, layer_id=lid, name=meta["name"], version=meta["version"],
            prefix=meta["prefix"], capabilities=meta["capabilities"], from_state=frm, to_state=to,
            status=to, created_at=now, input_hash=input_digest(lid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.layer_event_exists(eid):
            head = ledger.layers_head()
            ledger.append_layer_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_layer(self, name: str, version: str = "1.0", prefix: str = "",
                       capabilities: list | None = None, activate: bool = False, now: str = "",
                       *, commit: bool = False) -> LayerEvent:
        lid = _layer_id(name)
        existing = ledger.layer_events_for(lid)
        if existing:
            first = existing[0]
            if first.get("version") != version or first.get("prefix") != prefix:
                raise ImmutableLayerError(f"{lid} 레이어 불변 — 변경 불가")
            if activate:
                self._safe_advance_layer(lid, ACTIVE, now, commit=commit)
            return LayerEvent(**existing[-1])
        meta = {"layer_id": lid, "name": name, "version": version, "prefix": prefix,
                "capabilities": list(capabilities or [])}
        rec = self._emit_layer_event(meta, "", REGISTERED, now, commit=commit)
        self._record_artifact(ART_LAYER, lid, "", now, commit=commit)
        if activate:
            self._safe_advance_layer(lid, ACTIVE, now, commit=commit)
        return LayerEvent(**rec)

    def transition_layer(self, layer_id: str, to: str, now: str = "", *,
                         commit: bool = False) -> dict:
        meta = self._layer_meta(layer_id)
        if meta is None:
            raise UnknownLayer(f"미존재 레이어 {layer_id}")
        return self._emit_layer_event(meta, self.layer_state(layer_id), to, now, commit=commit)

    def _safe_advance_layer(self, layer_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._layer_meta(layer_id)
        if meta is None:
            return
        cur = self.layer_state(layer_id)
        if cur != to and can_transition_layer(cur, to):
            self._emit_layer_event(meta, cur, to, now, commit=commit)

    def register_known_layers(self, now: str = "", *, commit: bool = False) -> int:
        """상위 레이어(READ ONLY 소스)를 레이어 레지스트리에 등록·ACTIVE. 파일 무변경."""
        n = 0
        for name, (filename, _idf) in sorted(ledger.SOURCE_LEDGERS.items()):
            prefix = filename.split("_")[0] + "_" if "_" in filename else ""
            self.register_layer(name, "1.0", prefix, [], activate=True, now=now, commit=commit)
            n += 1
        return n

    # ── Research Workflow (이벤트 소싱, 그래프 검증) ──
    def workflow_state(self, workflow_id: str) -> str:
        evs = ledger.workflow_events_for(workflow_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _workflow_meta(self, workflow_id: str) -> dict | None:
        evs = ledger.workflow_events_for(workflow_id)
        return evs[0] if evs else None

    def _emit_workflow_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition_workflow(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(workflow)")
        wid = meta["workflow_id"]
        eid = workflow_event_id(wid, frm, to)
        rec = WorkflowEvent(
            event_id=eid, workflow_id=wid, name=meta["name"], nodes=meta["nodes"],
            edges=meta["edges"], created_from=meta["created_from"], from_state=frm, to_state=to,
            status=to, created_at=now, input_hash=input_digest(wid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.workflow_event_exists(eid):
            head = ledger.workflows_head()
            ledger.append_workflow_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_workflow(self, name: str, nodes: list | None = None, edges: list | None = None,
                          created_from: list | None = None, now: str = "",
                          *, commit: bool = False) -> WorkflowEvent:
        """교차계층 연구 여정을 워크플로 그래프로 등록. 노드 유형 검증 + 순환 차단."""
        nds = list(nodes or [])
        eds = [list(e) for e in (edges or [])]
        for nd in nds:
            if isinstance(nd, dict):
                if nd.get("type") not in NODE_TYPES:
                    raise InvalidWorkflowGraph(f"미등록 노드 유형 {nd.get('type')}")
        edge_pairs = []
        for e in eds:
            if len(e) >= 3 and e[1] not in EDGE_TYPES:
                raise InvalidWorkflowGraph(f"미등록 엣지 유형 {e[1]}")
            if len(e) >= 3:
                edge_pairs.append((e[0], e[2]))
            elif len(e) == 2:
                edge_pairs.append((e[0], e[1]))
        cyc = detect_cycle(edge_pairs)
        if cyc:
            raise InvalidWorkflowGraph("워크플로 순환 차단: " + "->".join(cyc))
        wid = _workflow_id(name)
        existing = ledger.workflow_events_for(wid)
        if existing:
            first = existing[0]
            if first.get("nodes") != nds:
                raise ImmutableWorkflowError(f"{wid} 워크플로 불변 — 변경 불가")
            return WorkflowEvent(**existing[-1])
        meta = {"workflow_id": wid, "name": name, "nodes": nds, "edges": eds,
                "created_from": list(created_from or [])}
        rec = self._emit_workflow_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_WORKFLOW, wid, "", now, commit=commit)
        return WorkflowEvent(**rec)

    def transition_workflow(self, workflow_id: str, to: str, now: str = "", *,
                            commit: bool = False) -> dict:
        meta = self._workflow_meta(workflow_id)
        if meta is None:
            raise UnknownWorkflow(f"미존재 워크플로 {workflow_id}")
        return self._emit_workflow_event(meta, self.workflow_state(workflow_id), to, now,
                                         commit=commit)

    # ── Cross Layer Event ──
    def record_event(self, layer: str, event_type: str, reference_id: str, timestamp: str = "",
                     now: str = "", *, commit: bool = False) -> CrossLayerEvent:
        eid = _event_id(layer, event_type, reference_id)
        rec = CrossLayerEvent(
            event_id=eid, layer=layer, event_type=event_type, reference_id=reference_id,
            timestamp=timestamp or now, created_at=now,
            input_hash=input_digest(layer, event_type, reference_id),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.events_head()
            ledger.append_event(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EVENT, eid, _artifact_id(ART_LAYER, _layer_id(layer))
                              if ledger.artifact_exists(_artifact_id(ART_LAYER, _layer_id(layer)))
                              else "", now, commit=commit)
        return CrossLayerEvent(**rec)

    # ── Lineage (연구 객체 그래프) ──
    def add_lineage(self, from_node: str, from_type: str, edge_type: str, to_node: str,
                    to_type: str, now: str = "", *, commit: bool = False) -> LineageEdge:
        if from_type not in NODE_TYPES or to_type not in NODE_TYPES:
            raise InvalidWorkflowGraph(f"미등록 노드 유형 {from_type}/{to_type}")
        if edge_type not in EDGE_TYPES:
            raise InvalidWorkflowGraph(f"미등록 엣지 유형 {edge_type}")
        lid = _lineage_id(from_node, edge_type, to_node)
        if not ledger.lineage_exists(lid):
            edges = [(e.get("from_node"), e.get("to_node")) for e in ledger.read_lineage()]
            cyc = detect_cycle(edges + [(from_node, to_node)])
            if cyc:
                raise InvalidWorkflowGraph("계보 순환 차단: " + "->".join(cyc))
        rec = LineageEdge(
            lineage_id=lid, from_node=from_node, from_type=from_type, edge_type=edge_type,
            to_node=to_node, to_type=to_type, created_at=now,
            input_hash=input_digest(from_node, edge_type, to_node),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_LINEAGE, lid, "", now, commit=commit)
        return LineageEdge(**rec)

    def trace_research_lineage(self, node: str) -> list:
        """node 의 상류 계보 조상(계보 엣지 역방향 도달 노드)."""
        rev: dict = {}
        for e in ledger.read_lineage():
            rev.setdefault(e.get("to_node"), set()).add(e.get("from_node"))
        seen: list = []
        visited: set = set()
        stack = [node]
        while stack:
            n = stack.pop()
            for anc in sorted(rev.get(n, ())):
                if anc not in visited:
                    visited.add(anc)
                    seen.append(anc)
                    stack.append(anc)
        return seen

    def lineage_cycle(self) -> list:
        edges = [(e.get("from_node"), e.get("to_node")) for e in ledger.read_lineage()]
        return detect_cycle(edges)

    # ── Dependency Analysis (레이어 간) ──
    def analyze_dependencies(self, dependencies: list | None = None, now: str = "",
                             *, commit: bool = False) -> list:
        """레이어 간 의존을 기록·검증(순환 탐지). dependencies: [(from_layer, to_layer, relation)]."""
        out: list = []
        for dep in (dependencies or []):
            from_layer, to_layer = dep[0], dep[1]
            relation = dep[2] if len(dep) > 2 else "DEPENDS_ON"
            did = _dependency_id(from_layer, to_layer)
            rec = DependencyEdge(
                dependency_id=did, from_layer=from_layer, to_layer=to_layer, relation=relation,
                created_at=now, input_hash=input_digest(from_layer, to_layer),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.dependency_exists(did):
                head = ledger.dependencies_head()
                ledger.append_dependency(_seal(rec, head["record_hash"] if head else GENESIS))
            self._record_artifact(ART_DEPENDENCY, did, "", now, commit=commit)
            out.append(DependencyEdge(**rec))
        return out

    def dependency_cycle(self) -> list:
        edges = [(d.get("from_layer"), d.get("to_layer")) for d in ledger.read_dependencies()]
        return detect_cycle(edges)

    # ── Ecosystem Snapshot (이벤트 소싱) ──
    def snapshot_state(self, snapshot_id: str) -> str:
        evs = ledger.snapshot_events_for(snapshot_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _snapshot_meta(self, snapshot_id: str) -> dict | None:
        evs = ledger.snapshot_events_for(snapshot_id)
        return evs[0] if evs else None

    def _emit_snapshot_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition_snapshot(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(snapshot)")
        sid = meta["snapshot_id"]
        eid = snapshot_event_id(sid, frm, to)
        rec = SnapshotEvent(
            event_id=eid, snapshot_id=sid, name=meta["name"], epoch=meta["epoch"],
            layers=meta["layers"], workflow_count=meta["workflow_count"],
            event_count=meta["event_count"], health_score=meta["health_score"],
            ecosystem_hash=meta["ecosystem_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(sid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_event_exists(eid):
            head = ledger.snapshots_head()
            ledger.append_snapshot_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def build_ecosystem_snapshot(self, name: str, epoch: str = "", metrics: dict | None = None,
                                 now: str = "", *, commit: bool = False) -> SnapshotEvent:
        """전 생태계 상태를 스냅샷(CREATED). health_score 는 정보용."""
        layers = sorted(l.get("layer_id") for l in ledger.distinct_layers())
        wf_count = len(ledger.distinct_workflows())
        ev_count = len(ledger.read_events())
        hscore = health_score(dict(metrics or {}))
        eh = _ecosystem_hash(layers, wf_count, ev_count)
        sid = _snapshot_id(name, epoch)
        existing = ledger.snapshot_events_for(sid)
        if existing:
            return SnapshotEvent(**existing[-1])
        meta = {"snapshot_id": sid, "name": name, "epoch": epoch, "layers": layers,
                "workflow_count": wf_count, "event_count": ev_count, "health_score": hscore,
                "ecosystem_hash": eh}
        rec = self._emit_snapshot_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SnapshotEvent(**rec)

    def verify_snapshot(self, snapshot_id: str, now: str = "", *, commit: bool = False) -> dict:
        meta = self._snapshot_meta(snapshot_id)
        if meta is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        cur = self.snapshot_state(snapshot_id)
        if cur == CREATED:
            self._emit_snapshot_event(meta, CREATED, VERIFIED, now, commit=commit)
        return {"snapshot_id": snapshot_id, "state": self.snapshot_state(snapshot_id)}

    def compare_snapshots(self, snapshot_a: str, snapshot_b: str) -> dict:
        """두 스냅샷의 서술적 차이(정보용)."""
        a = self._snapshot_meta(snapshot_a)
        b = self._snapshot_meta(snapshot_b)
        if a is None or b is None:
            raise UnknownSnapshot("미존재 스냅샷 참조")
        return {"snapshot_a": snapshot_a, "snapshot_b": snapshot_b,
                "layer_delta": len(a.get("layers", [])) - len(b.get("layers", [])),
                "workflow_delta": a.get("workflow_count", 0) - b.get("workflow_count", 0),
                "event_delta": a.get("event_count", 0) - b.get("event_count", 0),
                "health_delta": round(a.get("health_score", 0.0) - b.get("health_score", 0.0), 8),
                "hash_changed": a.get("ecosystem_hash") != b.get("ecosystem_hash"),
                "note": "서술적 비교만 — 자동 조치 없음"}

    # ── Health Report ──
    def generate_health_report(self, snapshot_ref: str = "GLOBAL", metrics: dict | None = None,
                               now: str = "", *, commit: bool = False) -> HealthReport:
        m = dict(metrics or {})
        layers = ledger.distinct_layers()
        active = sum(1 for l in layers if self.layer_state(l.get("layer_id")) == ACTIVE)
        if "layer_availability" not in m and layers:
            m["layer_availability"] = round(active / len(layers), 8)
        hscore = health_score(m)
        health = system_health(m)
        hid = _health_report_id(snapshot_ref)
        rec = HealthReport(
            health_report_id=hid, snapshot_ref=snapshot_ref, metrics=m, health_score=hscore,
            system_health=health, layer_count=len(layers), active_layer_count=active,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(snapshot_ref),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.health_report_exists(hid):
            head = ledger.health_head()
            ledger.append_health_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HEALTH, hid, "", now, commit=commit)
        return HealthReport(**rec)

    def analyze(self, metrics: dict) -> dict:
        return {"health_score": health_score(metrics), "system_health": system_health(metrics)}

    # ── Summary ──
    def summary(self, now: str = "") -> OrchestrationSummary:
        layers = ledger.distinct_layers()
        lstate: dict = {}
        for l in layers:
            st = self.layer_state(l.get("layer_id"))
            lstate[st] = lstate.get(st, 0) + 1
        wfs = ledger.distinct_workflows()
        wstate: dict = {}
        for w in wfs:
            st = self.workflow_state(w.get("workflow_id"))
            wstate[st] = wstate.get(st, 0) + 1
        events = ledger.read_events()
        edist: dict = {}
        for e in events:
            edist[e.get("event_type")] = edist.get(e.get("event_type"), 0) + 1
        return OrchestrationSummary(
            timestamp=now, layer_count=len(layers),
            layer_state_distribution=dict(sorted(lstate.items())), workflow_count=len(wfs),
            workflow_state_distribution=dict(sorted(wstate.items())), event_count=len(events),
            event_type_distribution=dict(sorted(edist.items())),
            snapshot_count=len(ledger.distinct_snapshots()),
            dependency_count=len(ledger.read_dependencies()),
            lineage_count=len(ledger.read_lineage()),
            health_report_count=len(ledger.read_health_reports()))
