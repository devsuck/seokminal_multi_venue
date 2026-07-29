"""Agent Research Governance Engine (P10.6) — AI 연구 에이전트 관리·감사. **기록·감사 전용.**

에이전트 정체성(불변)·능력(메타데이터)·연구요청·실험제안·행동감사·사람검토·연구예산·계보를 남긴다.
**AI Agent 는 연구 보조자이며 실행 권한이 없다.** execution/broker/order/capital allocation/deployment/
permission mutation/risk threshold/model promotion import·호출 없음. 금지 능력·행동은 거부 또는
BLOCKED 기록만. 자동 승인 금지(사람 검토 필수). Agent VALIDATED ≠ APPROVED FOR TRADING ·
Proposal ACCEPTED ≠ Execution permission. 상위 레이어(P9.8~P10.5) 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.agent_governance import ledger
from jarvis.agent_governance.models import (
    ACCEPTED,
    ACTION_BLOCKED,
    ACTIVE,
    APPROVE,
    APPROVED,
    ART_AGENT,
    ART_PROPOSAL,
    ART_REQUEST,
    BUDGET_BLOCKED,
    BUDGET_LIMIT,
    BUDGET_OK,
    BUDGET_USAGE,
    COMPLETED,
    CREATED,
    DRAFT,
    GENESIS,
    REGISTERED,
    REJECT,
    REJECTED,
    REQUEST_CHANGE,
    REVIEWED,
    REVIEWING,
    RUNNING,
    SUBMITTED,
    AgentAction,
    AgentArtifact,
    AgentEvent,
    BudgetRecord,
    Capability,
    ForbiddenCapability,
    HumanApprovalRequired,
    IllegalTransition,
    ImmutableAgentError,
    ImmutableRequestError,
    ProposalEvent,
    ResearchRequestEvent,
    HumanReview,
    UnknownProposal,
    agent_event_id,
    agent_identity_hash,
    artifact_id as _artifact_id,
    budget_key as _budget_key,
    budget_limit_id,
    budget_usage_id,
    can_transition_agent,
    can_transition_proposal,
    can_transition_request,
    capability_id as _capability_id,
    content_hash,
    input_digest,
    is_forbidden_action,
    is_forbidden_capability,
    proposal_event_id,
    proposal_id as _proposal_id,
    request_event_id,
    request_hash,
    request_id as _request_id,
    review_id as _review_id,
    ALLOWED_CAPABILITIES,
    KIND_EXPERIMENT,
)


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class AgentGovernanceEngine:
    """에이전트 거버넌스 엔진. 불변·append-only·결정적. 실행/배포/주문/자본배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         agent_id: str, now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = AgentArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, agent_id=agent_id, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Agent Registry (이벤트 소싱, 정체성 불변) ──
    def agent_state(self, agent_id: str) -> str:
        evs = ledger.agent_events_for(agent_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _agent_meta(self, agent_id: str) -> dict | None:
        evs = ledger.agent_events_for(agent_id)
        return evs[0] if evs else None

    def _emit_agent_event(self, meta: dict, frm: str, to: str, now: str, *, actor: str,
                          commit: bool) -> dict:
        if not can_transition_agent(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(agent)")
        aid = meta["agent_id"]
        eid = agent_event_id(aid, frm, to)
        rec = AgentEvent(
            event_id=eid, agent_id=aid, name=meta["name"], version=meta["version"],
            provider=meta["provider"], capabilities=meta["capabilities"],
            identity_hash=meta["identity_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, actor=actor, input_hash=input_digest(aid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.agent_event_exists(eid):
            head = ledger.agents_head()
            ledger.append_agent_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_agent(self, agent_id: str, name: str, version: str, provider: str,
                       capabilities: list | None = None, now: str = "",
                       *, commit: bool = False) -> AgentEvent:
        """AI 연구 에이전트를 불변 등록(REGISTERED). **실행 권한 부여 아님.**"""
        caps = sorted(capabilities or [])
        ih = agent_identity_hash(agent_id, name, version, provider, caps)
        existing = ledger.agent_events_for(agent_id)
        if existing:
            if existing[0].get("identity_hash") != ih:
                raise ImmutableAgentError(f"{agent_id} 에이전트 정체성 불변 — 변경 불가")
            return AgentEvent(**existing[-1])
        meta = {"agent_id": agent_id, "name": name, "version": version, "provider": provider,
                "capabilities": caps, "identity_hash": ih}
        rec = self._emit_agent_event(meta, "", REGISTERED, now, actor="system", commit=commit)
        self._record_artifact(ART_AGENT, agent_id, "", agent_id, now, commit=commit)
        return AgentEvent(**rec)

    def transition_agent(self, agent_id: str, to: str, now: str = "", *,
                         actor: str = "operator", commit: bool = False) -> dict:
        meta = self._agent_meta(agent_id)
        if meta is None:
            raise IllegalTransition(f"미존재 에이전트 {agent_id}")
        return self._emit_agent_event(meta, self.agent_state(agent_id), to, now, actor=actor,
                                      commit=commit)

    def activate_agent(self, agent_id: str, now: str = "", *, actor: str = "operator",
                       commit: bool = False) -> dict:
        return self.transition_agent(agent_id, ACTIVE, now, actor=actor, commit=commit)

    # ── Capability Registry (메타데이터 — 실제 권한 아님) ──
    def grant_capability(self, agent_id: str, capability: str, now: str = "",
                         *, commit: bool = False) -> Capability:
        """연구 능력 메타데이터 등록. 금지 능력(EXECUTE_TRADE 등)은 거부. **권한 부여 아님.**"""
        if is_forbidden_capability(capability):
            raise ForbiddenCapability(f"{capability} 금지 능력 — 부여 불가(실행 권한 없음)")
        if capability not in ALLOWED_CAPABILITIES:
            raise ForbiddenCapability(f"{capability} 미허용 능력 — 거부")
        cid = _capability_id(agent_id, capability)
        rec = Capability(
            capability_id=cid, agent_id=agent_id, capability=capability, allowed=True,
            created_at=now, input_hash=input_digest(agent_id, capability),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.capability_exists(cid):
            head = ledger.capabilities_head()
            ledger.append_capability(_seal(rec, head["record_hash"] if head else GENESIS))
        return Capability(**rec)

    def agent_capabilities(self, agent_id: str) -> list:
        return sorted(c.get("capability") for c in ledger.read_capabilities()
                      if c.get("agent_id") == agent_id)

    # ── Research Request (이벤트 소싱) ──
    def request_state(self, request_id: str) -> str:
        evs = ledger.request_events_for(request_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _request_meta(self, request_id: str) -> dict | None:
        evs = ledger.request_events_for(request_id)
        return evs[0] if evs else None

    def _emit_request_event(self, meta: dict, frm: str, to: str, now: str, *, actor: str,
                            commit: bool) -> dict:
        if not can_transition_request(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(request)")
        rid = meta["request_id"]
        eid = request_event_id(rid, frm, to)
        rec = ResearchRequestEvent(
            event_id=eid, request_id=rid, agent_id=meta["agent_id"],
            objective=meta["objective"], input_sources=meta["input_sources"],
            request_hash=meta["request_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, actor=actor, input_hash=input_digest(rid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.request_event_exists(eid):
            head = ledger.requests_head()
            ledger.append_request_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_request(self, agent_id: str, objective: str, input_sources: list | None = None,
                       now: str = "", *, commit: bool = False) -> ResearchRequestEvent:
        rid = _request_id(agent_id, objective)
        srcs = list(input_sources or [])
        rh = request_hash(agent_id, objective, srcs)
        existing = ledger.request_events_for(rid)
        if existing:
            if existing[0].get("request_hash") != rh:
                raise ImmutableRequestError(f"{rid} 연구요청 불변 — 변경 불가")
            return ResearchRequestEvent(**existing[-1])
        meta = {"request_id": rid, "agent_id": agent_id, "objective": objective,
                "input_sources": srcs, "request_hash": rh}
        rec = self._emit_request_event(meta, "", CREATED, now, actor=agent_id, commit=commit)
        self._record_artifact(ART_REQUEST, rid, _artifact_id(ART_AGENT, agent_id), agent_id,
                              now, commit=commit)
        return ResearchRequestEvent(**rec)

    def transition_request(self, request_id: str, to: str, now: str = "", *,
                           actor: str = "operator", commit: bool = False) -> dict:
        meta = self._request_meta(request_id)
        if meta is None:
            raise IllegalTransition(f"미존재 요청 {request_id}")
        return self._emit_request_event(meta, self.request_state(request_id), to, now,
                                        actor=actor, commit=commit)

    def _safe_advance_request(self, request_id: str, to: str, now: str, *, actor: str,
                              commit: bool) -> None:
        meta = self._request_meta(request_id)
        if meta is None:
            return
        cur = self.request_state(request_id)
        if cur != to and can_transition_request(cur, to):
            self._emit_request_event(meta, cur, to, now, actor=actor, commit=commit)

    # ── Experiment Proposal (이벤트 소싱) ──
    def proposal_state(self, proposal_id: str) -> str:
        evs = ledger.proposal_events_for(proposal_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _proposal_meta(self, proposal_id: str) -> dict | None:
        evs = ledger.proposal_events_for(proposal_id)
        return evs[0] if evs else None

    def _emit_proposal_event(self, meta: dict, frm: str, to: str, now: str, *, actor: str,
                             commit: bool) -> dict:
        if not can_transition_proposal(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(proposal)")
        pid = meta["proposal_id"]
        eid = proposal_event_id(pid, frm, to)
        rec = ProposalEvent(
            event_id=eid, proposal_id=pid, request_id=meta["request_id"],
            hypothesis=meta["hypothesis"], methodology=meta["methodology"],
            expected_output=meta["expected_output"], risk_notes=meta["risk_notes"],
            from_state=frm, to_state=to, status=to, created_at=now, actor=actor,
            input_hash=input_digest(pid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.proposal_event_exists(eid):
            head = ledger.proposals_head()
            ledger.append_proposal_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_proposal(self, request_id: str, hypothesis: str, methodology: str = "",
                        expected_output: str = "", risk_notes: str = "", now: str = "",
                        *, commit: bool = False) -> ProposalEvent:
        pid = _proposal_id(request_id, hypothesis)
        agent_id = ""
        rmeta = self._request_meta(request_id)
        if rmeta:
            agent_id = rmeta.get("agent_id", "")
        existing = ledger.proposal_events_for(pid)
        if existing:
            return ProposalEvent(**existing[-1])
        meta = {"proposal_id": pid, "request_id": request_id, "hypothesis": hypothesis,
                "methodology": methodology, "expected_output": expected_output,
                "risk_notes": risk_notes}
        rec = self._emit_proposal_event(meta, "", DRAFT, now, actor=agent_id or "agent",
                                        commit=commit)
        self._record_artifact(ART_PROPOSAL, pid, _artifact_id(ART_REQUEST, request_id),
                              agent_id, now, commit=commit)
        return ProposalEvent(**rec)

    def submit_proposal(self, proposal_id: str, now: str = "", *, commit: bool = False) -> dict:
        meta = self._proposal_meta(proposal_id)
        if meta is None:
            raise UnknownProposal(f"미존재 제안 {proposal_id}")
        return self._emit_proposal_event(meta, self.proposal_state(proposal_id), SUBMITTED, now,
                                         actor="agent", commit=commit)

    # ── Human Review Workflow (자동 승인 금지) ──
    def record_review(self, proposal_id: str, reviewer: str, decision: str, reason: str = "",
                      now: str = "", *, commit: bool = False) -> HumanReview:
        """사람 검토 기록 후 제안 상태를 이동. reviewer 필수 · 자동 승인 없음."""
        if not reviewer or not str(reviewer).strip():
            raise HumanApprovalRequired("reviewer(사람) 없이 검토 불가 — 자동 승인 금지")
        meta = self._proposal_meta(proposal_id)
        if meta is None:
            raise UnknownProposal(f"미존재 제안 {proposal_id}")
        rid = _review_id(proposal_id, reviewer, decision)
        rec = HumanReview(
            review_id=rid, proposal_id=proposal_id, reviewer=reviewer, decision=decision,
            reason=reason, created_at=now, input_hash=input_digest(proposal_id, reviewer, decision),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.review_exists(rid):
            head = ledger.reviews_head()
            ledger.append_review(_seal(rec, head["record_hash"] if head else GENESIS))
        # SUBMITTED -> REVIEWED (검토 개시), 이후 결정 반영. DRAFT 등 미제출은 상태 이동 없음.
        cur = self.proposal_state(proposal_id)
        at_reviewed = False
        if cur == SUBMITTED:
            self._emit_proposal_event(meta, SUBMITTED, REVIEWED, now, actor=reviewer,
                                      commit=commit)
            at_reviewed = True
        elif cur == REVIEWED:
            at_reviewed = True
        if at_reviewed:
            if decision == APPROVE and can_transition_proposal(REVIEWED, ACCEPTED):
                self._emit_proposal_event(meta, REVIEWED, ACCEPTED, now, actor=reviewer,
                                          commit=commit)
            elif decision == REJECT and can_transition_proposal(REVIEWED, REJECTED):
                self._emit_proposal_event(meta, REVIEWED, REJECTED, now, actor=reviewer,
                                          commit=commit)
            # REQUEST_CHANGE 는 REVIEWED 에 머무름(추가 검토 필요) — 상태 이동 없음.
        return HumanReview(**rec)

    def accept_proposal(self, *a, **k):
        raise HumanApprovalRequired("제안 수락은 record_review(decision=APPROVE)로만 — 자동 수락 금지")

    # ── Agent Action Audit (금지 행동은 기록만·실행 불가) ──
    def record_action(self, agent_id: str, action_type: str, target: str = "",
                      result: str = "logged", now: str = "", *, commit: bool = False) -> AgentAction:
        """모든 에이전트 행동 기록. 금지 행동은 BLOCKED 로만 남고 절대 실행되지 않는다."""
        forbidden = is_forbidden_action(action_type)
        eff_result = ACTION_BLOCKED if forbidden else result
        aid = _action_id_helper(agent_id, action_type, target, now)
        rec = AgentAction(
            action_id=aid, agent_id=agent_id, action_type=action_type, target=target,
            result=eff_result, is_forbidden=forbidden, timestamp=now,
            input_hash=input_digest(agent_id, action_type, target, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.action_exists(aid):
            head = ledger.actions_head()
            ledger.append_action(_seal(rec, head["record_hash"] if head else GENESIS))
        return AgentAction(**rec)

    # ── Research Budget Tracking (연구 메타데이터 — 실제 실행 제한 아님) ──
    def set_budget(self, agent_id: str, period: str, max_experiments: int, max_queries: int,
                   now: str = "", *, commit: bool = False) -> BudgetRecord:
        bkey = _budget_key(agent_id, period)
        eid = budget_limit_id(agent_id, period)
        rec = BudgetRecord(
            event_id=eid, budget_key=bkey, agent_id=agent_id, period=period,
            record_type=BUDGET_LIMIT, max_experiments=int(max_experiments),
            max_queries=int(max_queries), kind="", amount=0, status=BUDGET_OK, created_at=now,
            input_hash=input_digest(agent_id, period), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.budget_event_exists(eid):
            head = ledger.budgets_head()
            ledger.append_budget(_seal(rec, head["record_hash"] if head else GENESIS))
        return BudgetRecord(**rec)

    def _limit_for(self, bkey: str) -> dict | None:
        for r in ledger.budget_records_for(bkey):
            if r.get("record_type") == BUDGET_LIMIT:
                return r
        return None

    def budget_status(self, agent_id: str, period: str) -> dict:
        bkey = _budget_key(agent_id, period)
        limit = self._limit_for(bkey)
        used_exp = used_qry = 0
        for r in ledger.budget_records_for(bkey):
            if r.get("record_type") == BUDGET_USAGE and r.get("status") == BUDGET_OK:
                if r.get("kind") == KIND_EXPERIMENT:
                    used_exp += int(r.get("amount", 0))
                else:
                    used_qry += int(r.get("amount", 0))
        return {"budget_key": bkey,
                "max_experiments": int(limit.get("max_experiments", 0)) if limit else 0,
                "max_queries": int(limit.get("max_queries", 0)) if limit else 0,
                "used_experiments": used_exp, "used_queries": used_qry,
                "has_limit": limit is not None}

    def consume_budget(self, agent_id: str, period: str, kind: str, now: str = "",
                       *, commit: bool = False) -> BudgetRecord:
        """연구 자원 1건 소비 기록. 한도 초과 시 BLOCKED 로 기록(실제 실행 차단 아님·메타데이터)."""
        bkey = _budget_key(agent_id, period)
        status = self.budget_status(agent_id, period)
        used = status["used_experiments"] if kind == KIND_EXPERIMENT else status["used_queries"]
        cap = status["max_experiments"] if kind == KIND_EXPERIMENT else status["max_queries"]
        seq = len([r for r in ledger.budget_records_for(bkey)
                   if r.get("record_type") == BUDGET_USAGE and r.get("kind") == kind])
        blocked = status["has_limit"] and used + 1 > cap
        eid = budget_usage_id(bkey, kind, seq)
        rec = BudgetRecord(
            event_id=eid, budget_key=bkey, agent_id=agent_id, period=period,
            record_type=BUDGET_USAGE, max_experiments=0, max_queries=0, kind=kind,
            amount=0 if blocked else 1, status=BUDGET_BLOCKED if blocked else BUDGET_OK,
            created_at=now, input_hash=input_digest(bkey, kind, seq),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.budget_event_exists(eid):
            head = ledger.budgets_head()
            ledger.append_budget(_seal(rec, head["record_hash"] if head else GENESIS))
        return BudgetRecord(**rec)

    # ── Agent Lineage (P10.5 Knowledge Graph 연결 가능) ──
    def link_experiment(self, proposal_id: str, experiment_ref: str, now: str = "",
                        *, commit: bool = False) -> dict:
        """제안 → 실험(연구) 계보 엣지(아티팩트). experiment_ref 는 상위 레이어/그래프 참조 문자열."""
        agent_id = ""
        pmeta = self._proposal_meta(proposal_id)
        if pmeta:
            rmeta = self._request_meta(pmeta.get("request_id", ""))
            agent_id = rmeta.get("agent_id", "") if rmeta else ""
        from jarvis.agent_governance.models import ART_EXPERIMENT
        return self._record_artifact(ART_EXPERIMENT, experiment_ref,
                                     _artifact_id(ART_PROPOSAL, proposal_id), agent_id, now,
                                     commit=commit)

    def link_validation(self, experiment_ref: str, validation_ref: str, now: str = "",
                        *, commit: bool = False) -> dict:
        from jarvis.agent_governance.models import ART_EXPERIMENT, ART_VALIDATION
        return self._record_artifact(ART_VALIDATION, validation_ref,
                                     _artifact_id(ART_EXPERIMENT, experiment_ref), "", now,
                                     commit=commit)

    # ── Report ──
    def generate_report(self, now: str = "") -> "AgentGovernanceReport":
        from jarvis.agent_governance.models import AgentGovernanceReport
        agents = ledger.distinct_agents()
        astate: dict = {}
        provider: dict = {}
        for a in agents:
            st = self.agent_state(a.get("agent_id"))
            astate[st] = astate.get(st, 0) + 1
            provider[a.get("provider")] = provider.get(a.get("provider"), 0) + 1

        requests = ledger.distinct_requests()
        rstate: dict = {}
        for r in requests:
            st = self.request_state(r.get("request_id"))
            rstate[st] = rstate.get(st, 0) + 1

        proposals = ledger.distinct_proposals()
        pstate: dict = {}
        pending = 0
        for p in proposals:
            st = self.proposal_state(p.get("proposal_id"))
            pstate[st] = pstate.get(st, 0) + 1
            if st in (SUBMITTED, REVIEWED):
                pending += 1

        actions = ledger.read_actions()
        blocked_actions = sum(1 for a in actions if a.get("is_forbidden"))

        reviews = ledger.read_reviews()
        rdec: dict = {}
        for rv in reviews:
            rdec[rv.get("decision")] = rdec.get(rv.get("decision"), 0) + 1

        budgets = ledger.read_budgets()
        budget_keys = {b.get("budget_key") for b in budgets
                       if b.get("record_type") == BUDGET_LIMIT}
        blocked_budget = sum(1 for b in budgets if b.get("status") == BUDGET_BLOCKED)

        return AgentGovernanceReport(
            timestamp=now, agent_count=len(agents),
            agent_state_distribution=dict(sorted(astate.items())),
            provider_distribution=dict(sorted(provider.items())),
            request_count=len(requests),
            request_state_distribution=dict(sorted(rstate.items())),
            proposal_count=len(proposals),
            proposal_state_distribution=dict(sorted(pstate.items())),
            action_count=len(actions), blocked_action_count=blocked_actions,
            review_count=len(reviews), review_decision_distribution=dict(sorted(rdec.items())),
            budget_count=len(budget_keys), blocked_budget_count=blocked_budget,
            pending_reviews=pending)


def _action_id_helper(agent_id: str, action_type: str, target: str, timestamp: str) -> str:
    from jarvis.agent_governance.models import action_id
    return action_id(agent_id, action_type, target, timestamp)
