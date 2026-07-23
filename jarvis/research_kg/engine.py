"""Research Knowledge Graph Engine (P10.5) — 연구 엔티티·관계·계보·유사도·스냅샷. **분석 전용.**

P9.8~P10.4 연구 원장을 **READ ONLY** 로 연결(ingest)해 지식 그래프를 구성한다. 엔티티 등록(불변)·
관계 링크(규칙 검증·순환 차단)·계보 파생·유사도 분석(서술적 라벨)·그래프 스냅샷을 남긴다.
**실행/배포/주문/자본배분/모델적용 권한 없음.** execution/broker/portfolio mutation/risk governor/
permission/live trading import·변경 없음. VALIDATED ≠ DEPLOYED · RANKED ≠ SELECTED ·
CONNECTED ≠ ENABLED. 결정적·append-only. 상위 레이어 파일은 읽기만 한다.
"""
from __future__ import annotations

from jarvis.research_kg import ledger
from jarvis.research_kg.models import (
    ANALYZED,
    ART_ENTITY,
    ART_RELATIONSHIP,
    ART_SNAPSHOT,
    DATASET,
    DERIVED_FROM,
    GENESIS,
    LINKED,
    REGISTERED,
    SIGNAL,
    SNAPSHOTTED,
    STRATEGY,
    CycleError,
    EntityEvent,
    GraphArtifact,
    GraphSnapshot,
    IllegalTransition,
    ImmutableEntityError,
    InvalidRelationship,
    LineageEdge,
    Relationship,
    ResearchGraphReport,
    SimilarityReport,
    UnknownEntity,
    artifact_id as _artifact_id,
    can_transition,
    connected_components,
    content_hash,
    detect_cycle,
    entity_event_id,
    entity_id as _entity_id,
    graph_hash as _graph_hash,
    input_digest,
    lineage_edge_id as _lineage_edge_id,
    longest_path_depth,
    metadata_hash as _metadata_hash,
    relationship_allowed,
    relationship_id as _relationship_id,
    similarity_level,
    similarity_report_id as _similarity_report_id,
    snapshot_id as _snapshot_id,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchKnowledgeGraphEngine:
    """지식 그래프 엔진. 불변·append-only·결정적. 실행/배포/선택/적용 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = GraphArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── 엔티티 상태(이벤트 소싱) ──
    def entity_state(self, entity_key: str) -> str:
        evs = ledger.entity_events_for(entity_key)
        return evs[-1].get("to_state", "") if evs else ""

    def _entity_meta(self, entity_key: str) -> dict | None:
        evs = ledger.entity_events_for(entity_key)
        return evs[0] if evs else None

    def _emit_entity_event(self, meta: dict, frm: str, to: str, now: str,
                           *, commit: bool) -> dict:
        if not can_transition(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단")
        ekey = meta["entity_id"]
        eid = entity_event_id(ekey, frm, to)
        rec = EntityEvent(
            event_id=eid, entity_key=ekey, entity_id=ekey, entity_type=meta["entity_type"],
            source_layer=meta["source_layer"], source_id=meta["source_id"],
            metadata_hash=meta["metadata_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(ekey, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.entity_event_exists(eid):
            head = ledger.entities_head()
            ledger.append_entity_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_entity(self, entity_type: str, source_layer: str, source_id: str,
                        metadata: dict | None = None, now: str = "",
                        *, commit: bool = False) -> EntityEvent:
        """연구 엔티티를 그래프 노드로 등록(불변). REGISTERED 상태 이벤트를 남긴다."""
        eid = _entity_id(entity_type, source_layer, source_id)
        mh = _metadata_hash(metadata or {})
        existing = ledger.entity_events_for(eid)
        if existing:
            if existing[0].get("metadata_hash") != mh:
                raise ImmutableEntityError(f"{eid} 엔티티 불변 — 메타데이터 변경 불가")
            return EntityEvent(**existing[-1])
        meta = {"entity_id": eid, "entity_type": entity_type, "source_layer": source_layer,
                "source_id": source_id, "metadata_hash": mh}
        rec = self._emit_entity_event(meta, "", REGISTERED, now, commit=commit)
        self._record_artifact(ART_ENTITY, eid, "", now, commit=commit)
        return EntityEvent(**rec)

    def _safe_advance(self, entity_key: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._entity_meta(entity_key)
        if meta is None:
            return
        cur = self.entity_state(entity_key)
        if cur != to and can_transition(cur, to):
            self._emit_entity_event(meta, cur, to, now, commit=commit)

    def _entity_type_of(self, entity_id: str) -> str | None:
        meta = self._entity_meta(entity_id)
        return meta.get("entity_type") if meta else None

    # ── 관계 링크(규칙 검증·순환 차단) ──
    def link_relationship(self, source_entity: str, rel_type: str, target_entity: str,
                          now: str = "", *, commit: bool = False) -> Relationship:
        s_type = self._entity_type_of(source_entity)
        t_type = self._entity_type_of(target_entity)
        if s_type is None:
            raise UnknownEntity(f"미등록 source 엔티티 {source_entity}")
        if t_type is None:
            raise UnknownEntity(f"미등록 target 엔티티 {target_entity}")
        if not relationship_allowed(s_type, rel_type, t_type):
            raise InvalidRelationship(f"{s_type} -{rel_type}-> {t_type} 규칙 위반")
        rid = _relationship_id(source_entity, rel_type, target_entity)
        # 순환 방지: 기존 관계 엣지 + 신규 엣지에 사이클이 생기면 차단.
        edges = [(r.get("source_entity"), r.get("target_entity"))
                 for r in ledger.read_relationships()]
        if not ledger.relationship_exists(rid):
            cyc = detect_cycle(edges + [(source_entity, target_entity)])
            if cyc:
                raise CycleError("관계 순환 차단: " + "->".join(cyc))
        rec = Relationship(
            relationship_id=rid, source_entity=source_entity, source_type=s_type,
            rel_type=rel_type, target_entity=target_entity, target_type=t_type, created_at=now,
            input_hash=input_digest(source_entity, rel_type, target_entity),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.relationship_exists(rid):
            head = ledger.relationships_head()
            ledger.append_relationship(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_RELATIONSHIP, rid, _artifact_id(ART_ENTITY, source_entity),
                              now, commit=commit)
        self._safe_advance(source_entity, LINKED, now, commit=commit)
        self._safe_advance(target_entity, LINKED, now, commit=commit)
        return Relationship(**rec)

    # ── 계보 엣지(정방향 흐름) ──
    def record_lineage_edge(self, from_entity: str, to_entity: str, edge_type: str,
                            now: str = "", *, commit: bool = False) -> LineageEdge:
        lid = _lineage_edge_id(from_entity, to_entity, edge_type)
        rec = LineageEdge(
            lineage_id=lid, from_entity=from_entity, to_entity=to_entity, edge_type=edge_type,
            created_at=now, input_hash=input_digest(from_entity, to_entity, edge_type),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lineage_exists(lid):
            head = ledger.lineage_head()
            ledger.append_lineage_edge(_seal(rec, head["record_hash"] if head else GENESIS))
        return LineageEdge(**rec)

    def build_lineage(self, now: str = "", *, commit: bool = False) -> list[LineageEdge]:
        """관계로부터 정방향 계보(Dataset→Feature→Signal→Strategy→Experiment→Backtest→
        Portfolio)를 파생한다. 각 관계의 target(상류) → source(하류) 방향으로 계보 엣지 생성."""
        out: list[LineageEdge] = []
        for r in ledger.read_relationships():
            src = r.get("source_entity")
            tgt = r.get("target_entity")
            edge_type = f"{r.get('target_type')}->{r.get('source_type')}"
            out.append(self.record_lineage_edge(tgt, src, edge_type, now, commit=commit))
        return out

    def trace_lineage(self, entity_id: str) -> list[str]:
        """entity 의 상류 계보 조상 경로(계보 엣지 역방향 도달 노드)."""
        rev: dict = {}
        for e in ledger.read_lineage_edges():
            rev.setdefault(e.get("to_entity"), set()).add(e.get("from_entity"))
        seen: list = []
        stack = [entity_id]
        visited: set = set()
        while stack:
            n = stack.pop()
            for anc in sorted(rev.get(n, ())):
                if anc not in visited:
                    visited.add(anc)
                    seen.append(anc)
                    stack.append(anc)
        return seen

    # ── 유사도 분석(서술적 — 자동 제거/선택 아님) ──
    def analyze_similarity(self, entity_a: str, entity_b: str, score: float, basis: str = "",
                           now: str = "", *, commit: bool = False) -> SimilarityReport:
        rid = _similarity_report_id(entity_a, entity_b)
        t_a = self._entity_type_of(entity_a)
        t_b = self._entity_type_of(entity_b)
        etype = t_a if t_a == t_b and t_a is not None else "MIXED"
        level = similarity_level(score)
        rec = SimilarityReport(
            report_id=rid, entity_a=entity_a, entity_b=entity_b, entity_type=etype,
            score=round(float(score), 8), level=level, basis=basis, created_at=now,
            input_hash=input_digest(*sorted((entity_a, entity_b))),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.similarity_exists(rid):
            head = ledger.similarity_head()
            ledger.append_similarity(_seal(rec, head["record_hash"] if head else GENESIS))
        for e in (entity_a, entity_b):
            self._safe_advance(e, LINKED, now, commit=commit)
            self._safe_advance(e, ANALYZED, now, commit=commit)
        return SimilarityReport(**rec)

    # ── 그래프 스냅샷 ──
    def snapshot_graph(self, now: str = "", *, commit: bool = False) -> GraphSnapshot:
        entities = ledger.distinct_entities()
        rels = ledger.read_relationships()
        lineage = ledger.read_lineage_edges()
        sims = ledger.read_similarity()
        ent_ids = [e.get("entity_id") for e in entities]
        edges = [(r.get("source_entity"), r.get("target_entity")) for r in rels]
        gh = _graph_hash(ent_ids, edges)
        ent_dist: dict = {}
        layer_dist: dict = {}
        for e in entities:
            ent_dist[e.get("entity_type")] = ent_dist.get(e.get("entity_type"), 0) + 1
            layer_dist[e.get("source_layer")] = layer_dist.get(e.get("source_layer"), 0) + 1
        sid = _snapshot_id(gh)
        rec = GraphSnapshot(
            snapshot_id=sid, node_count=len(ent_ids), edge_count=len(rels),
            lineage_edge_count=len(lineage), similarity_count=len(sims),
            entity_distribution=dict(sorted(ent_dist.items())),
            layer_distribution=dict(sorted(layer_dist.items())), graph_hash=gh, created_at=now,
            input_hash=gh, previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_SNAPSHOT, sid, "", now, commit=commit)
        # 스냅샷에 포함된(분석까지 도달한) 엔티티만 SNAPSHOTTED 로.
        for e in entities:
            if self.entity_state(e.get("entity_id")) == ANALYZED:
                self._safe_advance(e.get("entity_id"), SNAPSHOTTED, now, commit=commit)
        return GraphSnapshot(**rec)

    # ── 상위 레이어 READ ONLY ingest ──
    def ingest_from_sources(self, now: str = "", *, commit: bool = False,
                            limit: int = 0) -> dict:
        """상위 레이어 원장(P9.8~P10.4)을 읽기 전용으로 스캔해 엔티티로 등록한다.

        상위 파일에는 절대 쓰지 않는다 — read_source 로 읽기만. 반환: 레이어별 등록 수.
        """
        counts: dict = {}
        for layer, mapping in sorted(ledger.SOURCE_LEDGERS.items()):
            for etype, (filename, id_field) in sorted(mapping.items()):
                n = 0
                for row in ledger.read_source(filename):
                    sid = row.get(id_field)
                    if not sid:
                        continue
                    self.register_entity(etype, layer, str(sid), {"src": filename}, now,
                                         commit=commit)
                    n += 1
                    if limit and n >= limit:
                        break
                if n:
                    counts[f"{layer}:{etype}"] = n
        return counts

    # ── 그래프 지표(읽기전용) ──
    def _degree_map(self) -> dict:
        deg: dict = {}
        for r in ledger.read_relationships():
            for e in (r.get("source_entity"), r.get("target_entity")):
                deg[e] = deg.get(e, 0) + 1
        return deg

    def generate_graph_report(self, now: str = "") -> ResearchGraphReport:
        entities = ledger.distinct_entities()
        by_id = {e.get("entity_id"): e for e in entities}
        rels = ledger.read_relationships()
        lineage = ledger.read_lineage_edges()
        deg = self._degree_map()

        ent_dist: dict = {}
        layer_dist: dict = {}
        state_dist: dict = {}
        for e in entities:
            ent_dist[e.get("entity_type")] = ent_dist.get(e.get("entity_type"), 0) + 1
            layer_dist[e.get("source_layer")] = layer_dist.get(e.get("source_layer"), 0) + 1
            st = self.entity_state(e.get("entity_id"))
            state_dist[st] = state_dist.get(st, 0) + 1

        # most connected signals
        sig_deg = [(eid, deg.get(eid, 0)) for eid, e in by_id.items()
                   if e.get("entity_type") == SIGNAL]
        sig_deg.sort(key=lambda x: (-x[1], x[0]))
        most_connected_signals = [{"entity_id": eid, "degree": d}
                                  for eid, d in sig_deg[:5] if d > 0]

        # most reused datasets (DERIVED_FROM target)
        reuse: dict = {}
        for r in rels:
            if r.get("rel_type") == DERIVED_FROM and r.get("target_type") == DATASET:
                t = r.get("target_entity")
                reuse[t] = reuse.get(t, 0) + 1
        ds_reuse = sorted(reuse.items(), key=lambda x: (-x[1], x[0]))
        most_reused_datasets = [{"entity_id": eid, "reuse": c} for eid, c in ds_reuse[:5]]

        # strategy dependency depth (계보 상류 방향 최장 경로)
        rev_edges = [(e.get("to_entity"), e.get("from_entity")) for e in lineage]
        strat_depth: dict = {}
        for eid, e in by_id.items():
            if e.get("entity_type") == STRATEGY:
                d = longest_path_depth(eid, rev_edges)
                strat_depth[eid] = d

        # research clusters (무방향 연결요소)
        nodes = list(by_id)
        undirected = [(r.get("source_entity"), r.get("target_entity")) for r in rels]
        comps = connected_components(nodes, undirected)
        clusters = sum(1 for c in comps if len(c) > 1)

        # orphan entities (관계 없음)
        touched = set()
        for r in rels:
            touched.add(r.get("source_entity"))
            touched.add(r.get("target_entity"))
        orphans = sorted(eid for eid in by_id if eid not in touched)

        # broken lineage (미존재 엔티티 참조)
        broken = []
        for e in lineage:
            for ref in (e.get("from_entity"), e.get("to_entity")):
                if ref not in by_id:
                    broken.append(f"{e.get('lineage_id')}:{ref}")

        return ResearchGraphReport(
            timestamp=now, total_entities=len(entities),
            entity_distribution=dict(sorted(ent_dist.items())),
            layer_distribution=dict(sorted(layer_dist.items())),
            state_distribution=dict(sorted(state_dist.items())),
            relationship_count=len(rels), lineage_edge_count=len(lineage),
            snapshot_count=len(ledger.read_snapshots()),
            similarity_count=len(ledger.read_similarity()),
            most_connected_signals=most_connected_signals,
            most_reused_datasets=most_reused_datasets,
            strategy_dependency_depth=dict(sorted(strat_depth.items())),
            research_clusters=clusters, orphan_entities=orphans,
            broken_lineage=sorted(set(broken)))
