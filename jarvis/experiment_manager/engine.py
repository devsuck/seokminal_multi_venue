"""Experiment Manager Engine (P11.4) — AI 보조 실험 생성. **제안 전용.**

실험 제안·계획·연구 요청·결과 수집을 생성한다. 생애주기 PROPOSED→REVIEWED→APPROVED_FOR_RESEARCH→COMPLETED.
**라이브 전략 실행 없음. 실행·배포 없음.** APPROVED_FOR_RESEARCH 는 거래 승인이 아니다(연구 승인일 뿐).
execution/broker/order/portfolio execution/capital allocation/live trading/permission/risk controller import·
호출 없음. PROPOSAL ≠ EXECUTION · APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL · RESULT ≠ DEPLOYMENT. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.experiment_manager import ledger
from jarvis.experiment_manager.models import (
    EXP_APPROVED_FOR_RESEARCH,
    EXP_COMPLETED,
    EXP_PROPOSED,
    EXP_REVIEWED,
    GENESIS,
    OUTCOME_PENDING,
    OUTCOMES,
    PLANNABLE_STATES,
    RESEARCH_STATES,
    ExperimentEventRecord,
    ExperimentPlanRecord,
    ExperimentReportRecord,
    ExperimentResultRecord,
    ExperimentStateError,
    ExperimentSummary,
    IllegalExperimentTransition,
    ImmutablePlanError,
    ImmutableRequestError,
    ImmutableResultError,
    InvalidOutcome,
    ResearchRequestRecord,
    UnknownExperimentError,
    can_transition,
    content_hash,
    event_id as _event_id,
    experiment_id as _experiment_id,
    input_digest,
    plan_id as _plan_id,
    report_id as _report_id,
    request_id as _request_id,
    result_id as _result_id,
)

_DISCLAIMER = ("Experiment Manager 데이터 — PROPOSAL ≠ EXECUTION · APPROVED_FOR_RESEARCH ≠ TRADING_APPROVAL · "
               "RESULT ≠ DEPLOYMENT. 실험 제안 전용 — 라이브 전략 실행/배포 없음. 연구 승인은 거래 승인이 아니다.")


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ExperimentManagerEngine:
    """자율 실험 매니저. 불변·append-only·결정적. 실행/배포/거래 승인 권한 없음."""

    # ══════════════ 실험 생애주기(이벤트 소싱) ══════════════
    def _event(self, exp: str, title: str, hypothesis: str, proposer: str, objective: str,
             frm: str, to: str, note: str, now: str, *, commit: bool) -> ExperimentEventRecord:
        eid = _event_id(exp, to)
        rec = ExperimentEventRecord(
            event_id=eid, experiment_id=exp, title=title, hypothesis=hypothesis, proposer=proposer,
            objective=objective, from_state=frm, to_state=to, note=note, occurred_at=now,
            input_hash=input_digest(exp, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.event_exists(eid):
            head = ledger.experiments_head()
            ledger.append_experiment_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExperimentEventRecord(**rec)

    def propose_experiment(self, title: str, hypothesis: str, proposer: str, objective: str = "",
                         now: str = "", *, commit: bool = False) -> ExperimentEventRecord:
        """실험 제안(PROPOSED). **제안만 — 실행/거래 승인 아님.**"""
        exp = _experiment_id(title, proposer, hypothesis)
        evs = ledger.experiment_events(exp)
        if evs:
            first = evs[0]
            return ExperimentEventRecord(**{k: v for k, v in first.items()
                                            if k in ExperimentEventRecord.__dataclass_fields__})
        return self._event(exp, title, hypothesis, proposer, objective, GENESIS, EXP_PROPOSED,
                           "proposed", now, commit=commit)

    def current_state(self, exp: str) -> str | None:
        evs = ledger.experiment_events(exp)
        return evs[-1].get("to_state") if evs else None

    def experiment_meta(self, exp: str) -> dict:
        evs = ledger.experiment_events(exp)
        if not evs:
            raise UnknownExperimentError(f"미등록 실험 {exp}")
        g = evs[0]
        return {"experiment_id": exp, "title": g.get("title"), "hypothesis": g.get("hypothesis"),
                "proposer": g.get("proposer"), "objective": g.get("objective"),
                "state": evs[-1].get("to_state")}

    def _require(self, exp: str) -> str:
        st = self.current_state(exp)
        if st is None:
            raise UnknownExperimentError(f"미등록 실험 {exp}")
        return st

    def _transition(self, exp: str, to: str, note: str, now: str, *, commit: bool) -> ExperimentEventRecord:
        frm = self._require(exp)
        if not can_transition(frm, to):
            raise IllegalExperimentTransition(f"{exp} {frm}→{to} 불가")
        m = self.experiment_meta(exp)
        return self._event(exp, m["title"], m["hypothesis"], m["proposer"], m["objective"],
                          frm, to, note, now, commit=commit)

    def review_experiment(self, exp: str, note: str = "", now: str = "",
                        *, commit: bool = False) -> ExperimentEventRecord:
        """PROPOSED→REVIEWED. **검토만.**"""
        return self._transition(exp, EXP_REVIEWED, note or "reviewed", now, commit=commit)

    def approve_for_research(self, exp: str, note: str = "", now: str = "",
                           *, commit: bool = False) -> ExperimentEventRecord:
        """REVIEWED→APPROVED_FOR_RESEARCH. **연구 승인일 뿐 — 거래 승인 아님.**"""
        return self._transition(exp, EXP_APPROVED_FOR_RESEARCH, note or "approved_for_research(NOT trading)",
                              now, commit=commit)

    def complete_experiment(self, exp: str, note: str = "", now: str = "",
                          *, commit: bool = False) -> ExperimentEventRecord:
        """APPROVED_FOR_RESEARCH→COMPLETED. **완료 기록만.**"""
        return self._transition(exp, EXP_COMPLETED, note or "completed", now, commit=commit)

    # ══════════════ generate_experiment_plan ══════════════
    def generate_experiment_plan(self, exp: str, method: str, variables=None, dataset: str = "",
                               success_criteria=None, horizon: str = "", now: str = "",
                               *, commit: bool = False) -> ExperimentPlanRecord:
        """실험 계획(설계) 생성(불변). 제안/검토 단계에서만. **설계·제안 — 실행 아님.**"""
        st = self._require(exp)
        if st not in PLANNABLE_STATES:
            raise ExperimentStateError(f"{exp} 상태({st})에서 계획 생성 불가 — 제안/검토 단계만")
        pid = _plan_id(exp, method)
        existing = ledger.get_plan(pid)
        var = list(variables or [])
        crit = list(success_criteria or [])
        if existing is not None:
            if list(existing.get("variables", [])) != var or existing.get("dataset") != dataset:
                raise ImmutablePlanError(f"{pid} 계획 불변 — 변경 불가")
            return ExperimentPlanRecord(**{k: v for k, v in existing.items()
                                           if k in ExperimentPlanRecord.__dataclass_fields__})
        rec = ExperimentPlanRecord(
            plan_id=pid, experiment_id=exp, method=method, variables=var, dataset=dataset,
            success_criteria=crit, horizon=horizon, created_at=now,
            input_hash=input_digest(exp, method), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.plan_exists(pid):
            head = ledger.plans_head()
            ledger.append_plan(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExperimentPlanRecord(**rec)

    # ══════════════ create_research_request ══════════════
    def create_research_request(self, exp: str, plan: str = "", scope: str = "RESEARCH",
                              justification: str = "", now: str = "",
                              *, commit: bool = False) -> ResearchRequestRecord:
        """연구 요청 생성(연구 승인 이후). **research_only=True·trading_approval=False — 절대 거래 승인 아님.**"""
        st = self._require(exp)
        if st not in RESEARCH_STATES:
            raise ExperimentStateError(f"{exp} 상태({st}) — 연구 승인 후에만 연구 요청 가능")
        rid = _request_id(exp, scope)
        existing = ledger.get_request(rid)
        if existing is not None:
            return ResearchRequestRecord(**{k: v for k, v in existing.items()
                                            if k in ResearchRequestRecord.__dataclass_fields__})
        rec = ResearchRequestRecord(
            request_id=rid, experiment_id=exp, plan_id=plan, scope=scope,
            justification=justification, research_only=True, trading_approval=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(exp, scope),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.request_exists(rid):
            head = ledger.requests_head()
            ledger.append_request(_seal(rec, head["record_hash"] if head else GENESIS))
        return ResearchRequestRecord(**rec)

    # ══════════════ collect_results ══════════════
    def collect_results(self, exp: str, metrics=None, findings=None, outcome: str = OUTCOME_PENDING,
                      summary: str = "", now: str = "", *, commit: bool = False) -> ExperimentResultRecord:
        """실험 결과(연구 산출물) 수집(불변). 연구 승인 이후에만. **결과 기록 — 배포 아님.**"""
        st = self._require(exp)
        if st not in RESEARCH_STATES:
            raise ExperimentStateError(f"{exp} 상태({st}) — 연구 승인 후에만 결과 수집 가능")
        if outcome not in OUTCOMES:
            raise InvalidOutcome(f"미등록 결과 결론 {outcome}")
        rid = _result_id(exp, now)
        existing = ledger.get_result(rid)
        finds = list(findings or [])
        m = dict(metrics or {})
        if existing is not None:
            if existing.get("outcome") != outcome or dict(existing.get("metrics", {})) != m:
                raise ImmutableResultError(f"{rid} 결과 불변 — 변경 불가")
            return ExperimentResultRecord(**{k: v for k, v in existing.items()
                                             if k in ExperimentResultRecord.__dataclass_fields__})
        rec = ExperimentResultRecord(
            result_id=rid, experiment_id=exp, metrics=m, findings=finds, outcome=outcome,
            summary=summary, collected_at=now, input_hash=input_digest(exp, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.result_exists(rid):
            head = ledger.results_head()
            ledger.append_result(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExperimentResultRecord(**rec)

    # ══════════════ track_experiment_status ══════════════
    def track_experiment_status(self, exp: str) -> dict:
        """실험 상태·이력 추적(읽기 전용). **조회만.**"""
        m = self.experiment_meta(exp)
        history = [{"to_state": e.get("to_state"), "at": e.get("occurred_at"),
                    "note": e.get("note")} for e in ledger.experiment_events(exp)]
        return {"experiment_id": exp, "title": m["title"], "state": m["state"],
                "history": history, "plan_count": len(ledger.experiment_plans(exp)),
                "request_count": len(ledger.experiment_requests(exp)),
                "result_count": len(ledger.experiment_results(exp)),
                "trading_approval": False}

    # ══════════════ 리포트 ══════════════
    def generate_report(self, exp: str, scope: str = "EXPERIMENT", now: str = "",
                      *, commit: bool = False) -> ExperimentReportRecord:
        """실험 리포트(상태·계획·요청·결과 분포). **관측 리포트 — trading_approval 항상 False.**"""
        st = self._require(exp)
        results = ledger.experiment_results(exp)
        out_dist: dict = {}
        for r in results:
            out_dist[r.get("outcome")] = out_dist.get(r.get("outcome"), 0) + 1
        rid = _report_id(exp, scope, now)
        rec = ExperimentReportRecord(
            report_id=rid, experiment_id=exp, scope=scope, lifecycle_state=st,
            plan_count=len(ledger.experiment_plans(exp)),
            request_count=len(ledger.experiment_requests(exp)), result_count=len(results),
            outcome_distribution=dict(sorted(out_dist.items())), trading_approval=False,
            disclaimer=_DISCLAIMER, created_at=now, input_hash=input_digest(exp, scope, now),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.report_exists(rid):
            head = ledger.reports_head()
            ledger.append_report(_seal(rec, head["record_hash"] if head else GENESIS))
        return ExperimentReportRecord(**rec)

    # ══════════════ 조회 편의 ══════════════
    def list_experiments(self) -> list:
        return ledger.experiment_ids()

    def experiments_in_state(self, state: str) -> list:
        return sorted(e for e in ledger.experiment_ids() if self.current_state(e) == state)

    # ══════════════ Summary ══════════════
    def summary(self, now: str = "") -> ExperimentSummary:
        return ExperimentSummary(
            timestamp=now, experiment_event_count=len(ledger.read_experiment_events()),
            experiment_count=len(ledger.experiment_ids()), plan_count=len(ledger.read_plans()),
            request_count=len(ledger.read_requests()), result_count=len(ledger.read_results()),
            report_count=len(ledger.read_reports()))
