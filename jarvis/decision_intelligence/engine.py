"""Research Decision Intelligence Engine (P10.7) — 연구 결과 비교·분석 판단 지원. **기록 전용.**

여러 연구 결과(P10.2~P10.6)를 READ ONLY 로 소비해 후보 등록·평가 세션·프레임워크·스코어카드(MCDA)·
트레이드오프·결정 리포트·계보를 남긴다. **판단 지원만 수행한다.** execution/broker/order/portfolio
mutation/risk governor/permission/live trading import·호출 없음. 자동 전략 선택·추천·배포·자본배분 없음.
score ≠ approval · VALIDATED ≠ SELECTED · RECOMMENDED ≠ DEPLOYABLE. Decision output 은 기록 데이터이며
실제 운영 상태를 바꾸지 않는다. 상위 레이어 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.decision_intelligence import ledger
from jarvis.decision_intelligence.models import (
    ARCHIVED,
    ART_CANDIDATE,
    ART_EVALUATION,
    ART_REPORT,
    ART_SCORECARD,
    ART_SOURCE,
    ART_TRADEOFF,
    COMPARED,
    COMPLETED,
    CREATED,
    DEFAULT_WEIGHTS,
    EVALUATING,
    GENESIS,
    REGISTERED,
    REPORTED,
    SCORE_DIMENSIONS,
    SCORED,
    UNDER_REVIEW,
    CandidateEvent,
    DecisionArtifact,
    DecisionIntelligenceReport,
    DecisionReport,
    DecisionSessionEvent,
    EvaluationFramework,
    IllegalTransition,
    ImmutableCandidateError,
    ImmutableFrameworkError,
    Scorecard,
    TradeoffAnalysis,
    UnknownCandidate,
    UnknownFramework,
    artifact_id as _artifact_id,
    can_transition_candidate,
    can_transition_session,
    candidate_event_id,
    candidate_id as _candidate_id,
    content_hash,
    detect_cycle,
    framework_id as _framework_id,
    input_digest,
    metadata_hash as _metadata_hash,
    overall_score as _overall_score,
    report_id as _report_id,
    scorecard_id as _scorecard_id,
    session_event_id,
    session_id as _session_id,
    tradeoff_id as _tradeoff_id,
    tradeoff_symbol,
)

_DISCLAIMER = ("판단 지원 데이터 — score ≠ approval · RECOMMENDED ≠ DEPLOYABLE · "
               "VALIDATED ≠ SELECTED. 실제 선택/배포/자본배분 아님.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchDecisionEngine:
    """연구 결정 지원 엔진. 불변·append-only·결정적. 선택/배포/실행/자본배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         session_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = DecisionArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, session_id=session_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Candidate Registry (이벤트 소싱, 불변 정체성) ──
    def candidate_state(self, candidate_id: str) -> str:
        evs = ledger.candidate_events_for(candidate_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _candidate_meta(self, candidate_id: str) -> dict | None:
        evs = ledger.candidate_events_for(candidate_id)
        return evs[0] if evs else None

    def _emit_candidate_event(self, meta: dict, frm: str, to: str, now: str,
                              *, commit: bool) -> dict:
        if not can_transition_candidate(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(candidate)")
        cid = meta["candidate_id"]
        eid = candidate_event_id(cid, frm, to)
        rec = CandidateEvent(
            event_id=eid, candidate_id=cid, source_layer=meta["source_layer"],
            source_reference=meta["source_reference"], research_type=meta["research_type"],
            metadata_hash=meta["metadata_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(cid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.candidate_event_exists(eid):
            head = ledger.candidates_head()
            ledger.append_candidate_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_candidate(self, source_layer: str, source_reference: str, research_type: str,
                           metadata: dict | None = None, now: str = "",
                           *, commit: bool = False) -> CandidateEvent:
        """연구 결과를 결정 후보로 불변 등록(REGISTERED). **선택/승인 아님.**"""
        cid = _candidate_id(source_layer, source_reference)
        mh = _metadata_hash(metadata or {})
        existing = ledger.candidate_events_for(cid)
        if existing:
            if existing[0].get("metadata_hash") != mh:
                raise ImmutableCandidateError(f"{cid} 후보 불변 — 메타데이터 변경 불가")
            return CandidateEvent(**existing[-1])
        meta = {"candidate_id": cid, "source_layer": source_layer,
                "source_reference": source_reference, "research_type": research_type,
                "metadata_hash": mh}
        rec = self._emit_candidate_event(meta, "", REGISTERED, now, commit=commit)
        # 계보: SOURCE -> CANDIDATE
        self._record_artifact(ART_SOURCE, f"{source_layer}:{source_reference}", "", "", now,
                              commit=commit)
        self._record_artifact(ART_CANDIDATE, cid,
                              _artifact_id(ART_SOURCE, f"{source_layer}:{source_reference}"),
                              "", now, commit=commit)
        return CandidateEvent(**rec)

    def transition_candidate(self, candidate_id: str, to: str, now: str = "", *,
                             commit: bool = False) -> dict:
        meta = self._candidate_meta(candidate_id)
        if meta is None:
            raise UnknownCandidate(f"미존재 후보 {candidate_id}")
        return self._emit_candidate_event(meta, self.candidate_state(candidate_id), to, now,
                                          commit=commit)

    def _safe_advance_candidate(self, candidate_id: str, to: str, now: str,
                                *, commit: bool) -> None:
        meta = self._candidate_meta(candidate_id)
        if meta is None:
            return
        cur = self.candidate_state(candidate_id)
        if cur != to and can_transition_candidate(cur, to):
            self._emit_candidate_event(meta, cur, to, now, commit=commit)

    # ── Decision Session (이벤트 소싱) ──
    def session_state(self, session_id: str) -> str:
        evs = ledger.session_events_for(session_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _session_meta(self, session_id: str) -> dict | None:
        evs = ledger.session_events_for(session_id)
        return evs[0] if evs else None

    def _emit_session_event(self, meta: dict, frm: str, to: str, now: str,
                            *, commit: bool) -> dict:
        if not can_transition_session(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(session)")
        sid = meta["session_id"]
        eid = session_event_id(sid, frm, to)
        rec = DecisionSessionEvent(
            event_id=eid, session_id=sid, objective=meta["objective"],
            evaluator=meta["evaluator"], candidates=meta["candidates"], from_state=frm,
            to_state=to, status=to, created_at=now, input_hash=input_digest(sid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.session_event_exists(eid):
            head = ledger.sessions_head()
            ledger.append_session_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_decision_session(self, objective: str, evaluator: str, candidates: list,
                                now: str = "", *, commit: bool = False) -> DecisionSessionEvent:
        cands = sorted(candidates or [])
        sid = _session_id(objective, evaluator, cands)
        existing = ledger.session_events_for(sid)
        if existing:
            return DecisionSessionEvent(**existing[-1])
        meta = {"session_id": sid, "objective": objective, "evaluator": evaluator,
                "candidates": cands}
        rec = self._emit_session_event(meta, "", CREATED, now, commit=commit)
        return DecisionSessionEvent(**rec)

    def transition_session(self, session_id: str, to: str, now: str = "", *,
                           commit: bool = False) -> dict:
        meta = self._session_meta(session_id)
        if meta is None:
            raise IllegalTransition(f"미존재 세션 {session_id}")
        return self._emit_session_event(meta, self.session_state(session_id), to, now,
                                        commit=commit)

    def _safe_advance_session(self, session_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._session_meta(session_id)
        if meta is None:
            return
        cur = self.session_state(session_id)
        if cur != to and can_transition_session(cur, to):
            self._emit_session_event(meta, cur, to, now, commit=commit)

    # ── Evaluation Framework (버전 관리, 불변) ──
    def define_framework(self, name: str, version: str, criteria: list | None = None,
                         weights: dict | None = None, now: str = "",
                         *, commit: bool = False) -> EvaluationFramework:
        fid = _framework_id(name, version)
        crit = list(criteria or list(SCORE_DIMENSIONS))
        wts = dict(weights or DEFAULT_WEIGHTS)
        existing = ledger.get_framework(fid)
        if existing:
            new_hash = input_digest(sorted(crit), sorted(wts.items()))
            if existing.get("input_hash") != new_hash:
                raise ImmutableFrameworkError(f"{fid} 프레임워크 불변 — 동일 name+version 내용 상이")
            return EvaluationFramework(**{k: v for k, v in existing.items()
                                          if k in EvaluationFramework.__dataclass_fields__})
        rec = EvaluationFramework(
            framework_id=fid, name=name, version=version, criteria=crit, weights=wts,
            created_at=now, input_hash=input_digest(sorted(crit), sorted(wts.items())),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.framework_exists(fid):
            head = ledger.frameworks_head()
            ledger.append_framework(_seal(rec, head["record_hash"] if head else GENESIS))
        return EvaluationFramework(**rec)

    # ── Scorecard 평가 (MCDA) ──
    def evaluate_candidate(self, session_id: str, candidate_id: str, framework_id: str,
                           scores: dict, evidence: dict | None = None,
                           explanations: dict | None = None, now: str = "",
                           *, commit: bool = False) -> Scorecard:
        """후보를 프레임워크 기준으로 평가해 스코어카드를 남긴다. **score ≠ approval.**"""
        fw = ledger.get_framework(framework_id)
        if fw is None:
            raise UnknownFramework(f"미존재 프레임워크 {framework_id}")
        if self._candidate_meta(candidate_id) is None:
            raise UnknownCandidate(f"미존재 후보 {candidate_id}")
        clean_scores = {d: round(float(scores.get(d, 0.0)), 8) for d in fw.get("criteria", [])}
        ov = _overall_score(clean_scores, fw.get("weights", {}))
        sc_id = _scorecard_id(session_id, candidate_id, framework_id)
        rec = Scorecard(
            scorecard_id=sc_id, session_id=session_id, candidate_id=candidate_id,
            framework_id=framework_id, scores=clean_scores, evidence=dict(evidence or {}),
            explanations=dict(explanations or {}), overall_score=ov, created_at=now,
            input_hash=input_digest(session_id, candidate_id, framework_id),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.scorecard_exists(sc_id):
            head = ledger.scorecards_head()
            ledger.append_scorecard(_seal(rec, head["record_hash"] if head else GENESIS))
        # 계보: CANDIDATE -> EVALUATION -> SCORECARD
        self._record_artifact(ART_EVALUATION, sc_id, _artifact_id(ART_CANDIDATE, candidate_id),
                              session_id, now, commit=commit)
        self._record_artifact(ART_SCORECARD, sc_id, _artifact_id(ART_EVALUATION, sc_id),
                              session_id, now, commit=commit)
        # 후보 상태 진행 REGISTERED→UNDER_REVIEW→SCORED, 세션 CREATED→EVALUATING
        self._safe_advance_candidate(candidate_id, UNDER_REVIEW, now, commit=commit)
        self._safe_advance_candidate(candidate_id, SCORED, now, commit=commit)
        self._safe_advance_session(session_id, EVALUATING, now, commit=commit)
        return Scorecard(**rec)

    # ── Trade-off 분석 (자동 추천 없음) ──
    def compare_candidates(self, session_id: str, candidate_a: str, candidate_b: str,
                           now: str = "", *, commit: bool = False) -> TradeoffAnalysis:
        """두 후보 스코어카드를 항목별 서술 기호로 비교. **recommendation 자동 생성 금지.**"""
        def _card(cid):
            for s in ledger.scorecards_for_session(session_id):
                if s.get("candidate_id") == cid:
                    return s
            return None

        ca, cb = _card(candidate_a), _card(candidate_b)
        sa = ca.get("scores", {}) if ca else {}
        sb = cb.get("scores", {}) if cb else {}
        dims: dict = {}
        for d in sorted(set(sa) | set(sb)):
            va, vb = float(sa.get(d, 0.0)), float(sb.get(d, 0.0))
            dims[d] = {"a": tradeoff_symbol(va), "b": tradeoff_symbol(vb),
                       "delta": round(va - vb, 8)}
        oa = ca.get("overall_score", 0.0) if ca else 0.0
        ob = cb.get("overall_score", 0.0) if cb else 0.0
        tid = _tradeoff_id(session_id, candidate_a, candidate_b)
        rec = TradeoffAnalysis(
            tradeoff_id=tid, session_id=session_id, candidate_a=candidate_a,
            candidate_b=candidate_b, dimensions=dims, overall_a=round(float(oa), 8),
            overall_b=round(float(ob), 8),
            note="서술적 비교만 — 자동 추천/선택 없음. 사람 검토 필요.", created_at=now,
            input_hash=input_digest(session_id, *sorted((candidate_a, candidate_b))),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.tradeoff_exists(tid):
            head = ledger.tradeoffs_head()
            ledger.append_tradeoff(_seal(rec, head["record_hash"] if head else GENESIS))
        # 부모: 존재하는 스코어카드 아티팩트(A 우선, 없으면 B), 둘 다 없으면 루트.
        anchor = ca or cb
        parent = _artifact_id(ART_SCORECARD, anchor.get("scorecard_id")) if anchor else ""
        self._record_artifact(ART_TRADEOFF, tid, parent, session_id, now, commit=commit)
        for c in (candidate_a, candidate_b):
            self._safe_advance_candidate(c, COMPARED, now, commit=commit)
        return TradeoffAnalysis(**rec)

    # ── Decision Report / snapshot ──
    def generate_tradeoff_report(self, session_id: str, now: str = "",
                                 *, commit: bool = False) -> DecisionReport:
        return self.create_decision_snapshot(session_id, now, commit=commit)

    def create_decision_snapshot(self, session_id: str, now: str = "",
                                 *, commit: bool = False) -> DecisionReport:
        """세션의 스코어카드·트레이드오프를 결정 리포트로 스냅샷. **선택/배포 아님 — 참고 순위만.**"""
        smeta = self._session_meta(session_id)
        objective = smeta.get("objective", "") if smeta else ""
        evaluator = smeta.get("evaluator", "") if smeta else ""
        cards = ledger.scorecards_for_session(session_id)
        ranking = sorted(
            [{"candidate_id": c.get("candidate_id"),
              "overall_score": c.get("overall_score", 0.0)} for c in cards],
            key=lambda x: (-x["overall_score"], x["candidate_id"]))
        tradeoffs = ledger.tradeoffs_for_session(session_id)
        rid = _report_id(session_id)
        rec = DecisionReport(
            report_id=rid, session_id=session_id, objective=objective, evaluator=evaluator,
            candidate_count=len({c.get("candidate_id") for c in cards}), ranking=ranking,
            scorecard_count=len(cards), tradeoff_count=len(tradeoffs), disclaimer=_DISCLAIMER,
            created_at=now, input_hash=input_digest(session_id, len(cards)),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        # 부모: 트레이드오프 우선, 없으면 첫 스코어카드, 둘 다 없으면 루트 — dangling 방지.
        if tradeoffs:
            parent = _artifact_id(ART_TRADEOFF, tradeoffs[0].get("tradeoff_id"))
        elif cards:
            parent = _artifact_id(ART_SCORECARD, cards[0].get("scorecard_id"))
        else:
            parent = ""
        self._record_artifact(ART_REPORT, rid, parent, session_id, now, commit=commit)
        for c in cards:
            self._safe_advance_candidate(c.get("candidate_id"), REPORTED, now, commit=commit)
        self._safe_advance_session(session_id, COMPLETED, now, commit=commit)
        return DecisionReport(**rec)

    # ── 상위 레이어 READ ONLY ingest ──
    def ingest_candidates(self, research_type: str, now: str = "", *, commit: bool = False,
                          limit: int = 0) -> int:
        """상위 레이어 원장을 읽기 전용으로 스캔해 후보로 등록. 상위 파일 무변경."""
        spec = ledger.SOURCE_LEDGERS.get(research_type)
        if not spec:
            return 0
        layer, filename, id_field = spec
        n = 0
        for row in ledger.read_source(filename):
            ref = row.get(id_field)
            if not ref:
                continue
            self.register_candidate(layer, str(ref), research_type, {"src": filename}, now,
                                    commit=commit)
            n += 1
            if limit and n >= limit:
                break
        return n

    # ── Report ──
    def generate_report(self, now: str = "") -> DecisionIntelligenceReport:
        candidates = ledger.distinct_candidates()
        cstate: dict = {}
        rtype: dict = {}
        for c in candidates:
            st = self.candidate_state(c.get("candidate_id"))
            cstate[st] = cstate.get(st, 0) + 1
            rtype[c.get("research_type")] = rtype.get(c.get("research_type"), 0) + 1
        sessions = ledger.distinct_sessions()
        sstate: dict = {}
        for s in sessions:
            st = self.session_state(s.get("session_id"))
            sstate[st] = sstate.get(st, 0) + 1
        return DecisionIntelligenceReport(
            timestamp=now, candidate_count=len(candidates),
            candidate_state_distribution=dict(sorted(cstate.items())),
            research_type_distribution=dict(sorted(rtype.items())),
            session_count=len(sessions),
            session_state_distribution=dict(sorted(sstate.items())),
            framework_count=len(ledger.read_frameworks()),
            scorecard_count=len(ledger.read_scorecards()),
            tradeoff_count=len(ledger.read_tradeoffs()),
            report_count=len(ledger.read_reports()))
