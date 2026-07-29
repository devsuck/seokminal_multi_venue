"""Research Risk Intelligence Engine (P10.25) — 연구 과정 리스크 분석. **분석·기록 전용, 투자 실행 아님.**

P10.2/P10.3/P10.4/P10.7/P10.8 을 READ ONLY 로 참조(파일 기반, import 없음)해 과적합·데이터 누수·거짓 발견·
복잡도·검증 취약·재현성 리스크를 분석하고 리스크 레지스트리·요인·평가·리포트·계보를 남긴다. **리스크 한도
변경·자본 결정·전략 거부·배포 결정 없음.** execution/broker/order/portfolio execution/capital allocation/
live trading/permission/risk controller import·호출 없음. RISK ANALYSIS ≠ RISK LIMIT CHANGE · ASSESSMENT ≠
CAPITAL DECISION · FINDING ≠ STRATEGY REJECTION · SCORE ≠ DEPLOYMENT DECISION. 상위 파일은 읽기만. 결정적.
"""
from __future__ import annotations

from jarvis.research_risk_intelligence import ledger
from jarvis.research_risk_intelligence.models import (
    ANALYZING,
    ART_ASSESSMENT,
    ART_FACTOR,
    ART_LAYER,
    ART_REPORT,
    ART_RISK,
    ASSESSED,
    GENESIS,
    RESULTS,
    REVIEWED,
    RISK_CATEGORIES,
    UNKNOWN,
    IllegalTransition,
    ImmutableAssessmentError,
    ImmutableFactorError,
    InvalidRiskCategory,
    RiskArtifact,
    RiskAssessment,
    RiskEvent,
    RiskFactor,
    RiskReport,
    RiskSummary,
    UnknownRisk,
    aggregate_factors,
    artifact_id as _artifact_id,
    assessment_id as _assessment_id,
    can_transition_risk,
    content_hash,
    detect_cycle,
    factor_id as _factor_id,
    input_digest,
    label_from_score,
    report_id as _report_id,
    risk_event_id,
    risk_id as _risk_id,
    risk_label,
    risk_score,
    worst_label,
)

_DISCLAIMER = ("연구 리스크 분석 데이터 — RISK ANALYSIS ≠ RISK LIMIT CHANGE · ASSESSMENT ≠ CAPITAL "
               "DECISION · FINDING ≠ STRATEGY REJECTION · SCORE ≠ DEPLOYMENT DECISION. 한도변경/자본"
               "결정/거부/배포 아님. (투자 실행 리스크 아님 — 연구 과정 리스크만.)")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchRiskIntelligenceEngine:
    """연구 리스크 인텔리전스 엔진. 불변·append-only·결정적. 한도변경/자본결정/거부/배포 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = RiskArtifact(
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

    # ── Risk Registry (이벤트 소싱) ──
    def risk_state(self, risk_id: str) -> str:
        evs = ledger.risk_events_for(risk_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _risk_meta(self, risk_id: str) -> dict | None:
        evs = ledger.risk_events_for(risk_id)
        return evs[0] if evs else None

    def _emit_risk_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_risk(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(risk)")
        rid = meta["risk_id"]
        eid = risk_event_id(rid, frm, to)
        rec = RiskEvent(
            event_id=eid, risk_id=rid, source_layer=meta["source_layer"],
            source_reference=meta["source_reference"], risk_category=meta["risk_category"],
            from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(rid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.risk_event_exists(eid):
            head = ledger.risks_head()
            ledger.append_risk_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_risk(self, source_layer: str, source_reference: str, risk_category: str,
                    now: str = "", *, commit: bool = False) -> RiskEvent:
        """연구 리스크 항목을 등록(UNKNOWN). risk_category 검증. **추적 시작 — 결정 없음.**"""
        if risk_category not in RISK_CATEGORIES:
            raise InvalidRiskCategory(f"미등록 리스크 범주 {risk_category}")
        rid = _risk_id(source_reference, risk_category)
        existing = ledger.risk_events_for(rid)
        if existing:
            return RiskEvent(**existing[-1])
        self._ensure_layer_artifact(source_layer, now, commit=commit)
        meta = {"risk_id": rid, "source_layer": source_layer, "source_reference": source_reference,
                "risk_category": risk_category}
        rec = self._emit_risk_event(meta, "", UNKNOWN, now, commit=commit)
        self._record_artifact(ART_RISK, rid, _artifact_id(ART_LAYER, source_layer), now,
                              commit=commit)
        return RiskEvent(**rec)

    def transition_risk(self, risk_id: str, to: str, now: str = "", *,
                        commit: bool = False) -> dict:
        meta = self._risk_meta(risk_id)
        if meta is None:
            raise UnknownRisk(f"미존재 리스크 {risk_id}")
        return self._emit_risk_event(meta, self.risk_state(risk_id), to, now, commit=commit)

    # ── Risk Factors (불변) ──
    def record_factor(self, risk_ref: str, name: str, category: str, value: float,
                    weight: float = 1.0, interpretation: str = "", now: str = "",
                    *, commit: bool = False) -> RiskFactor:
        """리스크 기여 요인을 불변 기록. category 검증. **관찰·기록만.**"""
        if category not in RISK_CATEGORIES:
            raise InvalidRiskCategory(f"미등록 리스크 범주 {category}")
        fid = _factor_id(risk_ref, name)
        existing = ledger.get_factor(fid)
        if existing is not None:
            if abs(float(existing.get("value", 0.0)) - round(float(value), 8)) > 1e-9:
                raise ImmutableFactorError(f"{fid} 리스크 요인 불변 — 변경 불가")
            return RiskFactor(**{k: v for k, v in existing.items()
                                 if k in RiskFactor.__dataclass_fields__})
        rec = RiskFactor(
            factor_id=fid, risk_ref=risk_ref, name=name, category=category,
            value=round(float(value), 8), weight=round(float(weight), 8),
            interpretation=interpretation, created_at=now, input_hash=input_digest(risk_ref, name),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.factor_exists(fid):
            head = ledger.factors_head()
            ledger.append_factor(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_RISK, risk_ref) if ledger.artifact_exists(
            _artifact_id(ART_RISK, risk_ref)) else ""
        self._record_artifact(ART_FACTOR, fid, parent, now, commit=commit)
        return RiskFactor(**rec)

    # ── Risk Assessment (불변, 결정적 점수) ──
    def assess_risk(self, risk_ref: str, dimension_scores: dict | None = None,
                  evidence_reference: str = "", epoch: str = "", now: str = "",
                  *, commit: bool = False) -> RiskAssessment:
        """리스크 평가를 불변 기록(결정적 점수). dimension_scores 미지정 시 요인에서 집계. risk UNKNOWN→
        ANALYZING→ASSESSED 로 승격. **SCORE ≠ DEPLOYMENT DECISION.**"""
        meta = self._risk_meta(risk_ref)
        if meta is None:
            raise UnknownRisk(f"미존재 리스크 {risk_ref}")
        ds = dict(dimension_scores) if dimension_scores is not None else \
            aggregate_factors(ledger.factors_for(risk_ref))
        aid = _assessment_id(risk_ref, epoch)
        existing = ledger.get_assessment(aid)
        if existing is not None:
            if existing.get("dimension_scores") != ds:
                raise ImmutableAssessmentError(f"{aid} 리스크 평가 불변 — 변경 불가")
            return RiskAssessment(**{k: v for k, v in existing.items()
                                     if k in RiskAssessment.__dataclass_fields__})
        # 리스크 상태 승격(UNKNOWN→ANALYZING→ASSESSED)
        cur = self.risk_state(risk_ref)
        if cur == UNKNOWN:
            self._emit_risk_event(meta, UNKNOWN, ANALYZING, now, commit=commit)
            cur = ANALYZING
        if cur == ANALYZING:
            self._emit_risk_event(meta, ANALYZING, ASSESSED, now, commit=commit)
        rec = RiskAssessment(
            assessment_id=aid, risk_ref=risk_ref,
            source_reference=meta.get("source_reference", ""), dimension_scores=ds,
            risk_score=risk_score(ds), risk_label=risk_label(ds),
            evidence_reference=evidence_reference, epoch=epoch, created_at=now,
            input_hash=input_digest(risk_ref, epoch), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.assessment_exists(aid):
            head = ledger.assessments_head()
            ledger.append_assessment(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_RISK, risk_ref) if ledger.artifact_exists(
            _artifact_id(ART_RISK, risk_ref)) else ""
        self._record_artifact(ART_ASSESSMENT, aid, parent, now, commit=commit)
        return RiskAssessment(**rec)

    def review_risk(self, risk_ref: str, now: str = "", *, commit: bool = False) -> dict:
        """ASSESSED→REVIEWED. **검토 기록일 뿐 자동 거부/한도변경 없음.**"""
        meta = self._risk_meta(risk_ref)
        if meta is None:
            raise UnknownRisk(f"미존재 리스크 {risk_ref}")
        cur = self.risk_state(risk_ref)
        if cur != ASSESSED:
            raise IllegalTransition(f"{cur or 'GENESIS'} -> {REVIEWED} 차단(risk)")
        self._emit_risk_event(meta, ASSESSED, REVIEWED, now, commit=commit)
        return {"risk_id": risk_ref, "state": self.risk_state(risk_ref),
                "note": "검토 기록 — 전략 거부/자본 결정/배포 아님"}

    # ── 분석 프레임워크 ──
    def analyze(self, dimension_scores: dict) -> dict:
        """리스크 지표 → SCORE/LABEL. **RISK ANALYSIS ≠ RISK LIMIT CHANGE — 결정 신호 아님.**"""
        return {"risk_score": risk_score(dimension_scores),
                "risk_label": risk_label(dimension_scores)}

    def high_risk_items(self, threshold: float = 0.7) -> list:
        """CRITICAL 수준(점수≥threshold) 평가 항목. **정보용 — 개입 없음.**"""
        return sorted({a.get("risk_ref") for a in ledger.read_assessments()
                       if float(a.get("risk_score", 0.0)) >= threshold})

    def assessed_label(self, risk_ref: str) -> str:
        """리스크의 최신 평가 라벨(없으면 PASS)."""
        labels = [a.get("risk_label") for a in ledger.read_assessments()
                  if a.get("risk_ref") == risk_ref]
        return worst_label(labels) if labels else "PASS"

    # ── 계보 검증 ──
    def verify_lineage(self) -> dict:
        """리스크 계보(아티팩트 parent 체인): dangling parent·순환 탐지. **읽기 전용.**"""
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

    # ── Risk Report ──
    def generate_report(self, scope: str = "GLOBAL", metrics: dict | None = None, now: str = "",
                      *, commit: bool = False) -> RiskReport:
        m = dict(metrics or {})
        risks = ledger.distinct_risks()
        rstate: dict = {}
        rcat: dict = {}
        for r in risks:
            st = self.risk_state(r.get("risk_id"))
            rstate[st] = rstate.get(st, 0) + 1
            rcat[r.get("risk_category")] = rcat.get(r.get("risk_category"), 0) + 1
        assessments = ledger.read_assessments()
        alabel: dict = {}
        for a in assessments:
            alabel[a.get("risk_label")] = alabel.get(a.get("risk_label"), 0) + 1
        scores = [float(a.get("risk_score", 0.0)) for a in assessments]
        avg = round(sum(scores) / len(scores), 8) if scores else 0.0
        overall = worst_label([a.get("risk_label") for a in assessments])
        rid = _report_id(scope)
        rec = RiskReport(
            report_id=rid, scope=scope, risk_count=len(risks),
            risk_state_distribution=dict(sorted(rstate.items())),
            risk_category_distribution=dict(sorted(rcat.items())),
            assessment_count=len(assessments),
            assessment_label_distribution=dict(sorted(alabel.items())),
            factor_count=len(ledger.read_factors()), average_risk_score=avg, overall_label=overall,
            high_risk_items=self.high_risk_items(), metrics=m, disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(scope), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_REPORT, rid, "", now, commit=commit)
        return RiskReport(**rec)

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
    def summary(self, now: str = "") -> RiskSummary:
        risks = ledger.distinct_risks()
        rstate: dict = {}
        rcat: dict = {}
        for r in risks:
            st = self.risk_state(r.get("risk_id"))
            rstate[st] = rstate.get(st, 0) + 1
            rcat[r.get("risk_category")] = rcat.get(r.get("risk_category"), 0) + 1
        assessments = ledger.read_assessments()
        alabel: dict = {}
        for a in assessments:
            alabel[a.get("risk_label")] = alabel.get(a.get("risk_label"), 0) + 1
        return RiskSummary(
            timestamp=now, risk_count=len(risks),
            risk_state_distribution=dict(sorted(rstate.items())),
            risk_category_distribution=dict(sorted(rcat.items())),
            factor_count=len(ledger.read_factors()), assessment_count=len(assessments),
            assessment_label_distribution=dict(sorted(alabel.items())),
            report_count=len(ledger.read_reports()))
