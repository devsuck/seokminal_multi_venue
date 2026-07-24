"""Research Conflict Resolution Engine (P11.9) — 연구 충돌 분석·해소. **리뷰·분석 전용.**

여러 AI 연구 에이전트의 이견을 기록·분석·해소한다. **거래 전략 선택·배포 승인·연구 결과 수정·에이전트 무시·
행위 실행 없음.** 원본 주장·증거 출처·에이전트 신원·추론 이력·소수의견을 보존한다. 삭제·덮어쓰기 없음.
execution/broker/portfolio/risk/permission/deployment/live import·호출 없음. CONFLICT ≠ EXECUTION · RESOLUTION ≠
APPROVAL · CONSENSUS ≠ DEPLOYMENT. 결정적·불변·append-only·이벤트 소싱.
"""
from __future__ import annotations

from jarvis.research_conflict_resolution import ledger
from jarvis.research_conflict_resolution.models import (
    ART_CLAIM,
    ART_CONFLICT,
    ART_OUTCOME,
    ART_REPORT,
    ART_SESSION,
    C_ANALYZING,
    C_ARCHIVED,
    C_DETECTED,
    C_DISCUSSING,
    C_RESOLVED,
    EVIDENCE_TYPES,
    GENESIS,
    OPEN_STATES,
    RESOLUTION_TYPES,
    ArtifactRecord,
    ClaimRecord,
    ConflictClosedError,
    ConflictEventRecord,
    ConflictReportRecord,
    ConflictSummary,
    ConsensusRecord,
    EvidenceRecord,
    IllegalConflictTransition,
    ImmutableClaimError,
    ImmutableEvidenceError,
    ImmutableMinorityError,
    ImmutableOutcomeError,
    ImmutablePositionError,
    InvalidEvidenceType,
    InvalidResolutionType,
    MinorityRecord,
    OutcomeRecord,
    PositionRecord,
    RegistryRecord,
    SessionRecord,
    UnknownClaimError,
    UnknownConflictError,
    UnknownRegistryError,
    artifact_id as _artifact_id,
    can_transition,
    claim_id as _claim_id,
    conflict_event_id as _conflict_event_id,
    conflict_id as _conflict_id,
    consensus_id as _consensus_id,
    content_hash,
    derive_resolution,
    evidence_id as _evidence_id,
    input_digest,
    minority_id as _minority_id,
    position_id as _position_id,
    registry_id as _registry_id,
    report_id as _report_id,
    resolution_id as _resolution_id,
    session_id as _session_id,
)

_DISCLAIMER = ("Research Conflict Resolution 데이터 — CONFLICT ≠ EXECUTION · RESOLUTION ≠ APPROVAL · CONSENSUS ≠ "
               "DEPLOYMENT. 충돌 기록·분석 전용 — 전략 선택/배포 승인/연구결과 수정/에이전트 무시/실행 없음. "
               "원본 주장·증거·신원·추론·소수의견 보존, 삭제·덮어쓰기 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchConflictResolutionEngine:
    """연구 충돌 분석·해소 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/승인/수정 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, conflict: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, conflict_id=conflict, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ Registry ══════════════
    def register_registry(self, name: str, mandate: str = "", now: str = "",
                        *, commit: bool = False) -> RegistryRecord:
        rid = _registry_id(name)
        existing = ledger.get_registry(rid)
        if existing is not None:
            return RegistryRecord(**{k: v for k, v in existing.items()
                                     if k in RegistryRecord.__dataclass_fields__})
        rec = RegistryRecord(registry_id=rid, name=name, mandate=mandate, created_at=now,
                             input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.registry_exists(rid):
            head = ledger.registry_head()
            ledger.append_registry(_seal(rec, head["record_hash"] if head else GENESIS))
        return RegistryRecord(**rec)

    def _require_registry(self, rid: str) -> dict:
        rec = ledger.get_registry(rid)
        if rec is None:
            raise UnknownRegistryError(f"미등록 레지스트리 {rid}")
        return rec

    # ══════════════ register_conflict (event-sourced) ══════════════
    def _case_event(self, conflict: str, registry: str, subject: str, description: str, frm: str,
                  to: str, note: str, now: str, *, commit: bool) -> ConflictEventRecord:
        seq = len(ledger.conflict_events(conflict))
        eid = _conflict_event_id(conflict, to, seq)
        rec = ConflictEventRecord(event_id=eid, conflict_id=conflict, registry_id=registry,
                                  subject=subject, description=description, from_state=frm,
                                  to_state=to, note=note, occurred_at=now,
                                  input_hash=input_digest(conflict, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.case_event_exists(eid):
            head = ledger.cases_head()
            ledger.append_case_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ConflictEventRecord(**rec)

    def register_conflict(self, registry: str, subject: str, description: str = "", now: str = "",
                        *, commit: bool = False) -> ConflictEventRecord:
        """충돌 케이스 등록(DETECTED). **탐지·기록만.**"""
        self._require_registry(registry)
        conflict = _conflict_id(registry, subject)
        evs = ledger.conflict_events(conflict)
        if evs:
            g = evs[0]
            return ConflictEventRecord(**{k: v for k, v in g.items()
                                          if k in ConflictEventRecord.__dataclass_fields__})
        ev = self._case_event(conflict, registry, subject, description, GENESIS, C_DETECTED,
                            "detected", now, commit=commit)
        self._artifact(ART_CONFLICT, conflict, "", conflict, now, commit=commit)
        return ev

    def current_state(self, conflict: str) -> str | None:
        evs = ledger.conflict_events(conflict)
        return evs[-1].get("to_state") if evs else None

    def conflict_meta(self, conflict: str) -> dict:
        evs = ledger.conflict_events(conflict)
        if not evs:
            raise UnknownConflictError(f"미등록 충돌 {conflict}")
        g = evs[0]
        return {"conflict_id": conflict, "registry_id": g.get("registry_id"),
                "subject": g.get("subject"), "description": g.get("description"),
                "state": evs[-1].get("to_state")}

    def _require_conflict(self, conflict: str) -> str:
        st = self.current_state(conflict)
        if st is None:
            raise UnknownConflictError(f"미등록 충돌 {conflict}")
        return st

    def _require_open(self, conflict: str) -> str:
        st = self._require_conflict(conflict)
        if st not in OPEN_STATES:
            raise ConflictClosedError(f"{conflict} 종료({st}) — 이력 편집 불가")
        return st

    def _transition(self, conflict: str, to: str, note: str, now: str, *, commit: bool) -> ConflictEventRecord:
        frm = self._require_conflict(conflict)
        if not can_transition(frm, to):
            raise IllegalConflictTransition(f"{conflict} {frm}→{to} 불가")
        m = self.conflict_meta(conflict)
        return self._case_event(conflict, m["registry_id"], m["subject"], m["description"], frm,
                              to, note, now, commit=commit)

    def start_analysis(self, conflict, now="", *, commit=False):
        return self._transition(conflict, C_ANALYZING, "analyzing", now, commit=commit)

    def archive_conflict(self, conflict, now="", *, commit=False):
        return self._transition(conflict, C_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ add_claim (preserve original claims + identity) ══════════════
    def add_claim(self, conflict: str, agent: str, conclusion: str, rationale: str = "", now: str = "",
                *, commit: bool = False) -> ClaimRecord:
        """상충 주장 추가(불변·보존). 원본 주장·에이전트 신원·추론 보존. **기록만.**"""
        self._require_open(conflict)
        cid = _claim_id(conflict, agent, conclusion)
        existing = ledger.get_claim(cid)
        if existing is not None:
            if existing.get("rationale") != rationale:
                raise ImmutableClaimError(f"{cid} 주장 불변 — 변경 불가")
            return ClaimRecord(**{k: v for k, v in existing.items()
                                  if k in ClaimRecord.__dataclass_fields__})
        rec = ClaimRecord(claim_id=cid, conflict_id=conflict, agent=agent, conclusion=conclusion,
                          rationale=rationale, created_at=now,
                          input_hash=input_digest(conflict, agent, conclusion),
                          previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.claim_exists(cid):
            head = ledger.claims_head()
            ledger.append_claim(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CONFLICT, conflict)
        self._artifact(ART_CLAIM, cid, parent if ledger.artifact_exists(parent) else "", conflict,
                       now, commit=commit)
        return ClaimRecord(**rec)

    def _require_claim(self, cid: str) -> dict:
        rec = ledger.get_claim(cid)
        if rec is None:
            raise UnknownClaimError(f"미등록 주장 {cid}")
        return rec

    # ══════════════ attach_evidence (READ ONLY source refs) ══════════════
    def attach_evidence(self, claim: str, layer: str, ref: str, evidence_type: str, detail: str = "",
                      now: str = "", *, commit: bool = False, verify_ref: bool = False) -> EvidenceRecord:
        """주장에 증거 참조 첨부(불변·보존). 상위 참조는 READ ONLY. **참조만 — 상위 무수정.**"""
        crec = self._require_claim(claim)
        conflict = crec.get("conflict_id")
        self._require_open(conflict)
        if evidence_type not in EVIDENCE_TYPES:
            raise InvalidEvidenceType(f"미등록 증거 유형 {evidence_type}")
        if verify_ref and not ledger.source_ref_exists(layer, ref):
            raise UnknownClaimError(f"상위 소스 없음 {layer}:{ref}")
        eid = _evidence_id(claim, layer, ref)
        for r in ledger.claim_evidence(claim):
            if r.get("evidence_id") == eid:
                if r.get("detail") != detail:
                    raise ImmutableEvidenceError(f"{eid} 증거 불변 — 변경 불가")
                return EvidenceRecord(**{k: v for k, v in r.items()
                                         if k in EvidenceRecord.__dataclass_fields__})
        rec = EvidenceRecord(evidence_id=eid, claim_id=claim, conflict_id=conflict, layer=layer,
                             ref=ref, evidence_type=evidence_type, detail=detail, read_only=True,
                             created_at=now, input_hash=input_digest(claim, layer, ref),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.evidence_exists(eid):
            head = ledger.evidence_head()
            ledger.append_evidence(_seal(rec, head["record_hash"] if head else GENESIS))
        return EvidenceRecord(**rec)

    # ══════════════ record_agent_position (reasoning history) ══════════════
    def record_agent_position(self, conflict: str, agent: str, backed_claim: str, rationale: str = "",
                            now: str = "", *, commit: bool = False) -> PositionRecord:
        """에이전트 포지션(지지 주장 + 추론) 기록(불변·보존). **기록만.**"""
        self._require_open(conflict)
        if not ledger.claim_exists(backed_claim):
            raise UnknownClaimError(f"미등록 주장 {backed_claim}")
        pid = _position_id(conflict, agent)
        existing = ledger.get_position(pid)
        if existing is not None:
            if existing.get("backed_claim") != backed_claim:
                raise ImmutablePositionError(f"{pid} 포지션 불변 — 변경 불가")
            return PositionRecord(**{k: v for k, v in existing.items()
                                     if k in PositionRecord.__dataclass_fields__})
        rec = PositionRecord(position_id=pid, conflict_id=conflict, agent=agent,
                             backed_claim=backed_claim, rationale=rationale, created_at=now,
                             input_hash=input_digest(conflict, agent), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.position_exists(pid):
            head = ledger.positions_head()
            ledger.append_position(_seal(rec, head["record_hash"] if head else GENESIS))
        return PositionRecord(**rec)

    # ══════════════ compare_claims (deterministic analysis) ══════════════
    def _tallies(self, conflict: str) -> tuple:
        claims = [c.get("claim_id") for c in ledger.conflict_claims(conflict)]
        support = {c: 0 for c in claims}
        for p in ledger.conflict_positions(conflict):
            bc = p.get("backed_claim")
            if bc in support:
                support[bc] += 1
        evidence = {c: len(ledger.claim_evidence(c)) for c in claims}
        return dict(sorted(support.items())), dict(sorted(evidence.items()))

    def compare_claims(self, conflict: str) -> dict:
        """주장 비교 분석(결정적): 지지·증거 집계 + 제안 해소 유형·주도 주장. **분석만 — 결정 아님.**"""
        self._require_conflict(conflict)
        support, evidence = self._tallies(conflict)
        rtype, leading = derive_resolution(support, evidence)
        return {"conflict_id": conflict, "support_tally": support, "evidence_tally": evidence,
                "suggested_type": rtype, "leading_claim": leading,
                "claim_count": len(support), "position_count": sum(support.values())}

    # ══════════════ start_resolution ══════════════
    def start_resolution(self, conflict: str, facilitator: str = "", method: str = "analysis",
                       now: str = "", *, commit: bool = False) -> SessionRecord:
        """해소 세션 시작(ANALYZING→DISCUSSING). **논의만.**"""
        st = self._require_conflict(conflict)
        if st == C_ANALYZING:
            self._transition(conflict, C_DISCUSSING, "start_resolution", now, commit=commit)
        seq = len(ledger.conflict_sessions(conflict))
        sid = _session_id(conflict, seq)
        rec = SessionRecord(session_id=sid, conflict_id=conflict, facilitator=facilitator,
                            method=method, started_at=now, input_hash=input_digest(conflict, seq),
                            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.session_exists(sid):
            head = ledger.sessions_head()
            ledger.append_session(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CONFLICT, conflict)
        self._artifact(ART_SESSION, sid, parent if ledger.artifact_exists(parent) else "", conflict,
                       now, commit=commit)
        return SessionRecord(**rec)

    # ══════════════ record_resolution (+consensus, DISCUSSING→RESOLVED) ══════════════
    def record_resolution(self, conflict: str, session: str, resolution_type: str,
                        winning_claim: str = "", rationale: str = "", now: str = "",
                        *, commit: bool = False) -> OutcomeRecord:
        """해소 결과 기록(불변) + 합의 스냅샷 + DISCUSSING→RESOLVED. **RESOLUTION ≠ APPROVAL.**"""
        st = self._require_conflict(conflict)
        if resolution_type not in RESOLUTION_TYPES:
            raise InvalidResolutionType(f"미등록 해소 유형 {resolution_type}")
        support, evidence = self._tallies(conflict)
        computed_type, leading = derive_resolution(support, evidence)
        # 합의 스냅샷(결정적) 기록
        kid = _consensus_id(conflict, session)
        if not ledger.consensus_exists(kid):
            krec = ConsensusRecord(
                consensus_id=kid, conflict_id=conflict, session_id=session, support_tally=support,
                evidence_tally=evidence, leading_claim=leading, computed_type=computed_type,
                participant_count=sum(support.values()), created_at=now,
                input_hash=input_digest(conflict, session), previous_hash=GENESIS).to_dict()
            krec["record_hash"] = content_hash(krec)
            if commit:
                head = ledger.consensus_head()
                ledger.append_consensus(_seal(krec, head["record_hash"] if head else GENESIS))
        rid = _resolution_id(conflict, session)
        existing = ledger.get_outcome(rid)
        if existing is not None:
            if existing.get("resolution_type") != resolution_type:
                raise ImmutableOutcomeError(f"{rid} 해소 결과 불변 — 변경 불가")
            out = OutcomeRecord(**{k: v for k, v in existing.items()
                                   if k in OutcomeRecord.__dataclass_fields__})
        else:
            rec = OutcomeRecord(resolution_id=rid, conflict_id=conflict, session_id=session,
                                resolution_type=resolution_type, winning_claim=winning_claim,
                                computed_type=computed_type, rationale=rationale, decided_at=now,
                                input_hash=input_digest(conflict, session),
                                previous_hash=GENESIS).to_dict()
            rec["record_hash"] = content_hash(rec)
            if commit and not ledger.outcome_exists(rid):
                head = ledger.outcomes_head()
                ledger.append_outcome(_seal(rec, head["record_hash"] if head else GENESIS))
            out = OutcomeRecord(**rec)
            parent = _artifact_id(ART_SESSION, session)
            self._artifact(ART_OUTCOME, rid, parent if ledger.artifact_exists(parent) else "",
                           conflict, now, commit=commit)
        if st == C_DISCUSSING:
            self._transition(conflict, C_RESOLVED, "resolved", now, commit=commit)
        return out

    # ══════════════ preserve_minority_view ══════════════
    def preserve_minority_view(self, conflict: str, agent: str, opinion: str, backed_claim: str = "",
                             now: str = "", *, commit: bool = False) -> MinorityRecord:
        """소수의견 보존 기록(불변). **소수의견은 결코 삭제되지 않는다.**"""
        self._require_conflict(conflict)
        mid = _minority_id(conflict, agent)
        for r in ledger.conflict_minority(conflict):
            if r.get("minority_id") == mid:
                if r.get("opinion") != opinion:
                    raise ImmutableMinorityError(f"{mid} 소수의견 불변 — 변경 불가")
                return MinorityRecord(**{k: v for k, v in r.items()
                                         if k in MinorityRecord.__dataclass_fields__})
        rec = MinorityRecord(minority_id=mid, conflict_id=conflict, agent=agent,
                             backed_claim=backed_claim, opinion=opinion, created_at=now,
                             input_hash=input_digest(conflict, agent), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.minority_exists(mid):
            head = ledger.minority_head()
            ledger.append_minority(_seal(rec, head["record_hash"] if head else GENESIS))
        return MinorityRecord(**rec)

    def preserve_all_minority(self, conflict: str, winning_claim: str, now: str = "",
                            *, commit: bool = False) -> list:
        """승리 주장을 지지하지 않은 모든 에이전트의 소수의견 자동 보존. **보존만.**"""
        out: list = []
        for p in ledger.conflict_positions(conflict):
            if p.get("backed_claim") != winning_claim:
                out.append(self.preserve_minority_view(
                    conflict, p.get("agent"), f"dissent:{p.get('rationale', '')}",
                    p.get("backed_claim"), now, commit=commit))
        return out

    # ══════════════ generate_report ══════════════
    def generate_report(self, conflict: str, scope: str = "CONFLICT", now: str = "",
                      *, commit: bool = False) -> ConflictReportRecord:
        """충돌 리포트(주장·포지션·증거·소수·해소). **관측 리포트 — is_binding=False.**"""
        st = self._require_conflict(conflict)
        outcomes = ledger.conflict_outcomes(conflict)
        last = outcomes[-1] if outcomes else {}
        rid = _report_id(conflict, scope, now)
        rec = ConflictReportRecord(
            report_id=rid, conflict_id=conflict, scope=scope, lifecycle_state=st,
            claim_count=len(ledger.conflict_claims(conflict)),
            position_count=len(ledger.conflict_positions(conflict)),
            evidence_count=len(ledger.conflict_evidence(conflict)),
            minority_count=len(ledger.conflict_minority(conflict)),
            resolution_type=last.get("resolution_type", ""), winning_claim=last.get("winning_claim", ""),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(conflict, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        parent = _artifact_id(ART_CONFLICT, conflict)
        self._artifact(ART_REPORT, rid, parent if ledger.artifact_exists(parent) else "", conflict,
                       now, commit=commit)
        return ConflictReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_conflict_resolution.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_conflicts(self, registry: str = "") -> list:
        cids = ledger.conflict_ids()
        if registry:
            cids = [c for c in cids
                    if any(ev.get("registry_id") == registry for ev in ledger.conflict_events(c))]
        return sorted(cids)

    def claims_of(self, conflict: str) -> list:
        return sorted(c.get("claim_id") for c in ledger.conflict_claims(conflict))

    def positions_of(self, conflict: str) -> list:
        return sorted(p.get("agent") for p in ledger.conflict_positions(conflict))

    def minority_of(self, conflict: str) -> list:
        return sorted(m.get("agent") for m in ledger.conflict_minority(conflict))

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ConflictSummary:
        return ConflictSummary(
            timestamp=now, registry_count=len(ledger.read_registry()),
            conflict_event_count=len(ledger.read_case_events()),
            claim_count=len(ledger.read_claims()), evidence_count=len(ledger.read_evidence()),
            position_count=len(ledger.read_positions()), session_count=len(ledger.read_sessions()),
            outcome_count=len(ledger.read_outcomes()), minority_count=len(ledger.read_minority()),
            consensus_count=len(ledger.read_consensus()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
