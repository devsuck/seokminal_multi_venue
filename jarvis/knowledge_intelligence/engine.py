"""Knowledge Intelligence Engine (P10.27) — 지식 그래프를 상위 인텔리전스로 확장. **분석·기록 전용.**

P10.5 Research Knowledge Graph·P10.21 Governance Memory·P10.26 Research Lifecycle 를 READ ONLY 로 참조
(파일 기반, import 없음)해 연구 유사도·실패 실험 검색·전략 패밀리 클러스터링·모순 탐지·지식 추천을 수행하고
지식 인사이트·유사도 리포트·클러스터·모순·연구 패턴을 남긴다. **권고는 정보용일 뿐 자동 선택·승인·배포 없음.**
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller
import·호출 없음. RECOMMENDATION ≠ ACTION · SIMILARITY ≠ SELECTION · CLUSTER ≠ APPROVAL · INSIGHT ≠ DEPLOYMENT.
상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.knowledge_intelligence import ledger
from jarvis.knowledge_intelligence.models import (
    ART_CLUSTER,
    ART_CONTRADICTION,
    ART_INSIGHT,
    ART_LAYER,
    ART_OBJECT,
    ART_PATTERN,
    ART_REPORT,
    ART_SIMILARITY,
    GENESIS,
    INSIGHT_CLUSTER,
    INSIGHT_CONTRADICTION,
    INSIGHT_PATTERN,
    INSIGHT_RECOMMENDATION,
    INSIGHT_SIMILARITY,
    INSIGHT_TYPES,
    P_COMMON_FAMILY,
    P_REPEATED_FAILURE,
    PATTERN_TYPES,
    ClusterRecord,
    ContradictionRecord,
    ImmutableContradictionError,
    ImmutableInsightError,
    ImmutablePatternError,
    ImmutableSimilarityError,
    InvalidInsightType,
    KnowledgeArtifact,
    KnowledgeInsight,
    KnowledgeReport,
    KnowledgeSummary,
    ResearchPattern,
    SimilarityRecord,
    artifact_id as _artifact_id,
    cluster_by_tokens,
    cluster_id as _cluster_id,
    content_hash,
    contradiction_id as _contradiction_id,
    detect_contradictions,
    detect_cycle,
    input_digest,
    insight_id as _insight_id,
    jaccard,
    members_hash as _members_hash,
    pattern_confidence,
    pattern_id as _pattern_id,
    report_id as _report_id,
    similarity_id as _similarity_id,
)

_DISCLAIMER = ("지식 인텔리전스 데이터 — RECOMMENDATION ≠ ACTION · SIMILARITY ≠ SELECTION · CLUSTER ≠ "
               "APPROVAL · INSIGHT ≠ DEPLOYMENT. 권고는 정보용 — 자동 선택/승인/배포 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class KnowledgeIntelligenceEngine:
    """상위 지식 인텔리전스 엔진. 불변·append-only·결정적. 선택/승인/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = KnowledgeArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _ensure_object(self, ref: str, now: str, *, commit: bool) -> str:
        return self._record_artifact(ART_OBJECT, ref, "", now, commit=commit)["artifact_id"]

    # ── research_similarity ──
    def research_similarity(self, ref_a: str, tokens_a: list, ref_b: str, tokens_b: list,
                          method: str = "jaccard", now: str = "",
                          *, commit: bool = False) -> SimilarityRecord:
        """두 연구 객체 유사도(결정적 Jaccard) 기록. **SIMILARITY ≠ SELECTION.**"""
        score = jaccard(tokens_a, tokens_b)
        sid = _similarity_id(ref_a, ref_b)
        existing = ledger.get_similarity(sid)
        if existing is not None:
            if abs(float(existing.get("score", 0.0)) - score) > 1e-9:
                raise ImmutableSimilarityError(f"{sid} 유사도 불변 — 변경 불가")
            return SimilarityRecord(**{k: v for k, v in existing.items()
                                       if k in SimilarityRecord.__dataclass_fields__})
        rec = SimilarityRecord(
            similarity_id=sid, ref_a=ref_a, ref_b=ref_b, score=score, method=method,
            created_at=now, input_hash=input_digest(ref_a, ref_b),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.similarity_exists(sid):
            head = ledger.similarity_head()
            ledger.append_similarity(_seal(rec, head["record_hash"] if head else GENESIS))
        self._ensure_object(ref_a, now, commit=commit)
        self._record_artifact(ART_SIMILARITY, sid, _artifact_id(ART_OBJECT, ref_a), now,
                              commit=commit)
        return SimilarityRecord(**rec)

    # ── failed_experiment_retrieval ──
    def failed_experiment_retrieval(self, source_layer: str = "governance_memory",
                                  marker_field: str = "category", marker_value: str = "failure_pattern",
                                  now: str = "", *, commit: bool = False) -> list:
        """상위 소스에서 실패 실험/패턴을 검색·반환하고 반복 실패 패턴을 기록. **검색·기록만.**"""
        spec = ledger.SOURCE_LEDGERS.get(source_layer)
        if not spec:
            return []
        filename, id_field = spec
        refs: list = []
        for r in ledger.read_source(filename):
            if str(r.get(marker_field, "")) == marker_value:
                rid = r.get(id_field)
                if rid:
                    refs.append(f"{source_layer}:{rid}")
        refs = sorted(set(refs))
        if refs and commit is not None:
            self.record_pattern(P_REPEATED_FAILURE, f"failures:{source_layer}", len(refs), refs,
                                now, commit=commit)
        return refs

    # ── strategy_family_clustering ──
    def strategy_family_clustering(self, items: list, min_shared: int = 1, now: str = "",
                                 *, commit: bool = False) -> list:
        """items=[(ref,[tokens])] 를 공유 토큰 기준으로 결정적 클러스터링. 클러스터 기록. **CLUSTER ≠ APPROVAL.**"""
        clusters = cluster_by_tokens(items, min_shared=min_shared)
        out: list = []
        for comp in clusters:
            family_key = comp[0] if comp else ""
            cid = _cluster_id(family_key, comp)
            existing = ledger.get_cluster(cid)
            if existing is not None:
                out.append(ClusterRecord(**{k: v for k, v in existing.items()
                                            if k in ClusterRecord.__dataclass_fields__}))
                continue
            rec = ClusterRecord(
                cluster_id=cid, family_key=family_key, members=comp, size=len(comp),
                members_hash=_members_hash(comp), created_at=now,
                input_hash=input_digest(family_key), previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.cluster_exists(cid):
                head = ledger.clusters_head()
                ledger.append_cluster(_seal(rec, head["record_hash"] if head else GENESIS))
            parent = _artifact_id(ART_OBJECT, family_key) if ledger.artifact_exists(
                _artifact_id(ART_OBJECT, family_key)) else ""
            self._record_artifact(ART_CLUSTER, cid, parent, now, commit=commit)
            out.append(ClusterRecord(**rec))
        return out

    # ── contradiction_detection ──
    def contradiction_detection(self, claims: list, now: str = "",
                              *, commit: bool = False) -> list:
        """claims=[{ref,subject,stance}] 에서 subject 별 상충(SUPPORTS/REFUTES) 탐지·기록. **탐지·기록만.**"""
        found = detect_contradictions(claims)
        out: list = []
        for c in found:
            subject = c["subject"]
            cid = _contradiction_id(subject)
            existing = ledger.get_contradiction(cid)
            if existing is not None:
                if existing.get("supporting") != c["supporting"] or \
                        existing.get("refuting") != c["refuting"]:
                    raise ImmutableContradictionError(f"{cid} 모순 불변 — 변경 불가")
                out.append(ContradictionRecord(**{k: v for k, v in existing.items()
                                                  if k in ContradictionRecord.__dataclass_fields__}))
                continue
            rec = ContradictionRecord(
                contradiction_id=cid, subject=subject, supporting=c["supporting"],
                refuting=c["refuting"], detail=f"{len(c['supporting'])} vs {len(c['refuting'])}",
                created_at=now, input_hash=input_digest(subject), previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.contradiction_exists(cid):
                head = ledger.contradictions_head()
                ledger.append_contradiction(_seal(rec, head["record_hash"] if head else GENESIS))
            self._record_artifact(ART_CONTRADICTION, cid, "", now, commit=commit)
            out.append(ContradictionRecord(**rec))
        return out

    # ── Research Pattern (불변) ──
    def record_pattern(self, pattern_type: str, subject: str, occurrences: int,
                     related_refs: list | None = None, now: str = "",
                     *, commit: bool = False) -> ResearchPattern:
        refs = sorted(set(related_refs or []))
        conf = pattern_confidence(int(occurrences), len(refs))
        pid = _pattern_id(pattern_type, subject)
        existing = ledger.get_pattern(pid)
        if existing is not None:
            if existing.get("related_refs") != refs or existing.get("occurrences") != int(occurrences):
                raise ImmutablePatternError(f"{pid} 연구 패턴 불변 — 변경 불가")
            return ResearchPattern(**{k: v for k, v in existing.items()
                                      if k in ResearchPattern.__dataclass_fields__})
        rec = ResearchPattern(
            pattern_id=pid, pattern_type=pattern_type, subject=subject,
            occurrences=int(occurrences), related_refs=refs, confidence=conf, created_at=now,
            input_hash=input_digest(pattern_type, subject), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PATTERN, pid, "", now, commit=commit)
        return ResearchPattern(**rec)

    # ── knowledge_recommendation (지식 인사이트) ──
    def knowledge_recommendation(self, subject: str, content: str, reference: str = "",
                               supporting_refs: list | None = None, confidence: float = 0.0,
                               now: str = "", *, commit: bool = False) -> KnowledgeInsight:
        """지식 추천(정보용 인사이트) 기록. **RECOMMENDATION ≠ ACTION — 자동 선택/승인/배포 없음.**"""
        return self.record_insight(INSIGHT_RECOMMENDATION, subject, content, reference,
                                  supporting_refs, confidence, now, commit=commit)

    def record_insight(self, insight_type: str, subject: str, content: str, reference: str = "",
                     supporting_refs: list | None = None, confidence: float = 0.0, now: str = "",
                     *, commit: bool = False) -> KnowledgeInsight:
        """지식 인사이트를 불변 기록. insight_type 검증. **INSIGHT ≠ DEPLOYMENT.**"""
        if insight_type not in INSIGHT_TYPES:
            raise InvalidInsightType(f"미등록 인사이트 유형 {insight_type}")
        iid = _insight_id(insight_type, subject, reference)
        existing = ledger.get_insight(iid)
        if existing is not None:
            if existing.get("content") != content:
                raise ImmutableInsightError(f"{iid} 인사이트 불변 — 변경 불가")
            return KnowledgeInsight(**{k: v for k, v in existing.items()
                                       if k in KnowledgeInsight.__dataclass_fields__})
        rec = KnowledgeInsight(
            insight_id=iid, insight_type=insight_type, subject=subject, reference=reference,
            content=content, supporting_refs=sorted(set(supporting_refs or [])),
            confidence=round(float(confidence), 8), created_at=now,
            input_hash=input_digest(insight_type, subject, reference),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.insight_exists(iid):
            head = ledger.insights_head()
            ledger.append_insight(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_INSIGHT, iid, "", now, commit=commit)
        return KnowledgeInsight(**rec)

    # ── 조회 편의 ──
    def most_similar(self, ref: str, threshold: float = 0.0) -> list:
        """ref 와 유사도 기록이 있는 상대 목록(점수 내림차순). **조회 전용.**"""
        out: list = []
        for s in ledger.read_similarity():
            if s.get("ref_a") == ref or s.get("ref_b") == ref:
                if float(s.get("score", 0.0)) >= threshold:
                    other = s.get("ref_b") if s.get("ref_a") == ref else s.get("ref_a")
                    out.append((other, float(s.get("score", 0.0))))
        return [o for o, _ in sorted(out, key=lambda x: (-x[1], x[0]))]

    def cluster_of(self, ref: str) -> list:
        """ref 가 속한 클러스터의 멤버(첫 매칭). **조회 전용.**"""
        for c in ledger.read_clusters():
            if ref in c.get("members", []):
                return c.get("members", [])
        return []

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """지식 인텔리전스 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
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
        insights = ledger.read_insights()
        it_dist: dict = {}
        for i in insights:
            it_dist[i.get("insight_type")] = it_dist.get(i.get("insight_type"), 0) + 1
        clusters = ledger.read_clusters()
        largest = max((int(c.get("size", 0)) for c in clusters), default=0)
        patterns = ledger.read_patterns()
        pt_dist: dict = {}
        for p in patterns:
            pt_dist[p.get("pattern_type")] = pt_dist.get(p.get("pattern_type"), 0) + 1
        rid = _report_id(scope)
        rec = KnowledgeReport(
            report_id=rid, scope=scope, insight_count=len(insights),
            insight_type_distribution=dict(sorted(it_dist.items())),
            similarity_count=len(ledger.read_similarity()), cluster_count=len(clusters),
            largest_cluster_size=largest, contradiction_count=len(ledger.read_contradictions()),
            pattern_count=len(patterns), pattern_type_distribution=dict(sorted(pt_dist.items())),
            recommendation_count=it_dist.get(INSIGHT_RECOMMENDATION, 0), metrics=m,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return KnowledgeReport(**rec)

    # ── 상위 소스 READ ONLY 조회 ──
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
    def summary(self, now: str = "") -> KnowledgeSummary:
        insights = ledger.read_insights()
        it_dist: dict = {}
        for i in insights:
            it_dist[i.get("insight_type")] = it_dist.get(i.get("insight_type"), 0) + 1
        return KnowledgeSummary(
            timestamp=now, insight_count=len(insights),
            insight_type_distribution=dict(sorted(it_dist.items())),
            similarity_count=len(ledger.read_similarity()),
            cluster_count=len(ledger.read_clusters()),
            contradiction_count=len(ledger.read_contradictions()),
            pattern_count=len(ledger.read_patterns()), report_count=len(ledger.read_reports()))
