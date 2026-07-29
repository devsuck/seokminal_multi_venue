"""Governance Orchestration Engine (P10.23) — 전 거버넌스 계층 관찰·집계·조정. **관찰·조직·기록 전용.**

P9.8~P10.22 전 계층을 READ ONLY 로 참조(파일 기반, import 없음)해 계층 레지스트리·계층 상태 수집·의존 지도·
시스템 스냅샷·교차계층 충돌·건강 요약·오케스트레이션 리포트·연구 OS 상태를 제공한다. **실행 계층 아님 —
거래·주문·portfolio 수정·capital 배분·strategy 배포·promote·activate·permission/config 변경 없음.**
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller
import·호출 없음. ORCHESTRATION ≠ EXECUTION · MONITORING ≠ CONTROL · STATUS ≠ APPROVAL · AGGREGATION ≠ ACTION.
상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.governance_orchestration import ledger
from jarvis.governance_orchestration.models import (
    ART_CONFLICT,
    GENESIS,
    ART_DEPENDENCY,
    ART_HEALTH,
    ART_LAYER,
    ART_REPORT,
    ART_SNAPSHOT,
    ART_STATUS,
    CONFLICT_CATEGORIES,
    CONNECTED,
    CREATED,
    GENERATED,
    MONITORED,
    REGISTERED,
    VERIFIED,
    ConflictRecord,
    DependencyEdge,
    HealthSummary,
    IllegalTransition,
    ImmutableLayerError,
    ImmutableStatusError,
    InvalidConflictCategory,
    InvalidDependencyGraph,
    LayerEvent,
    LayerStatusRecord,
    OrchestrationArtifact,
    OrchestrationReport,
    OrchestrationSummary,
    SystemSnapshotEvent,
    UnknownLayer,
    UnknownSnapshot,
    artifact_id as _artifact_id,
    can_transition_layer,
    can_transition_snapshot,
    conflict_id as _conflict_id,
    content_hash,
    dependency_id as _dependency_id,
    detect_cycle,
    health_id as _health_id,
    health_score,
    input_digest,
    layer_event_id,
    layer_id as _layer_id,
    metadata_hash as _metadata_hash,
    report_id as _report_id,
    snapshot_event_id,
    snapshot_id as _snapshot_id,
    status_id as _status_id,
    system_hash as _system_hash,
    system_health,
)

_DISCLAIMER = ("거버넌스 오케스트레이션 데이터 — ORCHESTRATION ≠ EXECUTION · MONITORING ≠ CONTROL · "
               "STATUS ≠ APPROVAL · AGGREGATION ≠ ACTION. 실행/거래/배포/config·permission 변경 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class GovernanceOrchestrationEngine:
    """거버넌스 오케스트레이션 엔진. 불변·append-only·결정적. 실행/거래/배포/승인/집행 권한 없음."""

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
            event_id=eid, layer_id=lid, name=meta["name"], layer_type=meta["layer_type"],
            source_prefix=meta["source_prefix"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(lid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.layer_event_exists(eid):
            head = ledger.layers_head()
            ledger.append_layer_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_layer(self, name: str, layer_type: str = "governance", source_prefix: str = "",
                     now: str = "", *, commit: bool = False) -> LayerEvent:
        """거버넌스 계층을 레지스트리에 등록(REGISTERED). 동일 name·상이 메타 → 불변 위반."""
        lid = _layer_id(name)
        existing = ledger.layer_events_for(lid)
        if existing:
            first = existing[0]
            if first.get("layer_type") != layer_type or first.get("source_prefix") != source_prefix:
                raise ImmutableLayerError(f"{lid} 레이어 불변 — 변경 불가")
            return LayerEvent(**existing[-1])
        meta = {"layer_id": lid, "name": name, "layer_type": layer_type,
                "source_prefix": source_prefix}
        rec = self._emit_layer_event(meta, "", REGISTERED, now, commit=commit)
        self._record_artifact(ART_LAYER, lid, "", now, commit=commit)
        return LayerEvent(**rec)

    def transition_layer(self, layer_id: str, to: str, now: str = "", *,
                         commit: bool = False) -> dict:
        meta = self._layer_meta(layer_id)
        if meta is None:
            raise UnknownLayer(f"미존재 레이어 {layer_id}")
        return self._emit_layer_event(meta, self.layer_state(layer_id), to, now, commit=commit)

    def register_known_layers(self, now: str = "", *, commit: bool = False) -> int:
        """상위 소스 레이어(READ ONLY)를 레지스트리에 등록. 파일 무변경."""
        n = 0
        for name in ledger.known_source_layers():
            spec = ledger.SOURCE_LEDGERS[name]
            prefix = spec[0].split("_")[0] + "_" if "_" in spec[0] else ""
            self.register_layer(name, "governance", prefix, now, commit=commit)
            n += 1
        return n

    # ── Layer Status 수집 (불변) ──
    def ingest_layer_status(self, layer_reference: str, status: str = "UNKNOWN",
                          metrics: dict | None = None, epoch: str = "", now: str = "",
                          *, commit: bool = False) -> LayerStatusRecord:
        """계층이 보고한 상태를 수집·기록하고 레이어를 CONNECTED→MONITORED 로 승격(관찰). **수집·기록만.**"""
        m = dict(metrics or {})
        sid = _status_id(layer_reference, epoch)
        mh = _metadata_hash({"status": status, "metrics": m})
        existing = ledger.get_status(sid)
        if existing is not None:
            if existing.get("metrics_hash") != mh:
                raise ImmutableStatusError(f"{sid} 상태 기록 불변 — 변경 불가")
            return LayerStatusRecord(**{k: v for k, v in existing.items()
                                        if k in LayerStatusRecord.__dataclass_fields__})
        rec = LayerStatusRecord(
            status_id=sid, layer_reference=layer_reference, status=status, metrics=m,
            metrics_hash=mh, epoch=epoch, timestamp=now, created_at=now,
            input_hash=input_digest(layer_reference, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.status_exists(sid):
            head = ledger.status_head()
            ledger.append_status(_seal(rec, head["record_hash"] if head else GENESIS))
        # 레이어 관찰 승격(등록된 경우)
        lid = _layer_id(layer_reference)
        parent = ""
        if ledger.layer_exists(lid):
            self._safe_advance_layer(lid, CONNECTED, now, commit=commit)
            self._safe_advance_layer(lid, MONITORED, now, commit=commit)
            parent = _artifact_id(ART_LAYER, lid) if ledger.artifact_exists(
                _artifact_id(ART_LAYER, lid)) else ""
        self._record_artifact(ART_STATUS, sid, parent, now, commit=commit)
        return LayerStatusRecord(**rec)

    def _safe_advance_layer(self, layer_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._layer_meta(layer_id)
        if meta is None:
            return
        cur = self.layer_state(layer_id)
        if cur != to and can_transition_layer(cur, to):
            self._emit_layer_event(meta, cur, to, now, commit=commit)

    # ── Dependency Map ──
    def build_dependency_map(self, dependencies: list | None = None, now: str = "",
                           *, commit: bool = False) -> list:
        """계층 간 의존 지도를 기록·검증(자기참조·순환 차단). dependencies: [(from, to, relation)]."""
        out: list = []
        for dep in (dependencies or []):
            from_layer, to_layer = dep[0], dep[1]
            relation = dep[2] if len(dep) > 2 else "DEPENDS_ON"
            if from_layer == to_layer:
                raise InvalidDependencyGraph(f"자기참조 의존 차단 {from_layer}")
            did = _dependency_id(from_layer, to_layer)
            if not ledger.dependency_exists(did):
                edges = [(d.get("from_layer"), d.get("to_layer"))
                         for d in ledger.read_dependencies()]
                cyc = detect_cycle(edges + [(from_layer, to_layer)])
                if cyc:
                    raise InvalidDependencyGraph("의존 순환 차단: " + "->".join(cyc))
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

    # ── System State Snapshot (이벤트 소싱) ──
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
        rec = SystemSnapshotEvent(
            event_id=eid, snapshot_id=sid, name=meta["name"], epoch=meta["epoch"],
            layers=meta["layers"], layer_count=meta["layer_count"],
            health_score=meta["health_score"], conflict_count=meta["conflict_count"],
            system_hash=meta["system_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(sid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_event_exists(eid):
            head = ledger.snapshots_head()
            ledger.append_snapshot_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_system_snapshot(self, name: str, epoch: str = "", metrics: dict | None = None,
                             now: str = "", *, commit: bool = False) -> SystemSnapshotEvent:
        """전 계층 시스템 상태를 스냅샷(CREATED). health_score/conflict_count 는 정보용·결정적."""
        layers = sorted(l.get("layer_id") for l in ledger.distinct_layers())
        hscore = health_score(dict(metrics or {}))
        conflicts = len(ledger.read_conflicts())
        sh = _system_hash(layers, hscore, conflicts)
        sid = _snapshot_id(name, epoch)
        existing = ledger.snapshot_events_for(sid)
        if existing:
            return SystemSnapshotEvent(**existing[-1])
        meta = {"snapshot_id": sid, "name": name, "epoch": epoch, "layers": layers,
                "layer_count": len(layers), "health_score": hscore, "conflict_count": conflicts,
                "system_hash": sh}
        rec = self._emit_snapshot_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        return SystemSnapshotEvent(**rec)

    def advance_snapshot(self, snapshot_id: str, now: str = "", *, commit: bool = False) -> dict:
        """CREATED→GENERATED→VERIFIED 로 한 단계 진행(정보용 상태만)."""
        meta = self._snapshot_meta(snapshot_id)
        if meta is None:
            raise UnknownSnapshot(f"미존재 스냅샷 {snapshot_id}")
        cur = self.snapshot_state(snapshot_id)
        nxt = {CREATED: GENERATED, GENERATED: VERIFIED}.get(cur)
        if nxt:
            self._emit_snapshot_event(meta, cur, nxt, now, commit=commit)
        return {"snapshot_id": snapshot_id, "state": self.snapshot_state(snapshot_id)}

    # ── Cross Layer Conflict (불변) ──
    def detect_conflicts(self, conflicts: list | None = None, now: str = "",
                       *, commit: bool = False) -> list:
        """교차계층 충돌 기록. category 검증. 의존 순환은 자동 충돌로 추가. **탐지·기록만.**"""
        out: list = []
        specs = list(conflicts or [])
        # 의존 그래프 순환을 자동 충돌 후보로 추가
        cyc = self.dependency_cycle()
        if cyc and len(cyc) >= 2:
            specs.append((cyc[0], cyc[1], "dependency_cycle", "HIGH",
                          "의존 순환: " + "->".join(cyc), list(cyc)))
        for spec in specs:
            layer_a, layer_b = spec[0], spec[1]
            category = spec[2] if len(spec) > 2 else "state_inconsistency"
            severity = spec[3] if len(spec) > 3 else "MEDIUM"
            detail = spec[4] if len(spec) > 4 else ""
            evidence = list(spec[5]) if len(spec) > 5 else []
            if category not in CONFLICT_CATEGORIES:
                raise InvalidConflictCategory(f"미등록 충돌 범주 {category}")
            cid = _conflict_id(layer_a, layer_b, category)
            if ledger.conflict_exists(cid):
                existing = next(c for c in ledger.read_conflicts()
                                if c.get("conflict_id") == cid)
                out.append(ConflictRecord(**{k: v for k, v in existing.items()
                                             if k in ConflictRecord.__dataclass_fields__}))
                continue
            rec = ConflictRecord(
                conflict_id=cid, layer_a=layer_a, layer_b=layer_b, category=category,
                severity=severity, detail=detail, evidence=evidence, created_at=now,
                input_hash=input_digest(layer_a, layer_b, category),
                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.conflict_exists(cid):
                head = ledger.conflicts_head()
                ledger.append_conflict(_seal(rec, head["record_hash"] if head else GENESIS))
            parent = _artifact_id(ART_LAYER, _layer_id(layer_a)) if ledger.artifact_exists(
                _artifact_id(ART_LAYER, _layer_id(layer_a))) else ""
            self._record_artifact(ART_CONFLICT, cid, parent, now, commit=commit)
            out.append(ConflictRecord(**rec))
        return out

    # ── Governance Health Summary + Orchestration Report ──
    def generate_health_report(self, scope: str = "GLOBAL", metrics: dict | None = None,
                             epoch: str = "", now: str = "",
                             *, commit: bool = False) -> HealthSummary:
        """거버넌스 건강 요약(go_health)과 오케스트레이션 리포트(go_reports)를 생성. **정보용 — 집행 없음.**"""
        m = dict(metrics or {})
        layers = ledger.distinct_layers()
        monitored = sum(1 for l in layers if self.layer_state(l.get("layer_id")) == MONITORED)
        if "layer_availability" not in m and layers:
            m["layer_availability"] = round(monitored / len(layers), 8)
        conflicts = ledger.read_conflicts()
        hscore = health_score(m)
        health = system_health(m)
        hid = _health_id(scope, epoch)
        summary = HealthSummary(
            health_id=hid, scope=scope, epoch=epoch, layer_count=len(layers),
            monitored_layer_count=monitored, metrics=m, health_score=hscore, system_health=health,
            conflict_count=len(conflicts), disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope, epoch), previous_hash=GENESIS).to_dict()
        summary["record_hash"] = content_hash(summary)
        if commit and not ledger.health_exists(hid):
            head = ledger.health_head()
            ledger.append_health(_seal(summary, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_HEALTH, hid, "", now, commit=commit)
        self._emit_report(scope, m, hscore, health, now, commit=commit)
        return HealthSummary(**summary)

    def _emit_report(self, scope: str, metrics: dict, hscore: float, health: str, now: str,
                     *, commit: bool) -> dict:
        layers = ledger.distinct_layers()
        lstate: dict = {}
        for l in layers:
            st = self.layer_state(l.get("layer_id"))
            lstate[st] = lstate.get(st, 0) + 1
        statuses = ledger.read_status()
        slabel: dict = {}
        for s in statuses:
            slabel[s.get("status")] = slabel.get(s.get("status"), 0) + 1
        conflicts = ledger.read_conflicts()
        cc_dist: dict = {}
        for c in conflicts:
            cc_dist[c.get("category")] = cc_dist.get(c.get("category"), 0) + 1
        rid = _report_id(scope)
        rec = OrchestrationReport(
            report_id=rid, scope=scope, layer_count=len(layers),
            layer_state_distribution=dict(sorted(lstate.items())), status_count=len(statuses),
            status_label_distribution=dict(sorted(slabel.items())),
            dependency_count=len(ledger.read_dependencies()),
            snapshot_count=len(ledger.distinct_snapshots()), conflict_count=len(conflicts),
            conflict_category_distribution=dict(sorted(cc_dist.items())), metrics=dict(metrics),
            health_score=hscore, system_health=health, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return rec

    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                      *, commit: bool = False) -> OrchestrationReport:
        m = dict(metrics or {})
        return OrchestrationReport(**self._emit_report(scope, m, health_score(m),
                                                       system_health(m), now, commit=commit))

    # ── 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """건강 지표 → SCORE/HEALTH. **AGGREGATION ≠ ACTION — 집행 신호 아님.**"""
        return {"health_score": health_score(metrics), "system_health": system_health(metrics)}

    # ── 계보/무결성 검증 ──
    def verify_integrity(self) -> dict:
        """오케스트레이션 계보(아티팩트 parent 체인)·의존 순환 무결성. **읽기 전용.**"""
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
        dep_cyc = self.dependency_cycle()
        if dep_cyc:
            issues.append("dependency_cycle:" + "->".join(dep_cyc))
        return {"ok": not issues, "issues": sorted(set(issues)), "n_artifacts": len(arts)}

    def trace_lineage(self, artifact_ref: str) -> list:
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

    # ── Summary (Research OS Status) ──
    def summary(self, now: str = "") -> OrchestrationSummary:
        layers = ledger.distinct_layers()
        lstate: dict = {}
        for l in layers:
            st = self.layer_state(l.get("layer_id"))
            lstate[st] = lstate.get(st, 0) + 1
        return OrchestrationSummary(
            timestamp=now, layer_count=len(layers),
            layer_state_distribution=dict(sorted(lstate.items())),
            status_count=len(ledger.read_status()),
            dependency_count=len(ledger.read_dependencies()),
            snapshot_count=len(ledger.distinct_snapshots()),
            health_summary_count=len(ledger.read_health()),
            conflict_count=len(ledger.read_conflicts()),
            report_count=len(ledger.read_reports()))

