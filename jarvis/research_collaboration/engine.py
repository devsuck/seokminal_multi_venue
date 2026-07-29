"""Research Collaboration Engine (P19) — 다중 에이전트 협업·토론·합의·검토 조정·기록. **실행 없음.**

**거래·전략 배포·권한 부여·자동 실행·자동 승인을 하지 않는다.** execution/broker/portfolio/permission/deployment/
live import·호출 없음. COLLABORATE ≠ EXECUTE · CONSENSUS ≠ APPROVAL · REVIEW ≠ DEPLOYMENT. 결정적·불변·append-only·
이벤트 소싱. P10.6 agent_governance 는 READ ONLY 참조.
"""
from __future__ import annotations

from jarvis.research_collaboration import ledger
from jarvis.research_collaboration import models as M
from jarvis.research_collaboration.models import (
    GENESIS,
    ArtifactRecord,
    CollabEventRecord,
    CollaborationReportRecord,
    CollaborationSummary,
    ConflictEventRecord,
    ConsensusEventRecord,
    HumanReviewEventRecord,
    HumanReviewRequired,
    IllegalTransition,
    ImmutableRecordError,
    MessageRecord,
    ParticipationEventRecord,
    ProposalEventRecord,
    ReviewRecord,
    ReviewerRequired,
    UnknownEntityError,
    content_hash,
    input_digest,
)

_DISCLAIMER = ("Research Collaboration 데이터 — COLLABORATE ≠ EXECUTE · CONSENSUS ≠ APPROVAL · "
               "REVIEW ≠ DEPLOYMENT. 협업·토론·합의·검토 조정·기록 전용 — 거래·전략 배포·권한 부여·자동 실행·자동 승인 없음.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchCollaborationEngine:
    """다중 에이전트 연구 협업 조정 엔진. 불변·append-only·이벤트 소싱·결정적. 실행/배포/거래/승인 권한 없음."""

    # ══════════════ 공통 append(불변·중복 무시) ══════════════
    def _emit(self, spec_read, spec_head, spec_exists, spec_append, rid: str, rec: dict,
              *, commit: bool) -> dict:
        rec = dict(rec)
        rec["record_hash"] = content_hash(rec)
        if commit and not spec_exists(rid):
            head = spec_head()
            spec_append(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, now: str, *, commit: bool) -> ArtifactRecord:
        aid = M.artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref, parent_artifact=parent,
                             created_at=now, input_hash=input_digest(atype, ref),
                             previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_artifacts, ledger.artifacts_head, ledger.artifact_exists,
                         ledger.append_artifact, aid, rec, commit=commit)
        return ArtifactRecord(**rec)

    # ══════════════ 협업 생애주기(event-sourced) ══════════════
    def _collab_event(self, cid, name, obj, frm, to, note, now, *, commit) -> CollabEventRecord:
        seq = len(ledger.collab_events(cid))
        eid = M.collab_event_id(cid, to, seq)
        rec = CollabEventRecord(collab_event_id=eid, collaboration_id=cid, name=name, objective=obj,
                                from_state=frm, to_state=to, note=note, occurred_at=now,
                                input_hash=input_digest(cid, to, seq), previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_collab_events, ledger.collab_head, ledger.collab_event_exists,
                         ledger.append_collab_event, eid, rec, commit=commit)
        return CollabEventRecord(**rec)

    def _collab_meta(self, cid) -> dict:
        evs = ledger.collab_events(cid)
        if not evs:
            raise UnknownEntityError(f"미등록 협업 {cid}")
        g = evs[0]
        return {"name": g.get("name"), "objective": g.get("objective"),
                "state": evs[-1].get("to_state")}

    def collaboration_state(self, cid) -> str | None:
        evs = ledger.collab_events(cid)
        return evs[-1].get("to_state") if evs else None

    def _require_collab(self, cid) -> str:
        st = self.collaboration_state(cid)
        if st is None:
            raise UnknownEntityError(f"미등록 협업 {cid}")
        return st

    def _collab_transition(self, cid, to, note, now, *, commit) -> CollabEventRecord:
        frm = self._require_collab(cid)
        if not M.can_collab_transition(frm, to):
            raise IllegalTransition(f"협업 {cid} {frm}→{to} 불가")
        m = self._collab_meta(cid)
        return self._collab_event(cid, m["name"], m["objective"], frm, to, note, now, commit=commit)

    def create_collaboration(self, name, objective="", now="", *, commit=False) -> CollabEventRecord:
        """연구 협업 생성(genesis CREATED). **협업 시작만.**"""
        cid = M.collaboration_id(name)
        evs = ledger.collab_events(cid)
        if evs:
            g = evs[0]
            if g.get("objective") != objective:
                raise ImmutableRecordError(f"{cid} 협업 불변")
            return CollabEventRecord(**{k: v for k, v in g.items()
                                        if k in CollabEventRecord.__dataclass_fields__})
        ev = self._collab_event(cid, name, objective, GENESIS, M.C_CREATED, "created", now,
                                commit=commit)
        self._artifact(M.ART_COLLABORATION, cid, "", now, commit=commit)
        return ev

    def form_collaboration(self, cid, now="", *, commit=False):
        return self._collab_transition(cid, M.C_FORMING, "forming", now, commit=commit)

    def activate_collaboration(self, cid, now="", *, commit=False):
        return self._collab_transition(cid, M.C_ACTIVE, "active", now, commit=commit)

    def review_collaboration(self, cid, now="", *, commit=False):
        return self._collab_transition(cid, M.C_REVIEWING, "reviewing", now, commit=commit)

    def complete_collaboration(self, cid, now="", *, commit=False):
        return self._collab_transition(cid, M.C_COMPLETED, "completed", now, commit=commit)

    def archive_collaboration(self, cid, now="", *, commit=False):
        return self._collab_transition(cid, M.C_ARCHIVED, "archived", now, commit=commit)

    # ══════════════ 참여 생애주기(event-sourced) ══════════════
    def _participation_event(self, pid, cid, agent, role, spec, frm, to, contribution, note, now,
                             *, commit) -> ParticipationEventRecord:
        seq = len(ledger.participation_events(pid))
        eid = M.participation_event_id(pid, to, seq)
        rec = ParticipationEventRecord(
            participation_event_id=eid, participant_id=pid, collaboration_id=cid, agent_id=agent,
            role=role, specialization=spec, from_state=frm, to_state=to, contribution=contribution,
            note=note, occurred_at=now, input_hash=input_digest(pid, to, seq),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_participations, ledger.participation_head,
                         ledger.participation_exists, ledger.append_participation, eid, rec,
                         commit=commit)
        return ParticipationEventRecord(**rec)

    def _participation_meta(self, pid) -> dict:
        evs = ledger.participation_events(pid)
        if not evs:
            raise UnknownEntityError(f"미등록 참여 {pid}")
        g = evs[0]
        return {"collaboration_id": g.get("collaboration_id"), "agent_id": g.get("agent_id"),
                "role": g.get("role"), "specialization": g.get("specialization"),
                "contribution": g.get("contribution"), "state": evs[-1].get("to_state")}

    def participation_state(self, pid) -> str | None:
        evs = ledger.participation_events(pid)
        return evs[-1].get("to_state") if evs else None

    def _participation_transition(self, pid, to, note, now, *, commit) -> ParticipationEventRecord:
        st = self.participation_state(pid)
        if st is None:
            raise UnknownEntityError(f"미등록 참여 {pid}")
        if not M.can_participation_transition(st, to):
            raise IllegalTransition(f"참여 {pid} {st}→{to} 불가")
        m = self._participation_meta(pid)
        return self._participation_event(pid, m["collaboration_id"], m["agent_id"], m["role"],
                                         m["specialization"], st, to, m["contribution"], note, now,
                                         commit=commit)

    def invite_participant(self, cid, agent_id, role="researcher", specialization="",
                           contribution="", now="", *, commit=False) -> ParticipationEventRecord:
        """참여자 초대(genesis INVITED). P10.6 는 READ ONLY 참조 — 권한/능력 변경 없음."""
        st = self._require_collab(cid)
        if st in (M.C_COMPLETED, M.C_ARCHIVED):
            raise IllegalTransition(f"협업 {cid} 상태 {st} — 초대 불가")
        pid = M.participant_id(cid, agent_id)
        evs = ledger.participation_events(pid)
        if evs:
            return ParticipationEventRecord(**{k: v for k, v in evs[0].items()
                                               if k in ParticipationEventRecord.__dataclass_fields__})
        return self._participation_event(pid, cid, agent_id, role, specialization, GENESIS,
                                         M.P_INVITED, contribution, "invited", now, commit=commit)

    def accept_participation(self, pid, now="", *, commit=False):
        return self._participation_transition(pid, M.P_ACCEPTED, "accepted", now, commit=commit)

    def activate_participation(self, pid, now="", *, commit=False):
        return self._participation_transition(pid, M.P_ACTIVE, "active", now, commit=commit)

    def pause_participation(self, pid, now="", *, commit=False):
        return self._participation_transition(pid, M.P_PAUSED, "paused", now, commit=commit)

    def remove_participation(self, pid, now="", *, commit=False):
        return self._participation_transition(pid, M.P_REMOVED, "removed", now, commit=commit)

    def complete_participation(self, pid, now="", *, commit=False):
        return self._participation_transition(pid, M.P_COMPLETED, "completed", now, commit=commit)

    # ══════════════ 메시지(불변) ══════════════
    def post_message(self, cid, author_agent, message_type, content="", reference_artifacts=None,
                     metadata=None, now="", *, commit=False) -> MessageRecord:
        """연구 메시지 기록(불변). 이전 연구 레코드를 수정하지 않는다. **의사소통 기록만.**"""
        self._require_collab(cid)
        seq = len(ledger.collab_messages(cid))
        mid = M.message_id(cid, author_agent, seq)
        rec = MessageRecord(message_id=mid, collaboration_id=cid, author_agent=author_agent,
                            message_type=message_type, payload_hash=input_digest(content),
                            reference_artifacts=list(reference_artifacts or []),
                            metadata=dict(metadata or {}), recorded_at=now,
                            input_hash=input_digest(cid, author_agent, seq),
                            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_messages, ledger.messages_head, ledger.message_exists,
                         ledger.append_message, mid, rec, commit=commit)
        self._artifact(M.ART_MESSAGE, mid, M.artifact_id(M.ART_COLLABORATION, cid)
                       if ledger.artifact_exists(M.artifact_id(M.ART_COLLABORATION, cid)) else "",
                       now, commit=commit)
        return MessageRecord(**rec)

    # ══════════════ 제안 생애주기(event-sourced) ══════════════
    def _proposal_event(self, prid, cid, author, title, frm, to, note, basis, now,
                        *, commit) -> ProposalEventRecord:
        seq = len(ledger.proposal_events(prid))
        eid = M.proposal_event_id(prid, to, seq)
        rec = ProposalEventRecord(proposal_event_id=eid, proposal_id=prid, collaboration_id=cid,
                                  author_agent=author, title=title, from_state=frm, to_state=to,
                                  note=note, basis=basis, occurred_at=now,
                                  input_hash=input_digest(prid, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_proposal_events, ledger.proposals_head,
                         ledger.proposal_event_exists, ledger.append_proposal_event, eid, rec,
                         commit=commit)
        return ProposalEventRecord(**rec)

    def _proposal_meta(self, prid) -> dict:
        evs = ledger.proposal_events(prid)
        if not evs:
            raise UnknownEntityError(f"미등록 제안 {prid}")
        g = evs[0]
        return {"collaboration_id": g.get("collaboration_id"), "author_agent": g.get("author_agent"),
                "title": g.get("title"), "state": evs[-1].get("to_state")}

    def proposal_state(self, prid) -> str | None:
        evs = ledger.proposal_events(prid)
        return evs[-1].get("to_state") if evs else None

    def _proposal_transition(self, prid, to, note, basis, now, *, commit) -> ProposalEventRecord:
        st = self.proposal_state(prid)
        if st is None:
            raise UnknownEntityError(f"미등록 제안 {prid}")
        if not M.can_proposal_transition(st, to):
            raise IllegalTransition(f"제안 {prid} {st}→{to} 불가")
        m = self._proposal_meta(prid)
        return self._proposal_event(prid, m["collaboration_id"], m["author_agent"], m["title"], st,
                                    to, note, basis, now, commit=commit)

    def create_proposal(self, cid, author_agent, title, now="", *, commit=False) -> ProposalEventRecord:
        """연구 제안 생성(genesis DRAFT)."""
        self._require_collab(cid)
        prid = M.proposal_id(cid, title)
        evs = ledger.proposal_events(prid)
        if evs:
            return ProposalEventRecord(**{k: v for k, v in evs[0].items()
                                          if k in ProposalEventRecord.__dataclass_fields__})
        ev = self._proposal_event(prid, cid, author_agent, title, GENESIS, M.PR_DRAFT, "draft", "",
                                  now, commit=commit)
        self._artifact(M.ART_PROPOSAL, prid, M.artifact_id(M.ART_COLLABORATION, cid)
                       if ledger.artifact_exists(M.artifact_id(M.ART_COLLABORATION, cid)) else "",
                       now, commit=commit)
        return ev

    def submit_proposal(self, prid, now="", *, commit=False):
        return self._proposal_transition(prid, M.PR_SUBMITTED, "submitted", "", now, commit=commit)

    def discuss_proposal(self, prid, now="", *, commit=False):
        return self._proposal_transition(prid, M.PR_DISCUSSION, "discussion", "", now, commit=commit)

    def review_proposal(self, prid, now="", *, commit=False):
        return self._proposal_transition(prid, M.PR_REVIEWED, "reviewed", "", now, commit=commit)

    def _has_closed_human_review(self, cid) -> bool:
        for hr in ledger.collab_human_reviews(cid):
            evs = ledger.human_review_events(hr)
            if evs and evs[-1].get("to_state") == M.HR_CLOSED:
                return True
        return False

    def _has_recorded_consensus(self, cid) -> bool:
        for cons in ledger.collab_consensus(cid):
            evs = ledger.consensus_events(cons)
            if evs and evs[-1].get("to_state") == M.CS_RECORDED:
                return True
        return False

    def accept_proposal(self, prid, now="", *, commit=False) -> ProposalEventRecord:
        """제안 승인(REVIEWED→ACCEPTED). **사람 검토(CLOSED) 또는 기록된 합의(RECORDED) 필수. 자동 승인 없음.**"""
        m = self._proposal_meta(prid)
        cid = m["collaboration_id"]
        hr = self._has_closed_human_review(cid)
        cons = self._has_recorded_consensus(cid)
        if not (hr or cons):
            raise HumanReviewRequired(f"{prid} 승인 불가 — 사람 검토 또는 기록된 합의 필요")
        basis = "human_review" if hr else "consensus"
        return self._proposal_transition(prid, M.PR_ACCEPTED, "accepted", basis, now, commit=commit)

    def reject_proposal(self, prid, now="", *, commit=False):
        return self._proposal_transition(prid, M.PR_REJECTED, "rejected", "", now, commit=commit)

    # ══════════════ 동료 검토(불변) ══════════════
    def add_peer_review(self, cid, reviewer, target, category, score, comments="", evidence=None,
                        now="", *, commit=False) -> ReviewRecord:
        """에이전트 동료 검토 기록(불변, 연구 메타데이터만). is_binding=False."""
        self._require_collab(cid)
        seq = len([r for r in ledger.read_reviews()
                   if r.get("reviewer") == reviewer and r.get("target") == target
                   and r.get("category") == category])
        rid = M.review_id(reviewer, target, category, seq)
        rec = ReviewRecord(review_id=rid, collaboration_id=cid, reviewer=reviewer, target=target,
                           category=category, score=float(score), comments=comments,
                           evidence=list(evidence or []), is_binding=False, recorded_at=now,
                           input_hash=input_digest(reviewer, target, category, seq),
                           previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_reviews, ledger.reviews_head, ledger.review_exists,
                         ledger.append_review, rid, rec, commit=commit)
        self._artifact(M.ART_REVIEW, rid, "", now, commit=commit)
        return ReviewRecord(**rec)

    # ══════════════ 합의 생애주기(event-sourced) ══════════════
    def _consensus_event(self, cons, cid, topic, frm, to, positions, note, now,
                         *, commit) -> ConsensusEventRecord:
        seq = len(ledger.consensus_events(cons))
        eid = M.consensus_event_id(cons, to, seq)
        rec = ConsensusEventRecord(consensus_event_id=eid, consensus_id=cons, collaboration_id=cid,
                                   topic=topic, from_state=frm, to_state=to,
                                   positions=dict(positions or {}), is_approval=False, note=note,
                                   occurred_at=now, input_hash=input_digest(cons, to, seq),
                                   previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_consensus_events, ledger.consensus_head,
                         ledger.consensus_event_exists, ledger.append_consensus_event, eid, rec,
                         commit=commit)
        return ConsensusEventRecord(**rec)

    def _consensus_meta(self, cons) -> dict:
        evs = ledger.consensus_events(cons)
        if not evs:
            raise UnknownEntityError(f"미등록 합의 {cons}")
        g = evs[0]
        return {"collaboration_id": g.get("collaboration_id"), "topic": g.get("topic"),
                "state": evs[-1].get("to_state")}

    def consensus_state(self, cons) -> str | None:
        evs = ledger.consensus_events(cons)
        return evs[-1].get("to_state") if evs else None

    def _consensus_transition(self, cons, to, positions, note, now, *, commit):
        st = self.consensus_state(cons)
        if st is None:
            raise UnknownEntityError(f"미등록 합의 {cons}")
        if not M.can_consensus_transition(st, to):
            raise IllegalTransition(f"합의 {cons} {st}→{to} 불가")
        m = self._consensus_meta(cons)
        return self._consensus_event(cons, m["collaboration_id"], m["topic"], st, to, positions,
                                     note, now, commit=commit)

    def open_consensus(self, cid, topic, now="", *, commit=False) -> ConsensusEventRecord:
        """합의 추적 시작(genesis OPEN). **합의 ≠ 승인/배포/거래.**"""
        self._require_collab(cid)
        cons = M.consensus_id(cid, topic)
        evs = ledger.consensus_events(cons)
        if evs:
            return ConsensusEventRecord(**{k: v for k, v in evs[0].items()
                                           if k in ConsensusEventRecord.__dataclass_fields__})
        ev = self._consensus_event(cons, cid, topic, GENESIS, M.CS_OPEN, {}, "opened", now,
                                   commit=commit)
        self._artifact(M.ART_CONSENSUS, cons, "", now, commit=commit)
        return ev

    def discuss_consensus(self, cons, positions=None, now="", *, commit=False):
        return self._consensus_transition(cons, M.CS_DISCUSSION, positions, "discussion", now,
                                          commit=commit)

    def tentative_consensus(self, cons, positions=None, now="", *, commit=False):
        return self._consensus_transition(cons, M.CS_TENTATIVE, positions, "tentative", now,
                                          commit=commit)

    def review_consensus(self, cons, positions=None, now="", *, commit=False):
        return self._consensus_transition(cons, M.CS_REVIEWED, positions, "reviewed", now,
                                          commit=commit)

    def record_consensus(self, cons, positions=None, now="", *, commit=False):
        """합의 기록(REVIEWED→RECORDED). **기록일 뿐 — 승인·배포·거래 권한 아님.**"""
        return self._consensus_transition(cons, M.CS_RECORDED, positions, "recorded", now,
                                          commit=commit)

    # ══════════════ 갈등 생애주기(event-sourced) ══════════════
    def _conflict_event(self, conf, cid, ctype, frm, to, desc, outcome, now,
                        *, commit) -> ConflictEventRecord:
        seq = len(ledger.conflict_events(conf))
        eid = M.conflict_event_id(conf, to, seq)
        rec = ConflictEventRecord(conflict_event_id=eid, conflict_id=conf, collaboration_id=cid,
                                  conflict_type=ctype, from_state=frm, to_state=to, description=desc,
                                  outcome=outcome, occurred_at=now, input_hash=input_digest(conf, to, seq),
                                  previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_conflict_events, ledger.conflicts_head,
                         ledger.conflict_event_exists, ledger.append_conflict_event, eid, rec,
                         commit=commit)
        return ConflictEventRecord(**rec)

    def _conflict_meta(self, conf) -> dict:
        evs = ledger.conflict_events(conf)
        if not evs:
            raise UnknownEntityError(f"미등록 갈등 {conf}")
        g = evs[0]
        return {"collaboration_id": g.get("collaboration_id"), "conflict_type": g.get("conflict_type"),
                "description": g.get("description"), "state": evs[-1].get("to_state")}

    def conflict_state(self, conf) -> str | None:
        evs = ledger.conflict_events(conf)
        return evs[-1].get("to_state") if evs else None

    def _conflict_transition(self, conf, to, outcome, now, *, commit):
        st = self.conflict_state(conf)
        if st is None:
            raise UnknownEntityError(f"미등록 갈등 {conf}")
        if not M.can_conflict_transition(st, to):
            raise IllegalTransition(f"갈등 {conf} {st}→{to} 불가")
        m = self._conflict_meta(conf)
        return self._conflict_event(conf, m["collaboration_id"], m["conflict_type"], st, to,
                                    m["description"], outcome, now, commit=commit)

    def open_conflict(self, cid, conflict_type, description="", now="", *, commit=False):
        """연구 이견 추적 시작(genesis OPEN)."""
        self._require_collab(cid)
        seq = len(ledger.collab_conflicts(cid))
        conf = M.conflict_id(cid, conflict_type, seq)
        ev = self._conflict_event(conf, cid, conflict_type, GENESIS, M.CF_OPEN, description, "",
                                  now, commit=commit)
        return ev

    def analyze_conflict(self, conf, now="", *, commit=False):
        return self._conflict_transition(conf, M.CF_ANALYZING, "", now, commit=commit)

    def resolve_conflict(self, conf, outcome="", now="", *, commit=False):
        """갈등 해소(ANALYZING→RESOLVED). **결과 기록만 — 선택을 강제하지 않는다.**"""
        return self._conflict_transition(conf, M.CF_RESOLVED, outcome, now, commit=commit)

    def document_conflict(self, conf, outcome="", now="", *, commit=False):
        return self._conflict_transition(conf, M.CF_DOCUMENTED, outcome, now, commit=commit)

    # ══════════════ 사람 검토 생애주기(event-sourced) ══════════════
    def _human_review_event(self, hr, cid, subject, reviewer, frm, to, comment, now,
                            *, commit) -> HumanReviewEventRecord:
        seq = len(ledger.human_review_events(hr))
        eid = M.human_review_event_id(hr, to, seq)
        rec = HumanReviewEventRecord(human_review_event_id=eid, human_review_id=hr,
                                     collaboration_id=cid, subject=subject, reviewer=reviewer,
                                     from_state=frm, to_state=to, comment=comment, occurred_at=now,
                                     input_hash=input_digest(hr, to, seq),
                                     previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_human_review_events, ledger.human_reviews_head,
                         ledger.human_review_event_exists, ledger.append_human_review_event, eid,
                         rec, commit=commit)
        return HumanReviewEventRecord(**rec)

    def _human_review_meta(self, hr) -> dict:
        evs = ledger.human_review_events(hr)
        if not evs:
            raise UnknownEntityError(f"미등록 사람검토 {hr}")
        g = evs[0]
        return {"collaboration_id": g.get("collaboration_id"), "subject": g.get("subject"),
                "reviewer": evs[-1].get("reviewer"), "state": evs[-1].get("to_state")}

    def human_review_state(self, hr) -> str | None:
        evs = ledger.human_review_events(hr)
        return evs[-1].get("to_state") if evs else None

    def request_human_review(self, cid, subject, now="", *, commit=False) -> HumanReviewEventRecord:
        """사람 검토 요청(genesis REQUESTED). **자동 수락 없음.**"""
        self._require_collab(cid)
        seq = len(ledger.collab_human_reviews(cid))
        hr = M.human_review_id(cid, subject, seq)
        return self._human_review_event(hr, cid, subject, "", GENESIS, M.HR_REQUESTED, "", now,
                                        commit=commit)

    def assign_human_review(self, hr, reviewer, now="", *, commit=False) -> HumanReviewEventRecord:
        """검토자 배정(REQUESTED→ASSIGNED). **검토자 신원 필수 — 익명 승인 없음.**"""
        if not reviewer or not str(reviewer).strip():
            raise ReviewerRequired("검토자 신원 필수 — 익명 승인 불가")
        st = self.human_review_state(hr)
        if st is None:
            raise UnknownEntityError(f"미등록 사람검토 {hr}")
        if not M.can_human_review_transition(st, M.HR_ASSIGNED):
            raise IllegalTransition(f"사람검토 {hr} {st}→ASSIGNED 불가")
        m = self._human_review_meta(hr)
        return self._human_review_event(hr, m["collaboration_id"], m["subject"], reviewer, st,
                                        M.HR_ASSIGNED, "assigned", now, commit=commit)

    def _hr_transition(self, hr, to, comment, now, *, commit) -> HumanReviewEventRecord:
        st = self.human_review_state(hr)
        if st is None:
            raise UnknownEntityError(f"미등록 사람검토 {hr}")
        if not M.can_human_review_transition(st, to):
            raise IllegalTransition(f"사람검토 {hr} {st}→{to} 불가")
        m = self._human_review_meta(hr)
        return self._human_review_event(hr, m["collaboration_id"], m["subject"], m["reviewer"], st,
                                        to, comment, now, commit=commit)

    def start_human_review(self, hr, now="", *, commit=False):
        return self._hr_transition(hr, M.HR_UNDER_REVIEW, "", now, commit=commit)

    def comment_human_review(self, hr, comment, now="", *, commit=False):
        return self._hr_transition(hr, M.HR_COMMENTED, comment, now, commit=commit)

    def close_human_review(self, hr, now="", *, commit=False):
        return self._hr_transition(hr, M.HR_CLOSED, "", now, commit=commit)

    # ══════════════ generate_report ══════════════
    def generate_report(self, cid, scope="COLLABORATION", now="", *, commit=False) -> CollaborationReportRecord:
        """협업 리포트(참여·메시지·제안·검토·합의·갈등·사람검토 집계). **is_binding=False.**"""
        self._require_collab(cid)
        rid = M.report_id(cid, scope, now)
        rec = CollaborationReportRecord(
            report_id=rid, collaboration_id=cid, scope=scope,
            collaboration_state=self.collaboration_state(cid),
            participant_count=len(ledger.collab_participants(cid)),
            message_count=len(ledger.collab_messages(cid)),
            proposal_count=len(ledger.collab_proposals(cid)),
            review_count=len(ledger.collab_reviews(cid)),
            consensus_count=len(ledger.collab_consensus(cid)),
            conflict_count=len(ledger.collab_conflicts(cid)),
            human_review_count=len(ledger.collab_human_reviews(cid)), is_binding=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(cid, scope, now),
            previous_hash=GENESIS).to_dict()
        rec = self._emit(ledger.read_reports, ledger.reports_head, ledger.report_exists,
                         ledger.append_report, rid, rec, commit=commit)
        self._artifact(M.ART_REPORT, rid, M.artifact_id(M.ART_COLLABORATION, cid)
                       if ledger.artifact_exists(M.artifact_id(M.ART_COLLABORATION, cid)) else "",
                       now, commit=commit)
        return CollaborationReportRecord(**rec)

    # ══════════════ verify / 조회 / summary ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_collaboration.verify import verify_chain
        return verify_chain()

    def list_collaborations(self) -> list:
        return ledger.collaboration_ids()

    def collaborations_in_state(self, state) -> list:
        return sorted(c for c in ledger.collaboration_ids() if self.collaboration_state(c) == state)

    def list_participants(self, cid) -> list:
        return ledger.collab_participants(cid)

    def summary(self, now="") -> CollaborationSummary:
        return CollaborationSummary(
            timestamp=now, collab_event_count=len(ledger.read_collab_events()),
            participation_event_count=len(ledger.read_participations()),
            message_count=len(ledger.read_messages()),
            proposal_event_count=len(ledger.read_proposal_events()),
            review_count=len(ledger.read_reviews()),
            consensus_event_count=len(ledger.read_consensus_events()),
            conflict_event_count=len(ledger.read_conflict_events()),
            human_review_event_count=len(ledger.read_human_review_events()),
            report_count=len(ledger.read_reports()), artifact_count=len(ledger.read_artifacts()))
