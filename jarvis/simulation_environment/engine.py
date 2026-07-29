"""Research Simulation Engine (P10.8) — 연구 결과 재현·검증 비실행 시뮬레이션. **분석·기록 전용.**

연구 결과(P10.2~P10.7)를 READ ONLY 로 소비해 시나리오·파라미터·레짐·스트레스 조건에서 시뮬레이션을
재현·비교한다. **order 생성·trade 실행·portfolio 변경·capital allocation·broker 접근·live trading·
strategy deployment·model promotion 없음.** execution/broker/order/portfolio mutation/risk governor/
permission import·호출 없음. 결과는 결정적으로 파생된 평가값(연구 기록)이며 자동 판단·선택·배포를
하지 않는다. score ≠ selection · result ≠ deployment. 상위 레이어 파일은 읽기만. 결정적·append-only.
"""
from __future__ import annotations

from jarvis.simulation_environment import ledger
from jarvis.simulation_environment.models import (
    ARCHIVED,
    ART_CANDIDATE,
    ART_COMPARISON,
    ART_REPORT,
    ART_RESULT,
    ART_RUN,
    ART_SCENARIO,
    COMPLETED,
    CONFIGURED,
    CREATED,
    GENERIC,
    GENESIS,
    RUNNING,
    USED,
    IllegalTransition,
    ImmutableRunError,
    ImmutableScenarioError,
    MarketRegimeScenario,
    ParameterScenario,
    ScenarioEvent,
    SimulationArtifact,
    SimulationComparison,
    SimulationEnvironmentReport,
    SimulationResult,
    SimulationRunEvent,
    UnknownRun,
    UnknownScenario,
    artifact_id as _artifact_id,
    can_transition_run,
    can_transition_scenario,
    compare_symbol,
    comparison_id as _comparison_id,
    content_hash,
    derive_metrics,
    detect_cycle,
    input_digest,
    params_hash as _params_hash,
    parameter_id as _parameter_id,
    regime_id as _regime_id,
    result_id as _result_id,
    run_event_id,
    run_id as _run_id,
    scenario_event_id,
    scenario_id as _scenario_id,
)

_NOTE = "서술적 비교만 — 자동 추천/선택 없음. score ≠ selection · result ≠ deployment. 사람 검토 필요."


def _seal(rec: dict, previous_hash: str) -> dict:
    rec = dict(rec)
    rec["previous_hash"] = previous_hash
    rec["record_hash"] = content_hash(rec)
    return rec


class ResearchSimulationEngine:
    """연구 시뮬레이션 엔진. 불변·append-only·결정적. 실행/거래/배포/자본배분 권한 없음."""

    # ── 아티팩트 계보(내부) ──
    def _record_artifact(self, artifact_type: str, ref_id: str, parent_artifact: str,
                         now: str, *, commit: bool) -> dict:
        aid = _artifact_id(artifact_type, ref_id)
        rec = SimulationArtifact(
            artifact_id=aid, artifact_type=artifact_type, ref_id=ref_id,
            parent_artifact=parent_artifact, created_at=now,
            input_hash=input_digest(artifact_type, ref_id), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.artifact_exists(aid):
            head = ledger.artifacts_head()
            ledger.append_artifact(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    # ── Scenario Registry (이벤트 소싱, 불변) ──
    def scenario_state(self, scenario_id: str) -> str:
        evs = ledger.scenario_events_for(scenario_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _scenario_meta(self, scenario_id: str) -> dict | None:
        evs = ledger.scenario_events_for(scenario_id)
        return evs[0] if evs else None

    def _emit_scenario_event(self, meta: dict, frm: str, to: str, now: str,
                             *, commit: bool) -> dict:
        if not can_transition_scenario(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(scenario)")
        sid = meta["scenario_id"]
        eid = scenario_event_id(sid, frm, to)
        rec = ScenarioEvent(
            event_id=eid, scenario_id=sid, name=meta["name"],
            scenario_type=meta["scenario_type"], description=meta["description"],
            metadata_hash=meta["metadata_hash"], from_state=frm, to_state=to, status=to,
            created_at=now, input_hash=input_digest(sid, frm, to),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.scenario_event_exists(eid):
            head = ledger.scenarios_head()
            ledger.append_scenario_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def register_scenario(self, name: str, scenario_type: str, description: str = "",
                          metadata: dict | None = None, now: str = "",
                          *, commit: bool = False) -> ScenarioEvent:
        sid = _scenario_id(name, scenario_type)
        mh = _params_hash(metadata or {})
        existing = ledger.scenario_events_for(sid)
        if existing:
            if existing[0].get("metadata_hash") != mh:
                raise ImmutableScenarioError(f"{sid} 시나리오 불변 — 변경 불가")
            return ScenarioEvent(**existing[-1])
        meta = {"scenario_id": sid, "name": name, "scenario_type": scenario_type,
                "description": description, "metadata_hash": mh}
        rec = self._emit_scenario_event(meta, "", CREATED, now, commit=commit)
        self._record_artifact(ART_SCENARIO, sid, "", now, commit=commit)
        return ScenarioEvent(**rec)

    def transition_scenario(self, scenario_id: str, to: str, now: str = "", *,
                            commit: bool = False) -> dict:
        meta = self._scenario_meta(scenario_id)
        if meta is None:
            raise UnknownScenario(f"미존재 시나리오 {scenario_id}")
        return self._emit_scenario_event(meta, self.scenario_state(scenario_id), to, now,
                                         commit=commit)

    def configure_scenario(self, scenario_id: str, now: str = "", *,
                           commit: bool = False) -> dict:
        return self.transition_scenario(scenario_id, CONFIGURED, now, commit=commit)

    def _safe_advance_scenario(self, scenario_id: str, to: str, now: str,
                               *, commit: bool) -> None:
        meta = self._scenario_meta(scenario_id)
        if meta is None:
            return
        cur = self.scenario_state(scenario_id)
        if cur != to and can_transition_scenario(cur, to):
            self._emit_scenario_event(meta, cur, to, now, commit=commit)

    # ── Parameter Scenario (불변) ──
    def attach_parameters(self, name: str, category: str, parameters: dict, now: str = "",
                          *, commit: bool = False) -> ParameterScenario:
        pid = _parameter_id(name, category, parameters)
        rec = ParameterScenario(
            parameter_id=pid, name=name, category=category, parameters=dict(parameters or {}),
            created_at=now, input_hash=input_digest(name, category), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.parameter_exists(pid):
            head = ledger.parameters_head()
            ledger.append_parameter(_seal(rec, head["record_hash"] if head else GENESIS))
        return ParameterScenario(**rec)

    # ── Market Regime Scenario (불변) ──
    def define_regime(self, name: str, regime: str, parameters: dict | None = None,
                      now: str = "", *, commit: bool = False) -> MarketRegimeScenario:
        rid = _regime_id(name, regime)
        rec = MarketRegimeScenario(
            regime_id=rid, name=name, regime=regime, parameters=dict(parameters or {}),
            created_at=now, input_hash=input_digest(name, regime), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.regime_exists(rid):
            head = ledger.regimes_head()
            ledger.append_regime(_seal(rec, head["record_hash"] if head else GENESIS))
        return MarketRegimeScenario(**rec)

    # ── Simulation Run (이벤트 소싱, 불변 입력) ──
    def run_state(self, run_id: str) -> str:
        evs = ledger.run_events_for(run_id)
        return evs[-1].get("to_state", "") if evs else ""

    def _run_meta(self, run_id: str) -> dict | None:
        evs = ledger.run_events_for(run_id)
        return evs[0] if evs else None

    def _emit_run_event(self, meta: dict, frm: str, to: str, now: str, *, commit: bool) -> dict:
        if not can_transition_run(frm, to):
            raise IllegalTransition(f"{frm or 'GENESIS'} -> {to} 차단(run)")
        rid = meta["run_id"]
        eid = run_event_id(rid, frm, to)
        rec = SimulationRunEvent(
            event_id=eid, run_id=rid, candidate_reference=meta["candidate_reference"],
            scenario_reference=meta["scenario_reference"], parameter_set=meta["parameter_set"],
            dataset_reference=meta["dataset_reference"], seed=meta["seed"],
            run_hash=meta["run_hash"], from_state=frm, to_state=to, status=to, created_at=now,
            input_hash=input_digest(rid, frm, to), previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.run_event_exists(eid):
            head = ledger.runs_head()
            ledger.append_run_event(_seal(rec, head["record_hash"] if head else GENESIS))
        return rec

    def create_simulation(self, candidate_reference: str, scenario_reference: str,
                          parameter_set: dict | None = None, dataset_reference: str = "",
                          seed: str = "0", now: str = "",
                          *, commit: bool = False) -> SimulationRunEvent:
        """시뮬레이션 런을 생성(CREATED). scenario 는 등록돼 있어야 한다. **실제 실행 아님.**"""
        if self._scenario_meta(scenario_reference) is None:
            raise UnknownScenario(f"미존재 시나리오 {scenario_reference}")
        pset = dict(parameter_set or {})
        ph = _params_hash(pset)
        rid = _run_id(candidate_reference, scenario_reference, ph, dataset_reference, seed)
        rh = input_digest(candidate_reference, scenario_reference, ph, dataset_reference, seed)
        existing = ledger.run_events_for(rid)
        if existing:
            if existing[0].get("run_hash") != rh:
                raise ImmutableRunError(f"{rid} 런 불변 — 입력 변경 불가")
            return SimulationRunEvent(**existing[-1])
        meta = {"run_id": rid, "candidate_reference": candidate_reference,
                "scenario_reference": scenario_reference, "parameter_set": pset,
                "dataset_reference": dataset_reference, "seed": seed, "run_hash": rh}
        rec = self._emit_run_event(meta, "", CREATED, now, commit=commit)
        # 계보: CANDIDATE(root) · SCENARIO -> RUN
        self._record_artifact(ART_CANDIDATE, candidate_reference, "", now, commit=commit)
        self._record_artifact(ART_RUN, rid, _artifact_id(ART_SCENARIO, scenario_reference), now,
                              commit=commit)
        return SimulationRunEvent(**rec)

    def transition_run(self, run_id: str, to: str, now: str = "", *, commit: bool = False) -> dict:
        meta = self._run_meta(run_id)
        if meta is None:
            raise UnknownRun(f"미존재 런 {run_id}")
        return self._emit_run_event(meta, self.run_state(run_id), to, now, commit=commit)

    def _safe_advance_run(self, run_id: str, to: str, now: str, *, commit: bool) -> None:
        meta = self._run_meta(run_id)
        if meta is None:
            return
        cur = self.run_state(run_id)
        if cur != to and can_transition_run(cur, to):
            self._emit_run_event(meta, cur, to, now, commit=commit)

    # ── 결정적 시뮬레이션 결과 기록 ──
    def _emit_result(self, run_id: str, metrics: dict, det_input: str, now: str,
                     *, commit: bool) -> SimulationResult:
        res_id = _result_id(run_id)
        rec = SimulationResult(
            result_id=res_id, run_id=run_id, metrics=dict(metrics),
            deterministic_input=det_input, created_at=now, input_hash=input_digest(run_id),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.result_exists(res_id):
            head = ledger.results_head()
            ledger.append_result(_seal(rec, head["record_hash"] if head else GENESIS))
        self._record_artifact(ART_RESULT, res_id, _artifact_id(ART_RUN, run_id), now,
                              commit=commit)
        # 런 진행 CREATED→RUNNING→COMPLETED, 시나리오 USED.
        meta = self._run_meta(run_id)
        self._safe_advance_run(run_id, RUNNING, now, commit=commit)
        self._safe_advance_run(run_id, COMPLETED, now, commit=commit)
        if meta:
            self._safe_advance_scenario(meta.get("scenario_reference"), CONFIGURED, now,
                                        commit=commit)
            self._safe_advance_scenario(meta.get("scenario_reference"), USED, now, commit=commit)
        return SimulationResult(**rec)

    def run_simulation_record(self, run_id: str, now: str = "", *,
                              commit: bool = False) -> SimulationResult:
        """런 입력에서 결정적으로 결과를 파생·기록. 동일 런 → 동일 결과(재현성). **실제 실행 아님.**"""
        meta = self._run_meta(run_id)
        if meta is None:
            raise UnknownRun(f"미존재 런 {run_id}")
        det_input = f"{run_id}:{meta.get('seed', '0')}"
        metrics = derive_metrics(det_input)
        return self._emit_result(run_id, metrics, det_input, now, commit=commit)

    def record_result(self, run_id: str, metrics: dict, now: str = "",
                      *, commit: bool = False) -> SimulationResult:
        """외부 제공 지표를 결과로 기록(연구 값). run 은 등록돼 있어야 한다."""
        if self._run_meta(run_id) is None:
            raise UnknownRun(f"미존재 런 {run_id}")
        clean = {m: round(float(metrics.get(m, 0.0)), 8) for m in metrics}
        return self._emit_result(run_id, clean, f"explicit:{run_id}", now, commit=commit)

    # ── Comparison (자동 추천 없음) ──
    def compare_results(self, run_a: str, run_b: str, now: str = "",
                        *, commit: bool = False) -> SimulationComparison:
        ra = ledger.result_for_run(run_a)
        rb = ledger.result_for_run(run_b)
        ma = ra.get("metrics", {}) if ra else {}
        mb = rb.get("metrics", {}) if rb else {}

        def _dim(a_val, b_val):
            d = round(float(a_val) - float(b_val), 8)
            return {"a": round(float(a_val), 8), "b": round(float(b_val), 8), "delta": d,
                    "symbol": compare_symbol(d)}

        dimensions = {
            "performance": _dim(ma.get("sharpe", 0.0), mb.get("sharpe", 0.0)),
            "stability": _dim(ma.get("stability_score", 0.0), mb.get("stability_score", 0.0)),
            "risk": _dim(mb.get("volatility", 0.0), ma.get("volatility", 0.0)),  # 낮을수록 좋음
            "sensitivity": _dim(mb.get("turnover", 0.0), ma.get("turnover", 0.0)),
        }
        cid = _comparison_id(run_a, run_b)
        rec = SimulationComparison(
            comparison_id=cid, run_a=run_a, run_b=run_b, dimensions=dimensions, note=_NOTE,
            created_at=now, input_hash=input_digest(*sorted((run_a, run_b))),
            previous_hash=GENESIS).to_dict()
        rec["record_hash"] = content_hash(rec)
        if commit and not ledger.comparison_exists(cid):
            head = ledger.comparisons_head()
            ledger.append_comparison(_seal(rec, head["record_hash"] if head else GENESIS))
        anchor = ra or rb
        parent = _artifact_id(ART_RESULT, anchor.get("result_id")) if anchor else ""
        self._record_artifact(ART_COMPARISON, cid, parent, now, commit=commit)
        return SimulationComparison(**rec)

    # ── Stress: 파라미터 민감도 스윕(여러 런+결과 결정적 생성) ──
    def parameter_sweep(self, candidate_reference: str, scenario_reference: str,
                        param_name: str, values: list, category: str = GENERIC,
                        dataset_reference: str = "", now: str = "",
                        *, commit: bool = False) -> list:
        """한 파라미터를 여러 값으로 스윕해 런·결과를 생성(민감도 분석). 결정적·기록만."""
        out: list = []
        for v in values:
            pset = {param_name: v}
            run = self.create_simulation(candidate_reference, scenario_reference, pset,
                                         dataset_reference, seed=str(v), now=now, commit=commit)
            res = self.run_simulation_record(run.run_id, now, commit=commit)
            out.append({"value": v, "run_id": run.run_id, "metrics": res.metrics})
        return out

    # ── 상위 레이어 READ ONLY ingest(후보 참조 수집) ──
    def list_source_candidates(self, research_type: str, limit: int = 0) -> list:
        """상위 레이어 원장을 읽기 전용으로 스캔해 후보 참조 문자열 목록 반환. 등록 없음·무변경."""
        spec = ledger.SOURCE_LEDGERS.get(research_type)
        if not spec:
            return []
        layer, filename, id_field = spec
        out: list = []
        for row in ledger.read_source(filename):
            ref = row.get(id_field)
            if not ref:
                continue
            out.append(f"{layer}:{ref}")
            if limit and len(out) >= limit:
                break
        return out

    # ── Report(요약 — 아티팩트 기록) ──
    def generate_report(self, now: str = "", *, commit: bool = False) -> SimulationEnvironmentReport:
        scenarios = ledger.distinct_scenarios()
        sstate: dict = {}
        stype: dict = {}
        for s in scenarios:
            st = self.scenario_state(s.get("scenario_id"))
            sstate[st] = sstate.get(st, 0) + 1
            stype[s.get("scenario_type")] = stype.get(s.get("scenario_type"), 0) + 1
        runs = ledger.distinct_runs()
        rstate: dict = {}
        for r in runs:
            st = self.run_state(r.get("run_id"))
            rstate[st] = rstate.get(st, 0) + 1
        comps = ledger.read_comparisons()
        if commit and comps:
            self._record_artifact(ART_REPORT, f"report@{now}",
                                  _artifact_id(ART_COMPARISON, comps[0].get("comparison_id")),
                                  now, commit=commit)
        return SimulationEnvironmentReport(
            timestamp=now, scenario_count=len(scenarios),
            scenario_state_distribution=dict(sorted(sstate.items())),
            scenario_type_distribution=dict(sorted(stype.items())),
            run_count=len(runs), run_state_distribution=dict(sorted(rstate.items())),
            result_count=len(ledger.read_results()), regime_count=len(ledger.read_regimes()),
            parameter_count=len(ledger.read_parameters()), comparison_count=len(comps))
