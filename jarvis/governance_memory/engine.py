"""Governance Memory Engine (P10.21) — 재사용 거버넌스 지식 저장·분석·조회. **저장·분석·조회 전용.**

P9.8~P10.20 연구 거버넌스 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 지식 항목·경험·교훈·해소
이력·메모리 링크·스냅샷·지식 리포트·계보를 저장한다. **의사결정 실행·정책 변경·config 수정·strategy 승인·
model 배포 없음.** execution/broker/order/portfolio execution/capital allocation/live trading/permission/
risk controller import·호출 없음. MEMORY ≠ AUTHORITY · SIMILARITY ≠ DECISION · HISTORICAL PATTERN ≠ FUTURE
ACTION · KNOWLEDGE ≠ PERMISSION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.governance_memory import ledger
from jarvis.governance_memory.models import (
    ACYCLIC_LINK_TYPES,
    ART_ENTRY,
    ART_EXPERIENCE,
    ART_LAYER,
    ART_LESSON,
    ART_LINK,
    ART_REPORT,
    ART_RESOLUTION,
    ART_SNAPSHOT,
    ENTRY_CATEGORIES,
    GENESIS,
    LINK_TYPES,
    ExperienceRecord,
    ImmutableEntryError,
    ImmutableExperienceError,
    ImmutableLessonError,
    ImmutableResolutionError,
    InvalidEntryCategory,
    InvalidLinkType,
    InvalidMemoryLink,
    KnowledgeEntry,
    KnowledgeReport,
    LessonRecord,
    MemoryArtifact,
    MemoryLink,
    MemorySnapshot,
    MemorySummary,
    ResolutionHistory,
    artifact_id as _artifact_id,
    connected_components,
    content_hash,
    detect_cycle,
    entry_id as _entry_id,
    experience_id as _experience_id,
    input_digest,
    knowledge_content_hash,
    lesson_id as _lesson_id,
    link_id as _link_id,
    memory_health,
    memory_score,
    metadata_hash as _metadata_hash,
    report_id as _report_id,
    resolution_id as _resolution_id,
    snapshot_hash as _snapshot_hash,
    snapshot_id as _snapshot_id,
)

_DISCLAIMER = ("거버넌스 지식 메모리 — MEMORY ≠ AUTHORITY · SIMILARITY ≠ DECISION · HISTORICAL "
               "PATTERN ≠ FUTURE ACTION · KNOWLEDGE ≠ PERMISSION. 실행/정책변경/승인/배포 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class GovernanceMemoryEngine:
    """거버넌스 지식 메모리 엔진. 불변·append-only·결정적. 실행/변경/승인/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = MemoryArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_layer_artifact(self, source_layer: str, now: str, *, commit: bool) -> str:
        return self._record_artifact(ART_LAYER, source_layer, "", now,
                                     commit=commit)["artifact_id"]

    def _known_refs(self) -> set:
        """메모리 객체 참조 집합(entry/experience/lesson/resolution)."""
        refs: set = set()
        refs.update(r.get("entry_id") for r in ledger.read_entries())
        refs.update(r.get("experience_id") for r in ledger.read_experiences())
        refs.update(r.get("lesson_id") for r in ledger.read_lessons())
        refs.update(r.get("resolution_id") for r in ledger.read_resolutions())
        return refs

    # ── Experience Record (불변) ──
    def record_experience(self, event_reference: str, outcome: str = "INCONCLUSIVE",
                        impact: str = "MEDIUM", detail: str = "", source_layer: str = "",
                        now: str = "", *, commit: bool = False) -> ExperienceRecord:
        """거버넌스 경험을 불변 기록. **저장만 — 실행/승인 없음.**"""
        xid = _experience_id(event_reference)
        existing = ledger.get_experience(xid)
        if existing is not None:
            if existing.get("outcome") != outcome or existing.get("impact") != impact:
                raise ImmutableExperienceError(f"{xid} 경험 불변 — 변경 불가")
            return ExperienceRecord(**{k: v for k, v in existing.items()
                                       if k in ExperienceRecord.__dataclass_fields__})
        parent = ""
        if source_layer:
            self._ensure_layer_artifact(source_layer, now, commit=commit)
            parent = _artifact_id(ART_LAYER, source_layer)
        rec = ExperienceRecord(
            experience_id=xid, event_reference=event_reference, outcome=outcome, impact=impact,
            detail=detail, timestamp=now, created_at=now, input_hash=input_digest(event_reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.experience_exists(xid):
            head = ledger.experiences_head()
            ledger.append_experience(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_EXPERIENCE, xid, parent, now, commit=commit)
        return ExperienceRecord(**rec)

    # ── Lesson Record (불변) ──
    def store_lesson(self, observation: str, conclusion: str, evidence: list | None = None,
                   experience_ref: str = "", now: str = "",
                   *, commit: bool = False) -> LessonRecord:
        """교훈을 불변 기록. **저장만.**"""
        lid = _lesson_id(observation, conclusion)
        existing = ledger.get_lesson(lid)
        if existing is not None:
            return LessonRecord(**{k: v for k, v in existing.items()
                                   if k in LessonRecord.__dataclass_fields__})
        rec = LessonRecord(
            lesson_id=lid, observation=observation, conclusion=conclusion,
            evidence=list(evidence or []), created_at=now,
            input_hash=input_digest(observation, conclusion), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.lesson_exists(lid):
            head = ledger.lessons_head()
            ledger.append_lesson(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_EXPERIENCE, experience_ref) if experience_ref and \
            ledger.artifact_exists(_artifact_id(ART_EXPERIENCE, experience_ref)) else ""
        self._record_artifact(ART_LESSON, lid, parent, now, commit=commit)
        return LessonRecord(**rec)

    # ── Knowledge Entry (불변) ──
    def create_entry(self, category: str, source_reference: str, content=None,
                   metadata: dict | None = None, lesson_ref: str = "", now: str = "",
                   *, commit: bool = False) -> KnowledgeEntry:
        """지식 항목을 불변 등록. category 검증. 동일 id·상이 content → 불변 위반. **저장만.**"""
        if category not in ENTRY_CATEGORIES:
            raise InvalidEntryCategory(f"미등록 지식 항목 범주 {category}")
        eid = _entry_id(category, source_reference)
        ch = knowledge_content_hash(content if content is not None else source_reference)
        existing = ledger.get_entry(eid)
        if existing is not None:
            if existing.get("content_hash") != ch:
                raise ImmutableEntryError(f"{eid} 지식 항목 불변 — 변경 불가")
            return KnowledgeEntry(**{k: v for k, v in existing.items()
                                     if k in KnowledgeEntry.__dataclass_fields__})
        rec = KnowledgeEntry(
            entry_id=eid, category=category, source_reference=source_reference, content_hash=ch,
            metadata=dict(metadata or {}), created_at=now,
            input_hash=input_digest(category, source_reference), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.entry_exists(eid):
            head = ledger.entries_head()
            ledger.append_entry(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_LESSON, lesson_ref) if lesson_ref and \
            ledger.artifact_exists(_artifact_id(ART_LESSON, lesson_ref)) else ""
        self._record_artifact(ART_ENTRY, eid, parent, now, commit=commit)
        return KnowledgeEntry(**rec)

    # ── Resolution History (불변) ──
    def record_resolution(self, original_issue: str, historical_response: str,
                        outcome: str = "INCONCLUSIVE", now: str = "",
                        *, commit: bool = False) -> ResolutionHistory:
        """반복 이슈의 과거 해소 이력을 불변 기록. **기록 전용 — 실행 없음.**"""
        rid = _resolution_id(original_issue, historical_response)
        for r in ledger.read_resolutions():
            if r.get("resolution_id") == rid:
                return ResolutionHistory(**{k: v for k, v in r.items()
                                            if k in ResolutionHistory.__dataclass_fields__})
        rec = ResolutionHistory(
            resolution_id=rid, original_issue=original_issue,
            historical_response=historical_response, outcome=outcome, created_at=now,
            input_hash=input_digest(original_issue, historical_response),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.resolution_exists(rid):
            head = ledger.resolutions_head()
            ledger.append_resolution(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_RESOLUTION, rid, "", now, commit=commit)
        return ResolutionHistory(**rec)

    # ── Memory Link (지식 관계 그래프) ──
    def link_memory(self, from_ref: str, link_type: str, to_ref: str, now: str = "",
                  *, commit: bool = False) -> MemoryLink:
        """메모리 링크 생성. 유형·미등록 노드·자기참조 검증 + derived_from 순환 차단."""
        if link_type not in LINK_TYPES:
            raise InvalidLinkType(f"미등록 링크 유형 {link_type}")
        if from_ref == to_ref:
            raise InvalidMemoryLink(f"자기참조 링크 차단 {from_ref}")
        known = self._known_refs()
        if from_ref not in known:
            raise InvalidMemoryLink(f"미등록 메모리 참조 {from_ref}")
        if to_ref not in known:
            raise InvalidMemoryLink(f"미등록 메모리 참조 {to_ref}")
        lid = _link_id(from_ref, link_type, to_ref)
        if not ledger.link_exists(lid) and link_type in ACYCLIC_LINK_TYPES:
            edges = [(l.get("from_ref"), l.get("to_ref")) for l in ledger.read_links()
                     if l.get("link_type") in ACYCLIC_LINK_TYPES]
            cyc = detect_cycle(edges + [(from_ref, to_ref)])
            if cyc:
                raise InvalidMemoryLink("derived_from 순환 차단: " + "->".join(cyc))
        rec = MemoryLink(
            link_id=lid, from_ref=from_ref, link_type=link_type, to_ref=to_ref, created_at=now,
            input_hash=input_digest(from_ref, link_type, to_ref),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.link_exists(lid):
            head = ledger.links_head()
            ledger.append_link(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_LINK, lid, "", now, commit=commit)
        return MemoryLink(**rec)

    def link_cycle(self) -> list:
        """derived_from 서브그래프의 순환(있으면)."""
        edges = [(l.get("from_ref"), l.get("to_ref")) for l in ledger.read_links()
                 if l.get("link_type") in ACYCLIC_LINK_TYPES]
        return detect_cycle(edges)

    # ── Retrieval (조회) ──
    def find_related(self, ref: str, link_type: str = "") -> list:
        """ref 에 연결된 메모리 참조(양방향). link_type 지정 시 해당 유형만. **조회 전용.**"""
        out: set = set()
        for l in ledger.read_links():
            if link_type and l.get("link_type") != link_type:
                continue
            if l.get("from_ref") == ref:
                out.add(l.get("to_ref"))
            elif l.get("to_ref") == ref:
                out.add(l.get("from_ref"))
        return sorted(out)

    def similar_entries(self, entry_id: str) -> list:
        """동일 category 의 다른 지식 항목(결정적 유사도). **SIMILARITY ≠ DECISION.**"""
        e = ledger.get_entry(entry_id)
        if e is None:
            return []
        return sorted(o.get("entry_id") for o in ledger.entries_by_category(e.get("category"))
                      if o.get("entry_id") != entry_id)

    def search(self, ref: str) -> dict:
        """ref 관련 지식 검색: 링크 이웃 + 동일 범주 유사 항목. **조회 전용.**"""
        return {"ref": ref, "related": self.find_related(ref),
                "similar_entries": self.similar_entries(ref),
                "note": "조회 결과 — MEMORY ≠ AUTHORITY"}

    # ── Memory Snapshot (불변·결정적) ──
    def create_snapshot(self, name: str, epoch: str = "", collected_entries: list | None = None,
                      summary: dict | None = None, now: str = "",
                      *, commit: bool = False) -> MemorySnapshot:
        """지식 항목·요약을 결정적 스냅샷으로 고정. 동일 (name, epoch) → 동일 스냅샷."""
        ce = sorted(collected_entries or [])
        smy = dict(summary or {})
        sid = _snapshot_id(name, epoch)
        existing = ledger.get_snapshot(sid)
        if existing is not None:
            return MemorySnapshot(**{k: v for k, v in existing.items()
                                     if k in MemorySnapshot.__dataclass_fields__})
        sh = _snapshot_hash(ce, smy)
        rec = MemorySnapshot(
            snapshot_id=sid, name=name, epoch=epoch, collected_entries=ce, summary=smy,
            entry_count=len(ce), snapshot_hash=sh, created_at=now,
            input_hash=input_digest(name, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.snapshot_exists(sid):
            head = ledger.snapshots_head()
            ledger.append_snapshot(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for eref in ce:
            cand = _artifact_id(ART_ENTRY, eref)
            if ledger.artifact_exists(cand):
                parent = cand
                break
        self._record_artifact(ART_SNAPSHOT, sid, parent, now, commit=commit)
        return MemorySnapshot(**rec)

    # ── 메모리 인텔리전스 ──
    def knowledge_clusters(self) -> list:
        """링크 그래프 연결 요소(재발 지식 클러스터)."""
        edges = [(l.get("from_ref"), l.get("to_ref")) for l in ledger.read_links()]
        return connected_components(edges)

    def lesson_frequency(self) -> dict:
        """결론(conclusion)별 교훈 빈도(정보용)."""
        out: dict = {}
        for l in ledger.read_lessons():
            out[l.get("conclusion")] = out.get(l.get("conclusion"), 0) + 1
        return dict(sorted(out.items()))

    def knowledge_gaps(self) -> list:
        """링크가 전무한 지식 항목(미연결 지식 gap). **정보용 — 개입 없음.**"""
        linked: set = set()
        for l in ledger.read_links():
            linked.add(l.get("from_ref"))
            linked.add(l.get("to_ref"))
        return sorted(e.get("entry_id") for e in ledger.read_entries()
                      if e.get("entry_id") not in linked)

    def analyze(self, metrics: dict) -> dict:
        """메모리 지표 → SCORE/HEALTH. **MEMORY ≠ AUTHORITY — 권한 신호 아님.**"""
        return {"memory_score": memory_score(metrics), "memory_health": memory_health(metrics)}

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """메모리 계보(아티팩트 parent 체인): dangling parent·순환 탐지 + 링크 순환. **읽기 전용.**"""
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
        lcyc = self.link_cycle()
        if lcyc:
            issues.append("link_cycle:" + "->".join(lcyc))
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

    # ── Knowledge Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                      *, commit: bool = False) -> KnowledgeReport:
        m = dict(metrics or {})
        entries = ledger.read_entries()
        cat_dist: dict = {}
        for e in entries:
            cat_dist[e.get("category")] = cat_dist.get(e.get("category"), 0) + 1
        links = ledger.read_links()
        lt_dist: dict = {}
        for l in links:
            lt_dist[l.get("link_type")] = lt_dist.get(l.get("link_type"), 0) + 1
        clusters = self.knowledge_clusters()
        largest = max((len(c) for c in clusters), default=0)
        rid = _report_id(scope)
        rec = KnowledgeReport(
            report_id=rid, scope=scope, entry_count=len(entries),
            entry_category_distribution=dict(sorted(cat_dist.items())),
            experience_count=len(ledger.read_experiences()),
            lesson_count=len(ledger.read_lessons()),
            resolution_count=len(ledger.read_resolutions()), link_count=len(links),
            link_type_distribution=dict(sorted(lt_dist.items())), cluster_count=len(clusters),
            largest_cluster_size=largest, knowledge_gap_count=len(self.knowledge_gaps()),
            snapshot_count=len(ledger.read_snapshots()), metrics=m, memory_score=memory_score(m),
            memory_health=memory_health(m), disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return KnowledgeReport(**rec)

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
    def summary(self, now: str = "") -> MemorySummary:
        entries = ledger.read_entries()
        cat_dist: dict = {}
        for e in entries:
            cat_dist[e.get("category")] = cat_dist.get(e.get("category"), 0) + 1
        links = ledger.read_links()
        lt_dist: dict = {}
        for l in links:
            lt_dist[l.get("link_type")] = lt_dist.get(l.get("link_type"), 0) + 1
        return MemorySummary(
            timestamp=now, entry_count=len(entries),
            entry_category_distribution=dict(sorted(cat_dist.items())),
            experience_count=len(ledger.read_experiences()),
            lesson_count=len(ledger.read_lessons()),
            resolution_count=len(ledger.read_resolutions()), link_count=len(links),
            link_type_distribution=dict(sorted(lt_dist.items())),
            snapshot_count=len(ledger.read_snapshots()),
            report_count=len(ledger.read_reports()))
