"""Research Council Engine (P11.6) — 다중 AI 연구 에이전트 협의체. **협의·기록 전용.**

여러 연구 에이전트가 연구 토론을 조율한다. **실행하지 않는다. 배포를 승인하지 않는다. 상위 연구를 수정하지
않는다.** 협의체는 권고만 할 수 있다 — 전략 승인·배포·거래·자본 할당·권한 변경·설정 변경·주문 실행·브로커
호출·포트폴리오 수정 없음. execution/broker/portfolio/risk/permission/live/deployment import·호출 없음.
COUNCIL ≠ EXECUTION · CONSENSUS ≠ APPROVAL · RECOMMENDATION ≠ DEPLOYMENT. 불변·append-only·이벤트 소싱·결정적.
"""
from __future__ import annotations

from jarvis.research_council import ledger
from jarvis.research_council.models import (
    AGENT_ROLES,
    ART_ARGUMENT,
    ART_CONSENSUS,
    ART_COUNCIL,
    ART_SESSION,
    ART_SUMMARY,
    GENESIS,
    S_ACTIVE,
    S_CLOSED,
    S_CONSENSUS,
    S_CREATED,
    S_DISCUSSING,
    S_VOTING,
    STANCES,
    STANCE_AGAINST,
    STANCE_FOR,
    VOTE_CHOICES,
    ArgumentRecord,
    ConsensusRecord,
    CouncilRecord,
    CouncilReportRecord,
    CouncilSummary,
    DiscussionRecord,
    IllegalSessionTransition,
    ImmutableArgumentError,
    ImmutableConsensusError,
    ImmutableCouncilError,
    ImmutableMinorityError,
    ImmutableParticipantError,
    ImmutableSummaryError,
    ImmutableVoteError,
    InvalidAgentRole,
    InvalidStance,
    InvalidVoteChoice,
    MinorityRecord,
    ParticipantRecord,
    SessionEventRecord,
    SessionStateError,
    SummaryRecord,
    UnknownArgumentError,
    UnknownCouncilError,
    UnknownSessionError,
    VoteRecord,
    ArtifactRecord,
    argument_id as _argument_id,
    artifact_id as _artifact_id,
    can_transition,
    consensus_id as _consensus_id,
    consensus_outcome,
    content_hash,
    council_id as _council_id,
    detect_cycle,
    discussion_id as _discussion_id,
    input_digest,
    minority_id as _minority_id,
    participant_id as _participant_id,
    report_id as _report_id,
    session_event_id as _session_event_id,
    session_id as _session_id,
    summary_id as _summary_id,
    tally_votes,
    vote_id as _vote_id,
    winning_stance,
)

_DISCLAIMER = ("Research Council 데이터 — COUNCIL ≠ EXECUTION · CONSENSUS ≠ APPROVAL · RECOMMENDATION ≠ "
               "DEPLOYMENT. 다중 에이전트 연구 협의·권고 전용 — 승인/배포/거래/할당/권한·설정 변경/주문·브로커·"
               "포트폴리오 수정 없음. 합의는 권고일 뿐이다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchCouncilEngine:
    """다중 에이전트 연구 협의체. 불변·append-only·이벤트 소싱·결정적. 실행/승인/배포 권한 없음."""

    # ══════════════ 아티팩트 계보(내부) ══════════════
    def _artifact(self, atype: str, ref: str, parent: str, session: str, now: str,
                *, commit: bool) -> ArtifactRecord:
        aid = _artifact_id(atype, ref)
        rec = ArtifactRecord(artifact_id=aid, artifact_type=atype, ref_id=ref,
                             parent_artifact=parent, session_id=session, created_at=now,
                             input_hash=input_digest(atype, ref), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return ArtifactRecord(**rec)

    # ══════════════ register_council ══════════════
    def register_council(self, name: str, mandate: str = "", now: str = "",
                       *, commit: bool = False) -> CouncilRecord:
        """연구 협의체 등록(불변). **협의 등록만 — 실행 권한 아님.**"""
        cid = _council_id(name)
        existing = ledger.get_council(cid)
        if existing is not None:
            if existing.get("name") != name:
                raise ImmutableCouncilError(f"{cid} 협의체 불변 — 변경 불가")
            return CouncilRecord(**{k: v for k, v in existing.items()
                                    if k in CouncilRecord.__dataclass_fields__})
        rec = CouncilRecord(council_id=cid, name=name, mandate=mandate, created_at=now,
                            input_hash=input_digest(name), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.council_exists(cid):
            head = ledger.councils_head()
            ledger.append_council(_seal(rec, head["record_hash"] if head else GENESIS))
        self._artifact(ART_COUNCIL, cid, "", "", now, commit=commit)
        return CouncilRecord(**rec)

    def _require_council(self, cid: str) -> dict:
        rec = ledger.get_council(cid)
        if rec is None:
            raise UnknownCouncilError(f"미등록 협의체 {cid}")
        return rec

    # ══════════════ create_session (event-sourced) ══════════════
    def _session_event(self, session: str, council: str, topic: str, objective: str, frm: str,
                     to: str, note: str, now: str, *, commit: bool) -> SessionEventRecord:
        seq = len(ledger.session_events(session))
        eid = _session_event_id(session, to, seq)
        rec = SessionEventRecord(
            session_event_id=eid, session_id=session, council_id=council, topic=topic,
            objective=objective, from_state=frm, to_state=to, note=note, occurred_at=now,
            input_hash=input_digest(session, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.session_event_exists(eid):
            head = ledger.sessions_head()
            ledger.append_session_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return SessionEventRecord(**rec)

    def create_session(self, council: str, topic: str, objective: str = "", now: str = "",
                     *, commit: bool = False) -> SessionEventRecord:
        """협의 세션 생성(CREATED). **협의만 — 실행 없음.**"""
        self._require_council(council)
        session = _session_id(council, topic)
        evs = ledger.session_events(session)
        if evs:
            g = evs[0]
            return SessionEventRecord(**{k: v for k, v in g.items()
                                         if k in SessionEventRecord.__dataclass_fields__})
        ev = self._session_event(session, council, topic, objective, GENESIS, S_CREATED,
                               "created", now, commit=commit)
        parent = _artifact_id(ART_COUNCIL, council)
        self._artifact(ART_SESSION, session, parent if ledger.artifact_exists(parent) else "",
                       session, now, commit=commit)
        return ev

    def current_state(self, session: str) -> str | None:
        evs = ledger.session_events(session)
        return evs[-1].get("to_state") if evs else None

    def session_meta(self, session: str) -> dict:
        evs = ledger.session_events(session)
        if not evs:
            raise UnknownSessionError(f"미등록 세션 {session}")
        g = evs[0]
        return {"session_id": session, "council_id": g.get("council_id"), "topic": g.get("topic"),
                "objective": g.get("objective"), "state": evs[-1].get("to_state")}

    def _require_session(self, session: str) -> str:
        st = self.current_state(session)
        if st is None:
            raise UnknownSessionError(f"미등록 세션 {session}")
        return st

    def _transition(self, session: str, to: str, note: str, now: str, *, commit: bool) -> SessionEventRecord:
        frm = self._require_session(session)
        if not can_transition(frm, to):
            raise IllegalSessionTransition(f"{session} {frm}→{to} 불가")
        m = self.session_meta(session)
        return self._session_event(session, m["council_id"], m["topic"], m["objective"], frm, to,
                                 note, now, commit=commit)

    def activate_session(self, session: str, now: str = "", *, commit: bool = False) -> SessionEventRecord:
        return self._transition(session, S_ACTIVE, "activated", now, commit=commit)

    def start_discussion(self, session: str, now: str = "", *, commit: bool = False) -> SessionEventRecord:
        return self._transition(session, S_DISCUSSING, "discussing", now, commit=commit)

    def open_voting(self, session: str, now: str = "", *, commit: bool = False) -> SessionEventRecord:
        return self._transition(session, S_VOTING, "voting", now, commit=commit)

    def reach_consensus(self, session: str, now: str = "", *, commit: bool = False) -> SessionEventRecord:
        return self._transition(session, S_CONSENSUS, "consensus", now, commit=commit)

    def close_session(self, session: str, now: str = "", *, commit: bool = False) -> SessionEventRecord:
        return self._transition(session, S_CLOSED, "closed", now, commit=commit)

    # ══════════════ invite_agent ══════════════
    def invite_agent(self, session: str, agent_name: str, role: str, now: str = "",
                   *, commit: bool = False) -> ParticipantRecord:
        """세션에 연구 에이전트 초대(참가자, 불변). 역할은 8종 협의체 멤버. **참여 등록만.**"""
        self._require_session(session)
        if role not in AGENT_ROLES:
            raise InvalidAgentRole(f"미등록 역할 {role}")
        pid = _participant_id(session, agent_name)
        existing = ledger.get_participant(pid)
        if existing is not None:
            if existing.get("role") != role:
                raise ImmutableParticipantError(f"{pid} 참가자 불변 — 변경 불가")
            return ParticipantRecord(**{k: v for k, v in existing.items()
                                        if k in ParticipantRecord.__dataclass_fields__})
        rec = ParticipantRecord(participant_id=pid, session_id=session, agent_name=agent_name,
                                role=role, invited_at=now, input_hash=input_digest(session, agent_name),
                                previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.participant_exists(pid):
            head = ledger.participants_head()
            ledger.append_participant(_seal(rec, head["record_hash"] if head else GENESIS))
        return ParticipantRecord(**rec)

    def _require_participant(self, session: str, agent: str) -> None:
        if not ledger.participant_exists(_participant_id(session, agent)):
            raise ImmutableParticipantError(f"{agent} 세션 {session} 미참여")

    # ══════════════ submit_discussion / submit_argument ══════════════
    def submit_discussion(self, session: str, participant: str, message: str, now: str = "",
                        *, commit: bool = False) -> DiscussionRecord:
        """토론 발언 기록(불변). **발언·기록만.**"""
        self._require_session(session)
        did = _discussion_id(session, participant, message)
        if ledger.discussion_exists(did):
            for r in ledger.session_discussions(session):
                if r.get("discussion_id") == did:
                    return DiscussionRecord(**{k: v for k, v in r.items()
                                               if k in DiscussionRecord.__dataclass_fields__})
        rec = DiscussionRecord(discussion_id=did, session_id=session, participant=participant,
                               message=message, created_at=now,
                               input_hash=input_digest(session, participant, message),
                               previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.discussion_exists(did):
            head = ledger.discussions_head()
            ledger.append_discussion(_seal(rec, head["record_hash"] if head else GENESIS))
        return DiscussionRecord(**rec)

    def _record_argument(self, session: str, participant: str, claim: str, stance: str,
                       parent: str, is_counter: bool, now: str, *, commit: bool) -> ArgumentRecord:
        if stance not in STANCES:
            raise InvalidStance(f"미등록 입장 {stance}")
        aid = _argument_id(session, participant, claim)
        existing = ledger.get_argument(aid)
        if existing is not None:
            if existing.get("stance") != stance:
                raise ImmutableArgumentError(f"{aid} 논증 불변 — 변경 불가")
            return ArgumentRecord(**{k: v for k, v in existing.items()
                                     if k in ArgumentRecord.__dataclass_fields__})
        rec = ArgumentRecord(argument_id=aid, session_id=session, participant=participant,
                             claim=claim, stance=stance, parent_argument=parent,
                             is_counter=is_counter, created_at=now,
                             input_hash=input_digest(session, participant, claim),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.argument_exists(aid):
            head = ledger.arguments_head()
            ledger.append_argument(_seal(rec, head["record_hash"] if head else GENESIS))
        parent_art = _artifact_id(ART_SESSION, session)
        self._artifact(ART_ARGUMENT, aid, parent_art if ledger.artifact_exists(parent_art) else "",
                       session, now, commit=commit)
        return ArgumentRecord(**rec)

    def submit_argument(self, session: str, participant: str, claim: str, stance: str = STANCE_FOR,
                      now: str = "", *, commit: bool = False) -> ArgumentRecord:
        """연구 논증 제출(불변). **논증·기록만.**"""
        self._require_session(session)
        return self._record_argument(session, participant, claim, stance, "", False, now,
                                    commit=commit)

    def submit_counter_argument(self, session: str, participant: str, parent_argument: str,
                              claim: str, now: str = "", *, commit: bool = False) -> ArgumentRecord:
        """반대 논증 제출(부모 논증의 반대 입장, 불변). **반박·기록만.**"""
        self._require_session(session)
        parent = ledger.get_argument(parent_argument)
        if parent is None:
            raise UnknownArgumentError(f"미등록 부모 논증 {parent_argument}")
        opposite = STANCE_AGAINST if parent.get("stance") == STANCE_FOR else STANCE_FOR
        return self._record_argument(session, participant, claim, opposite, parent_argument, True,
                                    now, commit=commit)

    # ══════════════ record_vote ══════════════
    def record_vote(self, session: str, topic: str, participant: str, choice: str,
                  rationale: str = "", now: str = "", *, commit: bool = False) -> VoteRecord:
        """투표 기록(참가자당 주제별 1표, 불변). **투표·기록만 — 승인 아님.**"""
        self._require_session(session)
        if choice not in VOTE_CHOICES:
            raise InvalidVoteChoice(f"미등록 투표 선택 {choice}")
        vid = _vote_id(session, topic, participant)
        existing = ledger.get_vote(vid)
        if existing is not None:
            if existing.get("choice") != choice:
                raise ImmutableVoteError(f"{vid} 투표 불변 — 변경 불가")
            return VoteRecord(**{k: v for k, v in existing.items()
                                 if k in VoteRecord.__dataclass_fields__})
        rec = VoteRecord(vote_id=vid, session_id=session, topic=topic, participant=participant,
                         choice=choice, rationale=rationale, created_at=now,
                         input_hash=input_digest(session, topic, participant),
                         previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.vote_exists(vid):
            head = ledger.votes_head()
            ledger.append_vote(_seal(rec, head["record_hash"] if head else GENESIS))
        return VoteRecord(**rec)

    # ══════════════ calculate_consensus ══════════════
    def calculate_consensus(self, session: str, topic: str, now: str = "",
                          *, commit: bool = False) -> ConsensusRecord:
        """투표로 합의 결과 계산·기록(결정적). **CONSENSUS ≠ APPROVAL — 권고일 뿐.**"""
        self._require_session(session)
        votes = ledger.topic_votes(session, topic)
        choices = [v.get("choice") for v in votes]
        t = tally_votes(choices)
        outcome = consensus_outcome(choices)
        stance = winning_stance(choices)
        cid = _consensus_id(session, topic)
        existing = ledger.get_consensus(cid)
        if existing is not None:
            if existing.get("outcome") != outcome or existing.get("for_count") != t["FOR"]:
                raise ImmutableConsensusError(f"{cid} 합의 불변 — 변경 불가")
            return ConsensusRecord(**{k: v for k, v in existing.items()
                                      if k in ConsensusRecord.__dataclass_fields__})
        rec = ConsensusRecord(
            consensus_id=cid, session_id=session, topic=topic, outcome=outcome,
            for_count=t["FOR"], against_count=t["AGAINST"], abstain_count=t["ABSTAIN"],
            winning_stance=stance, participant_count=len(votes), created_at=now,
            input_hash=input_digest(session, topic), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.consensus_exists(cid):
            head = ledger.consensus_head()
            ledger.append_consensus(_seal(rec, head["record_hash"] if head else GENESIS))
        parent_art = _artifact_id(ART_SESSION, session)
        self._artifact(ART_CONSENSUS, cid, parent_art if ledger.artifact_exists(parent_art) else "",
                       session, now, commit=commit)
        return ConsensusRecord(**rec)

    # ══════════════ record_minority ══════════════
    def record_minority(self, session: str, consensus: str, participant: str, stance: str,
                      opinion: str, now: str = "", *, commit: bool = False) -> MinorityRecord:
        """소수의견 기록·보존(불변). **소수의견은 결코 삭제되지 않는다.**"""
        self._require_session(session)
        mid = _minority_id(session, consensus, participant)
        existing = None
        for r in ledger.consensus_minority(consensus):
            if r.get("minority_id") == mid:
                existing = r
                break
        if existing is not None:
            if existing.get("opinion") != opinion:
                raise ImmutableMinorityError(f"{mid} 소수의견 불변 — 변경 불가")
            return MinorityRecord(**{k: v for k, v in existing.items()
                                     if k in MinorityRecord.__dataclass_fields__})
        rec = MinorityRecord(minority_id=mid, session_id=session, consensus_id=consensus,
                             participant=participant, stance=stance, opinion=opinion, created_at=now,
                             input_hash=input_digest(session, consensus, participant),
                             previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.minority_exists(mid):
            head = ledger.minority_head()
            ledger.append_minority(_seal(rec, head["record_hash"] if head else GENESIS))
        return MinorityRecord(**rec)

    def preserve_minority(self, session: str, topic: str, now: str = "",
                        *, commit: bool = False) -> list:
        """합의의 소수(패배) 입장 투표자 의견을 자동 보존 기록. **소수의견 보존.**"""
        cons = ledger.get_consensus(_consensus_id(session, topic))
        if cons is None:
            return []
        win = cons.get("winning_stance")
        losing = STANCE_AGAINST if win == STANCE_FOR else (STANCE_FOR if win == STANCE_AGAINST else "")
        if not losing:
            return []
        losing_choice = "AGAINST" if losing == STANCE_AGAINST else "FOR"
        out: list = []
        for v in ledger.topic_votes(session, topic):
            if v.get("choice") == losing_choice:
                out.append(self.record_minority(session, cons.get("consensus_id"),
                                              v.get("participant"), losing,
                                              f"dissent:{v.get('rationale', '')}", now, commit=commit))
        return out

    # ══════════════ generate_summary ══════════════
    def generate_summary(self, session: str, topic: str, recommendation: str = "", now: str = "",
                       *, commit: bool = False) -> SummaryRecord:
        """결정 요약 생성(권고, 불변). **is_decision=False — 협의 요약, 결정 아님.**"""
        self._require_session(session)
        cons = ledger.get_consensus(_consensus_id(session, topic))
        outcome = cons.get("outcome") if cons else "NO_CONSENSUS"
        cons_id = cons.get("consensus_id") if cons else ""
        sid = _summary_id(session, topic)
        existing = ledger.get_summary(sid)
        if existing is not None:
            if existing.get("recommendation") != recommendation:
                raise ImmutableSummaryError(f"{sid} 요약 불변 — 변경 불가")
            return SummaryRecord(**{k: v for k, v in existing.items()
                                    if k in SummaryRecord.__dataclass_fields__})
        rec = SummaryRecord(
            summary_id=sid, session_id=session, topic=topic, outcome=outcome,
            recommendation=recommendation, argument_count=len(ledger.session_arguments(session)),
            vote_count=len(ledger.topic_votes(session, topic)),
            minority_count=len(ledger.consensus_minority(cons_id)) if cons_id else 0,
            is_decision=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(session, topic), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.summary_exists(sid):
            head = ledger.summaries_head()
            ledger.append_summary(_seal(rec, head["record_hash"] if head else GENESIS))
        parent_art = _artifact_id(ART_CONSENSUS, cons_id) if cons_id else ""
        self._artifact(ART_SUMMARY, sid, parent_art if ledger.artifact_exists(parent_art) else "",
                       session, now, commit=commit)
        return SummaryRecord(**rec)

    # ══════════════ generate_report ══════════════
    def generate_report(self, council: str, scope: str = "COUNCIL", now: str = "",
                      *, commit: bool = False) -> CouncilReportRecord:
        """협의체 리포트(세션·합의·결과 분포). **is_binding=False — 권고 리포트, 구속력 없음.**"""
        self._require_council(council)
        sessions = [s for s in ledger.session_ids()
                    if any(ev.get("council_id") == council for ev in ledger.session_events(s))]
        cons = [c for c in ledger.read_consensus() if c.get("session_id") in sessions]
        out_dist: dict = {}
        for c in cons:
            out_dist[c.get("outcome")] = out_dist.get(c.get("outcome"), 0) + 1
        rid = _report_id(council, scope, now)
        rec = CouncilReportRecord(
            report_id=rid, council_id=council, scope=scope, session_count=len(sessions),
            consensus_count=len(cons), outcome_distribution=dict(sorted(out_dist.items())),
            is_binding=False, disclaimer=_DISCLAIMER, created_at=now,
            input_hash=input_digest(council, scope, now), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return CouncilReportRecord(**rec)

    # ══════════════ verify_integrity ══════════════
    def verify_integrity(self) -> dict:
        from jarvis.research_council.verify import verify_chain
        return verify_chain()

    # ══════════════ 조회 편의 ══════════════
    def list_sessions(self, council: str = "") -> list:
        sids = ledger.session_ids()
        if council:
            sids = [s for s in sids
                    if any(ev.get("council_id") == council for ev in ledger.session_events(s))]
        return sorted(sids)

    def participants_of(self, session: str) -> list:
        return sorted(p.get("agent_name") for p in ledger.session_participants(session))

    def arguments_of(self, session: str) -> list:
        return sorted(a.get("argument_id") for a in ledger.session_arguments(session))

    def minority_of(self, consensus: str) -> list:
        return sorted(m.get("minority_id") for m in ledger.consensus_minority(consensus))

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> CouncilSummary:
        return CouncilSummary(
            timestamp=now, council_count=len(ledger.read_councils()),
            session_event_count=len(ledger.read_session_events()),
            participant_count=len(ledger.read_participants()),
            discussion_count=len(ledger.read_discussions()),
            argument_count=len(ledger.read_arguments()), vote_count=len(ledger.read_votes()),
            consensus_count=len(ledger.read_consensus()), minority_count=len(ledger.read_minority()),
            summary_count=len(ledger.read_summaries()), report_count=len(ledger.read_reports()),
            artifact_count=len(ledger.read_artifacts()))
