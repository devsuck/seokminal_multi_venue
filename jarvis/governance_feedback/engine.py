"""Governance Feedback Engine (P10.20) — 거버넌스 폐루프 학습 기록. **분석·기록 전용, 변경 없음.**

P9.8~P10.19 연구 거버넌스 생태계를 READ ONLY 로 참조(파일 기반, import 없음)해 피드백·이슈·패턴·개선 테마·
집계·추세 리포트·계보를 남긴다. **정책 수정·permission 변경·config 변경·자동 이슈 수정·변경 승인·실행·배포
없음.** execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk
controller import·호출 없음. FEEDBACK ≠ CHANGE · PATTERN ≠ DECISION · RECOMMENDATION ≠ IMPLEMENTATION ·
TREND ≠ AUTOMATIC ACTION. 상위 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.governance_feedback import ledger
from jarvis.governance_feedback.models import (
    ANALYZED,
    ARCHIVED,
    ART_AGGREGATION,
    ART_FEEDBACK,
    ART_ISSUE,
    ART_LAYER,
    ART_PATTERN,
    ART_REPORT,
    ART_REVIEW,
    ART_THEME,
    DETECTED,
    FEEDBACK_CATEGORIES,
    GENESIS,
    REVIEW_DECISIONS,
    TRACKED,
    AggregationRecord,
    FeedbackArtifact,
    FeedbackRecord,
    FeedbackReview,
    FeedbackSummary,
    GovernanceIssueEvent,
    GovernanceTrendReport,
    IllegalTransition,
    ImmutableFeedbackError,
    ImmutablePatternError,
    ImmutableThemeError,
    ImprovementTheme,
    InvalidFeedbackCategory,
    InvalidReviewDecision,
    PatternRecord,
    UnknownIssue,
    aggregation_id as _aggregation_id,
    artifact_id as _artifact_id,
    can_transition_issue,
    content_hash,
    detect_cycle,
    feedback_id as _feedback_id,
    governance_health,
    governance_score,
    input_digest,
    issue_event_id,
    issue_id as _issue_id,
    metadata_hash as _metadata_hash,
    pattern_confidence,
    pattern_id as _pattern_id,
    report_id as _report_id,
    review_id as _review_id,
    theme_id as _theme_id,
    trend_label,
)

_DISCLAIMER = ("거버넌스 피드백 데이터 — FEEDBACK ≠ CHANGE · PATTERN ≠ DECISION · RECOMMENDATION ≠ "
               "IMPLEMENTATION · TREND ≠ AUTOMATIC ACTION. 정책수정/승인/자동조치/실행/배포 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class GovernanceFeedbackEngine:
    """거버넌스 피드백 인텔리전스 엔진. 불변·append-only·결정적. 실행/변경/승인/집행 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = FeedbackArtifact(
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

    # ── Feedback Registry (불변) ──
    def record_feedback(self, source_layer: str, category: str, description: str,
                      evidence_reference: str = "", severity: str = "MEDIUM", now: str = "",
                      *, commit: bool = False) -> FeedbackRecord:
        """거버넌스 피드백을 불변 기록. category 검증. 동일 id·상이 metadata → 불변 위반. **기록만.**"""
        if category not in FEEDBACK_CATEGORIES:
            raise InvalidFeedbackCategory(f"미등록 피드백 범주 {category}")
        fid = _feedback_id(source_layer, category, description)
        mh = _metadata_hash({"evidence_reference": evidence_reference, "severity": severity})
        existing = ledger.get_feedback(fid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutableFeedbackError(f"{fid} 피드백 불변 — 변경 불가")
            return FeedbackRecord(**{k: v for k, v in existing.items()
                                     if k in FeedbackRecord.__dataclass_fields__})
        self._ensure_layer_artifact(source_layer, now, commit=commit)
        rec = FeedbackRecord(
            feedback_id=fid, source_layer=source_layer, category=category, description=description,
            evidence_reference=evidence_reference, severity=severity, metadata_hash=mh,
            created_at=now, input_hash=input_digest(source_layer, category, description),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.feedback_exists(fid):
            head = ledger.feedback_head()
            ledger.append_feedback(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_FEEDBACK, fid, _artifact_id(ART_LAYER, source_layer), now,
                              commit=commit)
        return FeedbackRecord(**rec)

    # ── Governance Issue Registry (이벤트 소싱) ──
    def issue_state(self, issue_id: str) -> str:
        evs = ledger.issue_events_for(issue_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _issue_meta(self, issue_id: str) -> dict | None:
        evs = ledger.issue_events_for(issue_id)
        return evs[0] if evs else None

    def _emit_issue_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_issue(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(issue)")
        iid = meta["issue_id"]
        eid = issue_event_id(iid, frm, to)
        rec = GovernanceIssueEvent(
            event_id=eid, issue_id=iid, source=meta["source"], frequency=meta["frequency"],
            impact=meta["impact"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(iid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.issue_event_exists(eid):
            head = ledger.issues_head()
            ledger.append_issue_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_issue(self, source: str, frequency: int = 1, impact: str = "MEDIUM",
                     feedback_ref: str = "", now: str = "",
                     *, commit: bool = False) -> GovernanceIssueEvent:
        """거버넌스 이슈를 등록(DETECTED). **탐지·추적 기록 — 자동 수정 없음.**"""
        iid = _issue_id(source, impact)
        existing = ledger.issue_events_for(iid)
        if existing:
            return GovernanceIssueEvent(**existing[-1])
        meta = {"issue_id": iid, "source": source, "frequency": int(frequency), "impact": impact}
        rec = self._emit_issue_event(meta, "", DETECTED, now, commit=commit)
        parent = _artifact_id(ART_FEEDBACK, feedback_ref) if feedback_ref and \
            ledger.artifact_exists(_artifact_id(ART_FEEDBACK, feedback_ref)) else ""
        self._record_artifact(ART_ISSUE, iid, parent, now, commit=commit)
        return GovernanceIssueEvent(**rec)

    def transition_issue(self, issue_id: str, to: str, now: str = "", *,
                         commit: bool = False) -> dict:
        meta = self._issue_meta(issue_id)
        if meta is None:
            raise UnknownIssue(f"미존재 이슈 {issue_id}")
        return self._emit_issue_event(meta, self.issue_state(issue_id), to, now, commit=commit)

    def track_issue(self, issue_id: str, now: str = "", *, commit: bool = False) -> dict:
        """DETECTED→ANALYZED→TRACKED. **추적 상태 기록 — 자동 조치 없음.**"""
        meta = self._issue_meta(issue_id)
        if meta is None:
            raise UnknownIssue(f"미존재 이슈 {issue_id}")
        cur = self.issue_state(issue_id)
        if cur == DETECTED:
            self._emit_issue_event(meta, DETECTED, ANALYZED, now, commit=commit)
        self._emit_issue_event(meta, ANALYZED, TRACKED, now, commit=commit)
        return {"issue_id": issue_id, "state": self.issue_state(issue_id)}

    # ── Pattern Detection (불변) ──
    def analyze_pattern(self, issue_type: str, related_sources: list | None = None,
                      occurrences: int | None = None, now: str = "",
                      *, commit: bool = False) -> PatternRecord:
        """재발 이슈 패턴 탐지. occurrences/related_sources 미지정 시 피드백 원장에서 파생. **탐지 기록만.**"""
        fb = ledger.feedback_by_category(issue_type)
        if occurrences is None:
            occurrences = len(fb)
        if related_sources is None:
            related_sources = sorted({r.get("source_layer") for r in fb if r.get("source_layer")})
        related_sources = sorted(set(related_sources or []))
        conf = pattern_confidence(int(occurrences), len(related_sources))
        pid = _pattern_id(issue_type)
        mh = _metadata_hash({"occurrences": int(occurrences), "related_sources": related_sources})
        existing = ledger.get_pattern(pid)
        if existing is not None:
            if existing.get("metadata_hash") != mh:
                raise ImmutablePatternError(f"{pid} 패턴 불변 — 변경 불가")
            return PatternRecord(**{k: v for k, v in existing.items()
                                    if k in PatternRecord.__dataclass_fields__})
        rec = PatternRecord(
            pattern_id=pid, issue_type=issue_type, occurrences=int(occurrences),
            related_sources=related_sources, confidence=conf, metadata_hash=mh, created_at=now,
            input_hash=input_digest(issue_type), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.pattern_exists(pid):
            head = ledger.patterns_head()
            ledger.append_pattern(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_PATTERN, pid, "", now, commit=commit)
        return PatternRecord(**rec)

    # ── Improvement Theme (불변) ──
    def create_theme(self, description: str, supporting_feedback: list | None = None,
                   priority: str = "MEDIUM", now: str = "",
                   *, commit: bool = False) -> ImprovementTheme:
        """개선 테마 생성. **분석 전용 — RECOMMENDATION ≠ IMPLEMENTATION.**"""
        tid = _theme_id(description)
        for t in ledger.read_themes():
            if t.get("theme_id") == tid:
                return ImprovementTheme(**{k: v for k, v in t.items()
                                           if k in ImprovementTheme.__dataclass_fields__})
        sup = list(supporting_feedback or [])
        rec = ImprovementTheme(
            theme_id=tid, description=description, supporting_feedback=sup, priority=priority,
            created_at=now, input_hash=input_digest(description),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.theme_exists(tid):
            head = ledger.themes_head()
            ledger.append_theme(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = ""
        for ref in sup:
            for at in (ART_PATTERN, ART_FEEDBACK, ART_ISSUE):
                cand = _artifact_id(at, ref)
                if ledger.artifact_exists(cand):
                    parent = cand
                    break
            if parent:
                break
        self._record_artifact(ART_THEME, tid, parent, now, commit=commit)
        return ImprovementTheme(**rec)

    # ── Feedback Aggregation (불변·결정적) ──
    def aggregate_feedback(self, period: str, metrics: dict | None = None,
                         previous_period_score: float | None = None, now: str = "",
                         *, commit: bool = False) -> AggregationRecord:
        """기간별 피드백 집계·추세 요약(결정적). 동일 period → 동일 집계."""
        aid = _aggregation_id(period)
        existing = next((a for a in ledger.read_aggregations()
                         if a.get("aggregation_id") == aid), None)
        if existing is not None:
            return AggregationRecord(**{k: v for k, v in existing.items()
                                        if k in AggregationRecord.__dataclass_fields__})
        fb = ledger.read_feedback()
        cat_counts: dict = {}
        for r in fb:
            cat_counts[r.get("category")] = cat_counts.get(r.get("category"), 0) + 1
        issues = ledger.distinct_issues()
        open_issues = sum(1 for i in issues
                          if self.issue_state(i.get("issue_id")) not in ("ARCHIVED",))
        m = dict(metrics or {})
        m.setdefault("feedback_count", len(fb))
        m.setdefault("issue_count", len(issues))
        m.setdefault("open_issue_count", open_issues)
        cur_score = governance_score(m) if metrics else 0.0
        delta = round(cur_score - float(previous_period_score), 8) \
            if previous_period_score is not None else 0.0
        trend = {"category_counts": dict(sorted(cat_counts.items())),
                 "governance_score": cur_score, "delta": delta, "label": trend_label(delta)}
        rec = AggregationRecord(
            aggregation_id=aid, period=period, metrics=m, trend_summary=trend, created_at=now,
            input_hash=input_digest(period), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.aggregation_exists(aid):
            head = ledger.aggregations_head()
            ledger.append_aggregation(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_AGGREGATION, aid, "", now, commit=commit)
        return AggregationRecord(**rec)

    # ── Feedback Review (불변, 분석 전용) ──
    def create_review(self, reviewer: str, target_reference: str, decision: str, notes: str = "",
                    now: str = "", *, commit: bool = False) -> FeedbackReview:
        """거버넌스 피드백 검토 기록(비집행). decision ∈ {ACKNOWLEDGE,ESCALATE,MONITOR}."""
        if decision not in REVIEW_DECISIONS:
            raise InvalidReviewDecision(f"유효하지 않은 검토 결정 {decision}")
        rvid = _review_id(reviewer, target_reference)
        for r in ledger.read_reviews():
            if r.get("review_id") == rvid:
                return FeedbackReview(**{k: v for k, v in r.items()
                                         if k in FeedbackReview.__dataclass_fields__})
        rec = FeedbackReview(
            review_id=rvid, reviewer=reviewer, target_reference=target_reference,
            decision=decision, notes=notes, created_at=now,
            input_hash=input_digest(reviewer, target_reference), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.review_exists(rvid):
            head = ledger.reviews_head()
            ledger.append_review(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REVIEW, rvid, "", now, commit=commit)
        return FeedbackReview(**rec)

    # ── 분석 프레임워크 ──
    def analyze(self, metrics: dict) -> dict:
        """거버넌스 지표 → SCORE/HEALTH. **FEEDBACK ≠ CHANGE — 집행 신호 아님.**"""
        return {"governance_score": governance_score(metrics),
                "governance_health": governance_health(metrics)}

    def issue_frequency(self) -> dict:
        """소스별 이슈 빈도 집계(정보용)."""
        out: dict = {}
        for i in ledger.distinct_issues():
            out[i.get("source")] = out.get(i.get("source"), 0) + 1
        return dict(sorted(out.items()))

    def recurring_patterns(self, threshold: float = 0.6) -> list:
        """신뢰도 threshold 이상 패턴(재발 실패 패턴)."""
        return [p.get("pattern_id") for p in ledger.read_patterns()
                if float(p.get("confidence", 0.0)) >= threshold]

    def unresolved_issue_summary(self) -> list:
        """미해소(ARCHIVED 아님) 이슈 요약. **정보용 — 개입 없음.**"""
        out: list = []
        for i in ledger.distinct_issues():
            st = self.issue_state(i.get("issue_id"))
            if st != "ARCHIVED":
                out.append(f"{i.get('source')}:{i.get('impact')}:{st}")
        return sorted(set(out))

    def improvement_opportunity_map(self) -> dict:
        """개선 기회 지도: 테마별 지원 피드백 수(정보용)."""
        out: dict = {}
        for t in ledger.read_themes():
            out[t.get("theme_id")] = len(t.get("supporting_feedback", []))
        return dict(sorted(out.items()))

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """피드백 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
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

    # ── Governance Trend Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                       *, commit: bool = False) -> GovernanceTrendReport:
        m = dict(metrics or {})
        fb = ledger.read_feedback()
        cat_dist: dict = {}
        for r in fb:
            cat_dist[r.get("category")] = cat_dist.get(r.get("category"), 0) + 1
        issues = ledger.distinct_issues()
        ist_dist: dict = {}
        for i in issues:
            st = self.issue_state(i.get("issue_id"))
            ist_dist[st] = ist_dist.get(st, 0) + 1
        patterns = ledger.read_patterns()
        recurring = len(self.recurring_patterns())
        rid = _report_id(scope)
        rec = GovernanceTrendReport(
            report_id=rid, scope=scope, feedback_count=len(fb),
            feedback_category_distribution=dict(sorted(cat_dist.items())), issue_count=len(issues),
            issue_state_distribution=dict(sorted(ist_dist.items())), pattern_count=len(patterns),
            recurring_pattern_count=recurring, theme_count=len(ledger.read_themes()),
            aggregation_count=len(ledger.read_aggregations()),
            review_count=len(ledger.read_reviews()),
            unresolved_issue_summary=self.unresolved_issue_summary(),
            improvement_opportunity_map=self.improvement_opportunity_map(), metrics=m,
            governance_score=governance_score(m), governance_health=governance_health(m),
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return GovernanceTrendReport(**rec)

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
    def summary(self, now: str = "") -> FeedbackSummary:
        fb = ledger.read_feedback()
        cat_dist: dict = {}
        for r in fb:
            cat_dist[r.get("category")] = cat_dist.get(r.get("category"), 0) + 1
        issues = ledger.distinct_issues()
        ist_dist: dict = {}
        for i in issues:
            st = self.issue_state(i.get("issue_id"))
            ist_dist[st] = ist_dist.get(st, 0) + 1
        return FeedbackSummary(
            timestamp=now, feedback_count=len(fb),
            feedback_category_distribution=dict(sorted(cat_dist.items())), issue_count=len(issues),
            issue_state_distribution=dict(sorted(ist_dist.items())),
            pattern_count=len(ledger.read_patterns()), theme_count=len(ledger.read_themes()),
            aggregation_count=len(ledger.read_aggregations()),
            review_count=len(ledger.read_reviews()), report_count=len(ledger.read_reports()))
