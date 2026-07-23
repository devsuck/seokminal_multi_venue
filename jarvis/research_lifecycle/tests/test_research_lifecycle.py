"""P10.26 Research Lifecycle Intelligence 테스트. **전 모듈 연구 생명주기 추적 전용.**

연구 프로젝트(이벤트 소싱 생명주기 IDEA→HYPOTHESIS→EXPERIMENT→BACKTEST→VALIDATION→DECISION→ARCHIVE, 전이
검증·조기 ARCHIVE)·스테이지 전이 기록·생명주기 이벤트(불변)·병목(범주·불변)·누락 스테이지 탐지·리포트(결정적)·
verify(체인/변조/중복/전이/타임라인/계보)·replay·상위 READ ONLY 보호·CLI·보안(금지import·execute/deploy/
approve/trade 없음·상위 원장 무변경·삭제 API 없음·불변·append-only).

패키지 내부 tests/ — 상위 conftest(전체 app 의존) 미상속 → 단독 실행 가능.
"""
from __future__ import annotations

import json
import os

import pytest

from jarvis.research_lifecycle import ledger
from jarvis.research_lifecycle import models as M
from jarvis.research_lifecycle.engine import ResearchLifecycleEngine
from jarvis.research_lifecycle.models import (
    ARCHIVE,
    BACKTEST,
    DECISION,
    EXPERIMENT,
    HYPOTHESIS,
    IDEA,
    VALIDATION,
    IllegalTransition,
    ImmutableEventError,
    InvalidBottleneckCategory,
    InvalidEventType,
    InvalidStage,
    UnknownProject,
)

T0 = "2026-07-23T00:00:00Z"
T1 = "2026-07-23T00:01:00Z"
T2 = "2026-07-23T00:02:00Z"


def _iso(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    monkeypatch.setattr("jarvis.research_lifecycle.ledger.state_path", sp)
    return sp


def _eng():
    return ResearchLifecycleEngine()


def _proj(eng, name="momentum_v1", layer="strategy_governance", ref="rg:ST1", commit=True):
    return eng.register_project(name, layer, ref, T0, commit=commit)


def _full_lifecycle(eng, name="full_proj"):
    """IDEA→...→DECISION→ARCHIVE 완주."""
    p = eng.register_project(name, "strategy_governance", "rg:X", T0, commit=True)
    for st in (HYPOTHESIS, EXPERIMENT, BACKTEST, VALIDATION, DECISION, ARCHIVE):
        eng.advance_stage(p.project_id, st, "", T1, commit=True)
    return p


# ── Project registry ──
def test_project_register(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    assert p.project_id.startswith("RLP:")
    assert p.to_stage == IDEA


def test_project_starts_at_idea(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    assert eng.project_stage(p.project_id) == IDEA


def test_project_not_committed(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    _proj(_eng(), commit=False)
    assert ledger.read_project_events() == []


def test_project_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    assert p.project_id == M.project_id("momentum_v1")


def test_project_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = _proj(eng)
    b = _proj(eng)
    assert a.project_id == b.project_id
    assert len(ledger.distinct_projects()) == 1


def test_project_records_initial_transition(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    assert len(ledger.transitions_for(p.project_id)) == 1  # ""->IDEA


def test_project_artifact_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    assert ledger.artifact_exists(M.artifact_id(M.ART_PROJECT, p.project_id))


def test_project_layer_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    pa = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == p.project_id and a["artifact_type"] == M.ART_PROJECT)
    assert pa["parent_artifact"] == M.artifact_id(M.ART_LAYER, "strategy_governance")


# ── Stage transitions ──
def test_advance_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    res = eng.advance_stage(p.project_id, HYPOTHESIS, "hyp formed", T1, commit=True)
    assert res["from_stage"] == IDEA
    assert res["to_stage"] == HYPOTHESIS
    assert eng.project_stage(p.project_id) == HYPOTHESIS


def test_full_linear_lifecycle(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _full_lifecycle(eng)
    assert eng.project_stage(p.project_id) == ARCHIVE
    assert eng.entered_stages(p.project_id) == list(M.STAGES)


def test_advance_invalid_skip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    with pytest.raises(IllegalTransition):
        eng.advance_stage(p.project_id, EXPERIMENT, "", T1, commit=True)  # skips HYPOTHESIS


def test_advance_early_archive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, ARCHIVE, "abandoned", T1, commit=True)  # IDEA->ARCHIVE ok
    assert eng.project_stage(p.project_id) == ARCHIVE


def test_advance_invalid_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    with pytest.raises(InvalidStage):
        eng.advance_stage(p.project_id, "PRODUCTION", "", T1, commit=True)


def test_advance_unknown_project(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownProject):
        _eng().advance_stage("RLP:nope", HYPOTHESIS, "", T1, commit=True)


def test_archive_terminal(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, ARCHIVE, "", T1, commit=True)
    with pytest.raises(IllegalTransition):
        eng.advance_stage(p.project_id, HYPOTHESIS, "", T2, commit=True)


def test_transition_recorded(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    trs = ledger.transitions_for(p.project_id)
    assert len(trs) == 2  # ""->IDEA, IDEA->HYPOTHESIS
    assert trs[-1]["transition_id"] == M.transition_id(p.project_id, IDEA, HYPOTHESIS)


def test_can_transition_table():
    assert M.can_transition_stage("", IDEA)
    assert M.can_transition_stage(IDEA, HYPOTHESIS)
    assert M.can_transition_stage(VALIDATION, DECISION)
    assert M.can_transition_stage(EXPERIMENT, ARCHIVE)  # early archive
    assert not M.can_transition_stage(IDEA, EXPERIMENT)
    assert not M.can_transition_stage(ARCHIVE, IDEA)


def test_stage_index():
    assert M.stage_index(IDEA) == 0
    assert M.stage_index(ARCHIVE) == 6
    assert M.stage_index("nope") == -1


# ── Lifecycle events ──
def test_event_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    e = eng.record_event(p.project_id, M.EV_NOTE, "note1", "first idea", T0, commit=True)
    assert e.event_id.startswith("RLV:")
    assert e.stage == IDEA


def test_event_invalid_type(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    with pytest.raises(InvalidEventType):
        eng.record_event(p.project_id, "not_a_type", "r", "", T0, commit=True)


def test_event_all_types(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    for i, et in enumerate(M.EVENT_TYPES):
        e = eng.record_event(p.project_id, et, f"r{i}", "", T0, commit=True)
        assert e.event_type == et
    assert len(ledger.events_for(p.project_id)) == len(M.EVENT_TYPES)


def test_event_immutable(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.record_event(p.project_id, M.EV_NOTE, "n1", "d1", T0, commit=True)
    with pytest.raises(ImmutableEventError):
        eng.record_event(p.project_id, M.EV_NOTE, "n1", "d2", T0, commit=True)


def test_event_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    a = eng.record_event(p.project_id, M.EV_NOTE, "n1", "d", T0, commit=True)
    b = eng.record_event(p.project_id, M.EV_NOTE, "n1", "d", T0, commit=True)
    assert a.event_id == b.event_id
    assert len(ledger.read_events()) == 1


def test_event_stamps_current_stage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    e = eng.record_event(p.project_id, M.EV_NOTE, "n1", "", T1, commit=True)
    assert e.stage == HYPOTHESIS


def test_event_parent_links_project(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    e = eng.record_event(p.project_id, M.EV_NOTE, "n1", "", T0, commit=True)
    ea = next(a for a in ledger.read_artifacts()
              if a["ref_id"] == e.event_id and a["artifact_type"] == M.ART_EVENT)
    assert ea["parent_artifact"] == M.artifact_id(M.ART_PROJECT, p.project_id)


# ── Bottlenecks ──
def test_bottleneck_record(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    b = eng.record_bottleneck(p.project_id, IDEA, M.B_STALLED_STAGE, "HIGH", "stuck", ["e1"], T0,
                              commit=True)
    assert b.bottleneck_id.startswith("RLB:")
    assert b.category == M.B_STALLED_STAGE


def test_bottleneck_invalid_category(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(InvalidBottleneckCategory):
        _eng().record_bottleneck("RLP:x", IDEA, "nope", "LOW", "", [], T0, commit=True)


def test_bottleneck_all_categories(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    for i, cat in enumerate(M.BOTTLENECK_CATEGORIES):
        b = eng.record_bottleneck(f"RLP:{i}", IDEA, cat, "MEDIUM", "", [], T0, commit=True)
        assert b.category == cat
    assert len(ledger.read_bottlenecks()) == len(M.BOTTLENECK_CATEGORIES)


def test_bottleneck_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.record_bottleneck("RLP:x", IDEA, M.B_STALLED_STAGE, "HIGH", "", [], T0, commit=True)
    b = eng.record_bottleneck("RLP:x", IDEA, M.B_STALLED_STAGE, "LOW", "", [], T0, commit=True)
    assert a.bottleneck_id == b.bottleneck_id
    assert len(ledger.read_bottlenecks()) == 1


def test_bottleneck_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    b = _eng().record_bottleneck("RLP:x", BACKTEST, M.B_SLOW_TRANSITION, "LOW", "", [], T0,
                                 commit=True)
    assert b.bottleneck_id == M.bottleneck_id("RLP:x", BACKTEST, M.B_SLOW_TRANSITION)


# ── Missing stage detection ──
def test_missing_stages_full_complete(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _full_lifecycle(eng)
    assert eng.detect_missing_stages(p.project_id) == []


def test_missing_stages_early_archive(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, ARCHIVE, "", T1, commit=True)  # IDEA->ARCHIVE
    missing = eng.detect_missing_stages(p.project_id)
    assert HYPOTHESIS in missing and DECISION in missing
    assert IDEA not in missing  # IDEA was entered
    assert ARCHIVE not in missing  # ARCHIVE excluded from canonical


def test_missing_stages_partial(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    eng.advance_stage(p.project_id, EXPERIMENT, "", T1, commit=True)
    missing = eng.detect_missing_stages(p.project_id)
    assert set(missing) == {BACKTEST, VALIDATION, DECISION}


def test_missing_stages_helper():
    assert M.missing_stages([IDEA, HYPOTHESIS]) == [EXPERIMENT, BACKTEST, VALIDATION, DECISION]
    assert M.missing_stages(list(M.STAGES)) == []


def test_missing_unknown_project(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    with pytest.raises(UnknownProject):
        _eng().detect_missing_stages("RLP:nope")


def test_completion_ratio(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    eng.advance_stage(p.project_id, EXPERIMENT, "", T1, commit=True)
    # entered IDEA, HYPOTHESIS, EXPERIMENT = 3 of 6 core stages
    assert eng.completion(p.project_id) == 0.5


def test_completion_ratio_helper():
    assert M.completion_ratio([IDEA]) == round(1 / 6, 8)
    assert M.completion_ratio([IDEA, HYPOTHESIS, EXPERIMENT, BACKTEST, VALIDATION, DECISION]) == 1.0


def test_stalled_projects(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.register_project("stuck", "L", "r1", T0, commit=True)
    b = eng.register_project("moving", "L", "r2", T0, commit=True)
    eng.advance_stage(b.project_id, HYPOTHESIS, "", T1, commit=True)
    assert eng.stalled_projects((IDEA,)) == [a.project_id]


# ── Report ──
def test_report_basic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert r.report_id.startswith("RLR:")
    assert r.project_count >= 1
    assert r.transition_count >= 1


def test_report_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    a = eng.generate_report("GLOBAL", {}, T2, commit=False)
    b = eng.generate_report("GLOBAL", {}, T2, commit=False)
    assert a.to_dict() == b.to_dict()


def test_report_stage_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert ARCHIVE in r.stage_distribution


def test_report_completion_metrics(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert r.archived_count == 1
    assert r.completed_decision_count == 1
    assert r.average_completion == 1.0


def test_report_missing_stage_summary(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, ARCHIVE, "", T1, commit=True)  # skips many stages
    r = eng.generate_report("GLOBAL", {}, T2, commit=True)
    assert r.missing_stage_summary.get(HYPOTHESIS) == 1


def test_report_bottleneck_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.record_bottleneck(p.project_id, IDEA, M.B_STALLED_STAGE, "HIGH", "", [], T0, commit=True)
    r = eng.generate_report("GLOBAL", {}, T1, commit=True)
    assert M.B_STALLED_STAGE in r.bottleneck_category_distribution


def test_report_has_disclaimer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    assert "LIFECYCLE TRACKING ≠ EXECUTION" in r.disclaimer


def test_report_idempotent(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    eng.generate_report("GLOBAL", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 1


def test_report_no_action_verbs(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    d = r.to_dict()
    d.pop("disclaimer")
    blob = json.dumps(d, ensure_ascii=False).lower()
    for verb in ("execute", "deploy", "approve", "trade", "place_order"):
        assert verb not in blob


# ── Lineage / verify ──
def test_verify_lineage_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    assert eng.verify_lineage()["ok"] is True


def test_trace_lineage(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    e = eng.record_event(p.project_id, M.EV_NOTE, "n1", "", T0, commit=True)
    anc = eng.trace_lineage(M.artifact_id(M.ART_EVENT, e.event_id))
    assert M.artifact_id(M.ART_PROJECT, p.project_id) in anc
    assert M.artifact_id(M.ART_LAYER, "strategy_governance") in anc


def test_verify_chain_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    from jarvis.research_lifecycle.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["n"] >= 1


def test_verify_empty_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.verify import verify_chain
    assert verify_chain()["ok"] is True


def test_verify_detects_tamper(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _proj(eng)
    p = sp("rl_projects.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows[0]["name"] = "TAMPERED"
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_lifecycle.verify import verify_ledger
    assert verify_ledger(ledger.PROJECTS)["ok"] is False


def test_verify_detects_broken_chain(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    pf = sp("rl_transitions.jsonl")
    rows = [json.loads(x) for x in open(pf) if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeef"
    with open(pf, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_lifecycle.verify import verify_ledger
    assert verify_ledger(ledger.TRANSITIONS)["ok"] is False


def test_verify_detects_duplicate(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    _proj(eng)
    p = sp("rl_projects.jsonl")
    rows = [json.loads(x) for x in open(p) if x.strip()]
    rows.append(dict(rows[0]))
    with open(p, "w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    from jarvis.research_lifecycle.verify import verify_ledger
    assert verify_ledger(ledger.PROJECTS)["ok"] is False


def test_verify_timeline_ok(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    from jarvis.research_lifecycle.verify import stage_timeline_validation
    assert stage_timeline_validation()["ok"] is True


def test_verify_detects_invalid_transition(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    from jarvis.research_lifecycle.models import content_hash, project_event_id
    # inject illegal skip event bypassing engine guard
    eid = project_event_id(p.project_id, IDEA, BACKTEST)
    head = ledger.projects_head()
    rec = {"event_id": eid, "project_id": p.project_id, "name": "momentum_v1", "source_layer": "",
           "source_reference": "", "from_stage": IDEA, "to_stage": BACKTEST, "stage": BACKTEST,
           "created_at": T1, "input_hash": "", "record_hash": "",
           "previous_hash": head["record_hash"]}
    rec["record_hash"] = content_hash(rec)
    ledger.append_project_event(rec)
    from jarvis.research_lifecycle.verify import stage_timeline_validation
    res = stage_timeline_validation()
    assert res["ok"] is False
    assert any("invalid_transition" in i for i in res["issues"])


def test_verify_full_chain(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    from jarvis.research_lifecycle.verify import verify_chain
    res = verify_chain()
    assert res["ok"] is True
    assert res["timeline"]["ok"] is True
    assert res["lineage"]["ok"] is True


def test_verify_lineage_cycle_detection(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _proj(eng)
    from jarvis.research_lifecycle.models import content_hash
    h = ledger.artifacts_head()["record_hash"]
    a1 = {"artifact_id": "RLX:c1", "artifact_type": "EVENT", "ref_id": "x1",
          "parent_artifact": "RLX:c2", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": h}
    a1["record_hash"] = content_hash(a1)
    ledger.append_artifact(a1)
    a2 = {"artifact_id": "RLX:c2", "artifact_type": "EVENT", "ref_id": "x2",
          "parent_artifact": "RLX:c1", "created_at": T0, "input_hash": "", "record_hash": "",
          "previous_hash": a1["record_hash"]}
    a2["record_hash"] = content_hash(a2)
    ledger.append_artifact(a2)
    res = eng.verify_lineage()
    assert res["ok"] is False
    assert any("cycle" in i for i in res["issues"])


# ── replay / summary ──
def test_replay_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    from jarvis.research_lifecycle.verify import replay
    assert replay(eng, T0)["deterministic"] is True


def test_summary_counts(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _full_lifecycle(eng)
    eng.record_event(p.project_id, M.EV_NOTE, "n", "", T1, commit=True)
    eng.record_bottleneck(p.project_id, BACKTEST, M.B_SLOW_TRANSITION, "LOW", "", [], T1,
                          commit=True)
    s = eng.summary(T0)
    assert s.project_count >= 1
    assert s.transition_count >= 1
    assert s.event_count >= 1
    assert s.bottleneck_count >= 1


def test_summary_deterministic(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _full_lifecycle(eng)
    assert eng.summary(T0).to_dict() == eng.summary(T0).to_dict()


def test_summary_stage_distribution(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.register_project("p1", "L", "r1", T0, commit=True)
    _full_lifecycle(eng)
    s = eng.summary(T0)
    assert IDEA in s.stage_distribution
    assert ARCHIVE in s.stage_distribution


# ── 상위 READ ONLY ──
def test_list_source_objects_empty(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("strategy_governance") == []


def test_list_source_objects_reads(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("rg_strategies.jsonl"), "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
        f.write(json.dumps({"strategy_id": "ST2"}) + "\n")
    out = _eng().list_source_objects("strategy_governance")
    assert out == ["strategy_governance:ST1", "strategy_governance:ST2"]


def test_source_read_only_no_write(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    src = sp("rg_strategies.jsonl")
    with open(src, "w") as f:
        f.write(json.dumps({"strategy_id": "ST1"}) + "\n")
    before = open(src).read()
    eng = _eng()
    _full_lifecycle(eng)
    eng.list_source_objects("strategy_governance")
    assert open(src).read() == before


def test_unknown_source_layer(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    assert _eng().list_source_objects("nonexistent") == []


def test_source_count(tmp_path, monkeypatch):
    sp = _iso(tmp_path, monkeypatch)
    with open(sp("ai_signals.jsonl"), "w") as f:
        f.write(json.dumps({"signal_id": "S1"}) + "\n")
    assert ledger.source_count("alpha_intelligence") == 1
    assert ledger.source_count("nope") == 0


def test_upstream_layers_p10_2_to_p10_25():
    for layer in ("strategy_governance", "research_risk_intelligence", "self_audit_intelligence",
                  "governance_orchestration", "research_compliance"):
        assert layer in ledger.SOURCE_LEDGERS


# ── CLI ──
def test_cli_project(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    rc = main(["project", "--name", "p1", "--source-layer", "strategy_governance", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["project"]["project_id"].startswith("RLP:")


def test_cli_advance(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    main(["project", "--name", "p1", "--commit"])
    pid = json.loads(capsys.readouterr().out)["project"]["project_id"]
    rc = main(["advance", "--project-ref", pid, "--to-stage", "HYPOTHESIS", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["advance"]["to_stage"] == "HYPOTHESIS"


def test_cli_event(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    main(["project", "--name", "p1", "--commit"])
    pid = json.loads(capsys.readouterr().out)["project"]["project_id"]
    rc = main(["event", "--project-ref", pid, "--event-type", "NOTE", "--reference", "n1",
               "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["event"]["event_id"].startswith("RLV:")


def test_cli_bottleneck(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    rc = main(["bottleneck", "--project-ref", "RLP:x", "--stage", "IDEA", "--category",
               "stalled_stage", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["bottleneck"]["bottleneck_id"].startswith("RLB:")


def test_cli_missing(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    main(["project", "--name", "p1", "--commit"])
    pid = json.loads(capsys.readouterr().out)["project"]["project_id"]
    rc = main(["missing", "--project-ref", pid])
    assert rc == 0
    assert "HYPOTHESIS" in json.loads(capsys.readouterr().out)["missing_stages"]


def test_cli_report(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    rc = main(["report", "--commit"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["report"]["report_id"].startswith("RLR:")


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    main(["project", "--name", "p1", "--commit"])
    capsys.readouterr()
    rc = main(["verify"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["ok"] is True


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    main(["project", "--name", "p1", "--commit"])
    capsys.readouterr()
    rc = main(["replay"])
    assert rc == 0
    assert json.loads(capsys.readouterr().out)["deterministic"] is True


def test_cli_summary(tmp_path, monkeypatch, capsys):
    _iso(tmp_path, monkeypatch)
    from jarvis.research_lifecycle.__main__ import main
    rc = main(["summary"])
    assert rc == 0
    assert "project_count" in json.loads(capsys.readouterr().out)


# ── 보안·불변·READ ONLY 가드 ──
def test_no_forbidden_imports():
    import jarvis.research_lifecycle.engine as eng_mod
    import jarvis.research_lifecycle.models as mdl_mod
    import jarvis.research_lifecycle.ledger as led_mod
    import jarvis.research_lifecycle.verify as ver_mod
    import jarvis.research_lifecycle.__main__ as cli_mod
    src = ""
    for m in (eng_mod, mdl_mod, led_mod, ver_mod, cli_mod):
        with open(m.__file__) as f:
            src += f.read()
    _j = "jarvis."
    forbidden = [_j + "execution", _j + "broker", _j + "order",
                 _j + "portfolio_execution", _j + "capital_allocation", _j + "live_trading",
                 _j + "permission", _j + "risk_controller",
                 "place_order(", "submit_order(", "execute_trade(", "deploy_strategy(",
                 "allocate_capital("]
    for token in forbidden:
        assert token not in src, f"forbidden reference: {token}"


def test_no_action_methods():
    import jarvis.research_lifecycle.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for kw in ("def execute", "def deploy", "def approve", "def trade", "def allocate",
               "def place_order"):
        assert kw not in src


def test_no_action_authority_api():
    api = set(dir(ResearchLifecycleEngine))
    for banned in ("execute", "deploy", "approve", "trade", "allocate", "place_order"):
        assert banned not in api


def test_transition_not_approval(tmp_path, monkeypatch):
    """프로젝트 이벤트에 approve/deploy/execute/trade 필드가 없어야 한다."""
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    d = p.to_dict()
    for banned in ("approve", "deploy", "execute", "trade", "order"):
        assert banned not in d


def test_live_execution_disabled_invariant():
    import jarvis.config as _cfg
    assert _cfg.live_execution_enabled() is False
    assert _cfg.AUTONOMY_LEVEL < _cfg.MIN_LIVE_LEVEL


def test_autonomy_unchanged(tmp_path, monkeypatch):
    import jarvis.config as _cfg
    before = _cfg.AUTONOMY_LEVEL
    _iso(tmp_path, monkeypatch)
    _full_lifecycle(_eng())
    assert _cfg.AUTONOMY_LEVEL == before
    assert _cfg.live_execution_enabled() is False


def test_no_delete_or_update_api():
    import importlib
    for mod_name in ("engine", "ledger"):
        m = importlib.import_module(f"jarvis.research_lifecycle.{mod_name}")
        for name in dir(m):
            low = name.lower()
            assert not low.startswith("delete_")
            assert not low.startswith("update_")
            assert not low.startswith("remove_")


def test_ledger_prefix_rl(tmp_path, monkeypatch):
    for fn, _idf in ledger.ALL_LEDGERS:
        assert fn.startswith("rl_")


def test_all_ledgers_distinct():
    names = [fn for fn, _ in ledger.ALL_LEDGERS]
    assert len(names) == len(set(names)) == 6


def test_engine_no_upstream_layer_import():
    import jarvis.research_lifecycle.engine as eng_mod
    with open(eng_mod.__file__) as f:
        src = f.read()
    for up in ("import jarvis.research_risk_intelligence", "import jarvis.self_audit_intelligence",
               "import jarvis.governance_orchestration", "import jarvis.research_compliance"):
        assert up not in src


# ── 추가 커버리지 ──
def test_id_prefixes_distinct():
    prefixes = {
        M.project_id("a")[:4],
        M.project_event_id("a", "", IDEA)[:4],
        M.transition_id("a", "", IDEA)[:4],
        M.event_id("a", "b", "c")[:4],
        M.bottleneck_id("a", "b", "c")[:4],
        M.report_id("a")[:4],
        M.artifact_id("a", "b")[:4],
    }
    assert len(prefixes) == 7


def test_content_hash_excludes_chain_fields():
    r1 = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    r2 = {"a": 1, "previous_hash": "z", "record_hash": "w"}
    assert M.content_hash(r1) == M.content_hash(r2)


def test_input_digest_order_matters():
    assert M.input_digest("a", "b") != M.input_digest("b", "a")


def test_detect_cycle_finds():
    assert M.detect_cycle([("a", "b"), ("b", "a")])


def test_detect_cycle_none():
    assert M.detect_cycle([("a", "b"), ("b", "c")]) == []


def test_stages_count():
    assert len(M.STAGES) == 7


def test_stages_order():
    assert M.STAGES == (IDEA, HYPOTHESIS, EXPERIMENT, BACKTEST, VALIDATION, DECISION, ARCHIVE)


def test_event_types_count():
    assert len(M.EVENT_TYPES) == 5


def test_bottleneck_categories_count():
    assert len(M.BOTTLENECK_CATEGORIES) == 5


def test_node_types_count():
    assert len(M.NODE_TYPES) == 6


def test_no_commit_no_files(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    _proj(eng, commit=False)
    for fn, _ in ledger.ALL_LEDGERS:
        assert ledger.read_jsonl(fn) == []


def test_project_to_dict_roundtrip(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    d = p.to_dict()
    assert d["project_id"] == p.project_id
    assert set(("name", "source_layer", "from_stage", "to_stage")).issubset(d)


def test_report_metrics_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {"k": 1}, T0, commit=True)
    assert r.metrics == {"k": 1}


def test_multiple_scopes_distinct_reports(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    eng.generate_report("A", {}, T0, commit=True)
    eng.generate_report("B", {}, T0, commit=True)
    assert len(ledger.read_reports()) == 2


def test_project_input_hash(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    p = _proj(_eng())
    assert p.input_hash == M.input_digest(p.project_id, "", IDEA)


def test_transition_note_kept(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "formed hypothesis", T1, commit=True)
    tr = ledger.transitions_for(p.project_id)[-1]
    assert tr["note"] == "formed hypothesis"


def test_entered_stages_order(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    assert eng.entered_stages(p.project_id) == [IDEA, HYPOTHESIS]


def test_source_ledgers_not_rl_prefixed():
    for layer, (fn, idf) in ledger.SOURCE_LEDGERS.items():
        assert not fn.startswith("rl_")
        assert isinstance(idf, str)


def test_engine_reused(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    a = eng.register_project("p1", "L", "r1", T0, commit=True)
    b = eng.register_project("p2", "L", "r2", T0, commit=True)
    assert a.project_id != b.project_id
    assert len(ledger.distinct_projects()) == 2


def test_disclaimer_full_phrases(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    r = _eng().generate_report("GLOBAL", {}, T0, commit=True)
    for phrase in ("LIFECYCLE TRACKING ≠ EXECUTION", "TRANSITION ≠ APPROVAL",
                   "STAGE ≠ DEPLOYMENT", "RECORD ≠ DECISION"):
        assert phrase in r.disclaimer


def test_transition_deterministic_id(tmp_path, monkeypatch):
    _iso(tmp_path, monkeypatch)
    eng = _eng()
    p = _proj(eng)
    eng.advance_stage(p.project_id, HYPOTHESIS, "", T1, commit=True)
    tr = ledger.transitions_for(p.project_id)[-1]
    assert tr["transition_id"] == M.transition_id(p.project_id, IDEA, HYPOTHESIS)
