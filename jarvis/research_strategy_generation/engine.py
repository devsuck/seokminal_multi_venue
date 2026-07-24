"""Research Strategy Generation Engine (P29) — 역사적 지식에서 연구 전략 후보 생성. **생성 전용, 동작 없음.**

**후보를 만든다 — 선택·승인·배포·실행·거래·자본 배분을 하지 않는다.** execution/broker/live_trading/
portfolio_execution import·호출 없음. GENERATED ≠ SELECTED · CANDIDATE ≠ STRATEGY · CANDIDATE ≠ DEPLOYMENT.
결정적·불변·append-only·이벤트 소싱. 상위 계층은 READ ONLY.
"""
from __future__ import annotations

from jarvis.research_strategy_generation import ledger
from jarvis.research_strategy_generation import models as M
from jarvis.research_strategy_generation.models import (
    GENESIS,
    ArtifactRecord,
    CandidateEventRecord,
    EvidenceRecord,
    GenerationReportRecord,
    GenerationSummary,
    HypothesisRecord,
    IllegalCandidateTransition,
    IllegalSessionTransition,
    NoveltyRecord,
    SessionEventRecord,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Strategy Generation Intelligence 데이터 — GENERATED ≠ SELECTED · CANDIDATE ≠ "
               "STRATEGY · CANDIDATE ≠ DEPLOYMENT. 역사적 지식에서 연구 후보·가설·신규성·증거 생성 전용 — 선택·승인·배포·"
               "실행·거래·자본 배분 없음.")


def _seal(rec, previous_hash) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchStrategyGenerationEngine:
    """연구 전략 생성 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/선택/배포/승인/거래 권한 없음."""

    def _emit(self, exists_fn, head_fn, append_fn, rid, rec, *, commit) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not exists_fn(rid):
            head = head_fn()
            append_fn(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def _artifact(self, atype, ref, parent, now, *, commit) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.artifact_exists, ledger.artifacts_head, ledger.append_artifact,
                         aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ 생성 세션 생애주기(event-sourced) ══════════════
    def _session_event(self, sess, objective, frm, to, note, now, *, commit):
        seq = len(ledger.session_events(sess))
        eid = M.session_event_id(sess, to, seq)
        rec = SessionEventRecord(
            session_event_id=eid, session_id=sess, objective=objective, from_state=frm, to_state=to,
            note=note, occurred_at=now, input_hash=input_digest(sess, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.session_event_exists, ledger.sessions_head,
                         ledger.append_session_event, eid, rec, commit=commit)
        return SessionEventRecord(**rec)

    def session_state(self, sess) -> str | None:
        evs = ledger.session_events(sess)
        return evs[-1].get("to_state") if evs else None

    def _session_meta(self, sess) -> dict:
        evs = ledger.session_events(sess)
        if not evs:
            raise UnknownEntityError(f"미등록 세션 {sess}")
        return {"objective": evs[0].get("objective"), "state": evs[-1].get("to_state")}

    def _session_transition(self, sess, to, note, now, *, commit):
        m = self._session_meta(sess)
        frm = m["state"]
        if not M.can_session_transition(frm, to):
            raise IllegalSessionTransition(f"세션 {sess} {frm}→{to} 불가")
        return self._session_event(sess, m["objective"], frm, to, note, now, commit=commit)

    def create_session(self, objective, now="", *, commit=False) -> SessionEventRecord:
        """생성 세션 생성(genesis CREATED)."""
        sess = M.session_id(objective)
        evs = ledger.session_events(sess)
        if evs:
            return SessionEventRecord(**{k: v for k, v in evs[0].items()
                                         if k in SessionEventRecord.__dataclass_fields__})
        ev = self._session_event(sess, objective, GENESIS, M.S_CREATED, "created", now, commit=commit)
        self._artifact(M.ART_SESSION, sess, "", now, commit=commit)
        return ev

    def start_generating(self, sess, note="generating", now="", *, commit=False):
        return self._session_transition(sess, M.S_GENERATING, note, now, commit=commit)

    def analyze_session(self, sess, note="analyzed", now="", *, commit=False):
        return self._session_transition(sess, M.S_ANALYZED, note, now, commit=commit)

    def conclude_session(self, sess, note="concluded", now="", *, commit=False):
        return self._session_transition(sess, M.S_CONCLUDED, note, now, commit=commit)

    def archive_session(self, sess, note="archived", now="", *, commit=False):
        return self._session_transition(sess, M.S_ARCHIVED, note, now, commit=commit)

    # ══════════════ 전략 후보 생애주기(event-sourced, 선택 없음) ══════════════
    def _candidate_event(self, cand, sess, category, statement, refs, frm, to, note, now, *, commit):
        seq = len(ledger.candidate_events(cand))
        eid = M.candidate_event_id(cand, to, seq)
        rec = CandidateEventRecord(
            candidate_event_id=eid, candidate_id=cand, session_id=sess, category=category,
            statement=statement, source_refs=list(refs), is_selected=False, from_state=frm,
            to_state=to, note=note, occurred_at=now, input_hash=input_digest(cand, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.candidate_event_exists, ledger.candidates_head,
                         ledger.append_candidate_event, eid, rec, commit=commit)
        return CandidateEventRecord(**rec)

    def candidate_state(self, cand) -> str | None:
        evs = ledger.candidate_events(cand)
        return evs[-1].get("to_state") if evs else None

    def _candidate_meta(self, cand) -> dict:
        evs = ledger.candidate_events(cand)
        if not evs:
            raise UnknownEntityError(f"미등록 후보 {cand}")
        g = evs[0]
        return {"session_id": g.get("session_id"), "category": g.get("category"),
                "statement": g.get("statement"), "source_refs": g.get("source_refs", []),
                "state": evs[-1].get("to_state")}

    def _candidate_transition(self, cand, to, note, now, *, commit):
        m = self._candidate_meta(cand)
        frm = m["state"]
        if not M.can_candidate_transition(frm, to):
            raise IllegalCandidateTransition(f"후보 {cand} {frm}→{to} 불가")
        return self._candidate_event(cand, m["session_id"], m["category"], m["statement"],
                                     m["source_refs"], frm, to, note, now, commit=commit)

    def generate_candidate(self, sess, category, statement, source_refs=None, now="",
                           *, commit=False) -> CandidateEventRecord:
        """전략 후보 생성(genesis PROPOSED, is_selected=False). **생성만 — 자동 선택/배포 없음.**"""
        self._session_meta(sess)  # 존재 검증
        if category not in M.CANDIDATE_CATEGORIES:
            raise ValueError(f"미지원 category {category}")
        cand = M.candidate_id(sess, statement)
        evs = ledger.candidate_events(cand)
        if evs:
            return CandidateEventRecord(**{k: v for k, v in evs[0].items()
                                           if k in CandidateEventRecord.__dataclass_fields__})
        ev = self._candidate_event(cand, sess, category, statement, source_refs or [], GENESIS,
                                   M.C_PROPOSED, "proposed", now, commit=commit)
        self._artifact(M.ART_CANDIDATE, cand, M.artifact_id(M.ART_SESSION, sess), now, commit=commit)
        return ev

    def analyze_candidate(self, cand, note="analyzed", now="", *, commit=False):
        return self._candidate_transition(cand, M.C_ANALYZED, note, now, commit=commit)

    def review_candidate(self, cand, note="reviewed", now="", *, commit=False):
        """후보 검토(NOVELTY_CHECKED→REVIEWED). **검토만 — 선택/승인/배포 아님.**"""
        return self._candidate_transition(cand, M.C_REVIEWED, note, now, commit=commit)

    def archive_candidate(self, cand, note="archived", now="", *, commit=False):
        return self._candidate_transition(cand, M.C_ARCHIVED, note, now, commit=commit)

    # ══════════════ record_hypothesis ══════════════
    def record_hypothesis(self, cand, hypothesis, rationale="", expected_signal="", now="",
                          *, commit=False) -> HypothesisRecord:
        """후보 가설 기록(불변). **기록만.**"""
        self._candidate_meta(cand)
        hid = M.hypothesis_id(cand, hypothesis)
        rec = HypothesisRecord(hypothesis_id=hid, candidate_id=cand, hypothesis=hypothesis,
                               rationale=rationale, expected_signal=expected_signal, created_at=now,
                               input_hash=input_digest(cand, hypothesis),
                               previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.hypothesis_exists, ledger.hypotheses_head, ledger.append_hypothesis,
                         hid, rec, commit=commit)
        self._artifact(M.ART_HYPOTHESIS, hid, M.artifact_id(M.ART_CANDIDATE, cand), now,
                       commit=commit)
        return HypothesisRecord(**rec)

    # ══════════════ analyze_novelty (결정적, 후보 전이) ══════════════
    def analyze_novelty(self, cand, now="", *, commit=False) -> NoveltyRecord:
        """신규성 분석(기존 후보 대비 결정적 점수). 후보 ANALYZED→NOVELTY_CHECKED. **분석·기록만.**"""
        m = self._candidate_meta(cand)
        priors = [self._candidate_meta(c)["statement"] for c in ledger.candidate_ids()
                  if c != cand]
        score = M.novelty_score(m["statement"], priors)
        level = M.classify_novelty(score)
        seq = len(ledger.novelty_for(cand))
        nid = M.novelty_id(cand, seq)
        rec = NoveltyRecord(novelty_id=nid, candidate_id=cand, score=score, level=level,
                            compared_count=len(priors), created_at=now,
                            input_hash=input_digest(cand, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.novelty_exists, ledger.novelty_head, ledger.append_novelty, nid,
                         rec, commit=commit)
        self._artifact(M.ART_NOVELTY, nid, M.artifact_id(M.ART_CANDIDATE, cand), now, commit=commit)
        if self.candidate_state(cand) == M.C_ANALYZED:
            self._candidate_transition(cand, M.C_NOVELTY_CHECKED, "novelty checked", now,
                                       commit=commit)
        return NoveltyRecord(**rec)

    # ══════════════ record_evidence ══════════════
    def record_evidence(self, cand, evidence_ref, evidence_type, source_layer="", now="",
                        *, commit=False) -> EvidenceRecord:
        """후보 증거 기록(불변). **기록만.**"""
        self._candidate_meta(cand)
        if evidence_type not in M.EVIDENCE_TYPES:
            raise ValueError(f"미지원 evidence_type {evidence_type}")
        seq = len(ledger.evidence_for(cand))
        eid = M.evidence_id(cand, evidence_ref, seq)
        rec = EvidenceRecord(evidence_id=eid, candidate_id=cand, evidence_ref=evidence_ref,
                             evidence_type=evidence_type, source_layer=source_layer, created_at=now,
                             input_hash=input_digest(cand, evidence_ref, seq),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.evidence_exists, ledger.evidence_head, ledger.append_evidence, eid,
                         rec, commit=commit)
        return EvidenceRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, scope="SYSTEM", now="", *, commit=False) -> GenerationReportRecord:
        """생성 리포트(세션·후보·가설·신규성·증거 집계). **is_binding=False, GENERATED ≠ SELECTED.**"""
        candidates = ledger.candidate_ids()
        states = {c: self.candidate_state(c) for c in candidates}
        cat_dist: dict = {}
        for c in candidates:
            cat = self._candidate_meta(c)["category"]
            cat_dist[cat] = cat_dist.get(cat, 0) + 1
        nov_dist: dict = {}
        for n in ledger.read_novelty():
            nov_dist[n.get("level")] = nov_dist.get(n.get("level"), 0) + 1
        rid = M.report_id(scope, now)
        rec = GenerationReportRecord(
            report_id=rid, scope=scope, session_count=len(ledger.session_ids()),
            candidate_count=len(candidates),
            reviewed_candidate_count=sum(1 for st in states.values()
                                         if st in (M.C_REVIEWED, M.C_ARCHIVED)),
            hypothesis_count=len(ledger.read_hypotheses()), novelty_count=len(ledger.read_novelty()),
            evidence_count=len(ledger.read_evidence()),
            category_distribution=dict(sorted(cat_dist.items())),
            novelty_distribution=dict(sorted(nov_dist.items())), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.report_exists, ledger.reports_head, ledger.append_report, rid, rec,
                         commit=commit)
        self._artifact(M.ART_REPORT, rid, "", now, commit=commit)
        return GenerationReportRecord(**rec)

    def verify_integrity(self) -> dict:
        from jarvis.research_strategy_generation.verify import verify_chain
        return verify_chain()

    def list_candidates(self) -> list:
        return ledger.candidate_ids()

    def candidates_in_state(self, state) -> list:
        return sorted(c for c in ledger.candidate_ids() if self.candidate_state(c) == state)

    def summary(self, now="") -> GenerationSummary:
        return GenerationSummary(
            timestamp=now, session_event_count=len(ledger.read_session_events()),
            session_count=len(ledger.session_ids()),
            candidate_event_count=len(ledger.read_candidate_events()),
            candidate_count=len(ledger.candidate_ids()),
            hypothesis_count=len(ledger.read_hypotheses()), novelty_count=len(ledger.read_novelty()),
            evidence_count=len(ledger.read_evidence()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
