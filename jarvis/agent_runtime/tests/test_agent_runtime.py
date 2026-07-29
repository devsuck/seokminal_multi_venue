"""Agent Runtime Layer(P45) 테스트 — 에이전트 생애주기·능력 허용목록·배정·산출물 안전·메모리 참조·로그·검증·재현·안전.

**거래·배포·실행·자본 결정 없음. 무제한 도구 접근 없음.** 격리 원장(tmp)에서 실행: state_path 몽키패치.
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.agent_runtime import ledger
from jarvis.agent_runtime import models as M
from jarvis.agent_runtime.engine import AgentRuntimeEngine
from jarvis.agent_runtime.models import (
    ForbiddenCapabilityError,
    IllegalAgentTransition,
    UnknownEntityError,
)
from jarvis.agent_runtime.verify import (
    agent_lifecycle_integrity,
    assignment_integrity,
    capability_integrity,
    duplicate_integrity,
    lineage_integrity,
    memory_reference_integrity,
    output_safety_integrity,
    replay,
    verify_chain,
)

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    return AgentRuntimeEngine()


def _agent(eng, name="a1", role="ANALYST", caps=("ANALYZE",)):
    eng.register_agent(name, role, list(caps), NOW, commit=True)
    return M.agent_id(name)


# ──────────────────────── 에이전트 등록/생애주기 ────────────────────────
def test_register_agent_genesis(eng):
    ev = eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    assert ev.from_state == M.GENESIS
    assert ev.to_state == M.A_CREATED
    assert ev.agent_id.startswith("ARNA:")
    assert ev.capabilities == ["ANALYZE"]


def test_register_idempotent(eng):
    a = eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    b = eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    assert a.agent_id == b.agent_id
    assert len(ledger.agent_ids()) == 1


def test_register_no_commit(eng):
    eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=False)
    assert ledger.agent_ids() == []


def test_register_bad_role(eng):
    with pytest.raises(ValueError):
        eng.register_agent("a1", "NONSENSE", ["ANALYZE"], NOW, commit=True)


def test_agent_initial_state(eng):
    a = _agent(eng)
    assert eng.agent_state(a) == M.A_CREATED


def test_full_agent_lifecycle(eng):
    a = _agent(eng)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.start_work(a, now=NOW, commit=True)
    eng.submit_for_review(a, now=NOW, commit=True)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.archive_agent(a, now=NOW, commit=True)
    assert eng.agent_state(a) == M.A_ARCHIVED


def test_agent_review_loop(eng):
    a = _agent(eng)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.start_work(a, now=NOW, commit=True)
    eng.submit_for_review(a, now=NOW, commit=True)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.start_work(a, now=NOW, commit=True)
    assert eng.agent_state(a) == M.A_WORKING


def test_illegal_skip_transition(eng):
    a = _agent(eng)
    with pytest.raises(IllegalAgentTransition):
        eng.start_work(a, now=NOW, commit=True)  # CREATED -> WORKING illegal


def test_illegal_created_to_review(eng):
    a = _agent(eng)
    with pytest.raises(IllegalAgentTransition):
        eng.submit_for_review(a, now=NOW, commit=True)


def test_archived_terminal(eng):
    a = _agent(eng)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.archive_agent(a, now=NOW, commit=True)
    with pytest.raises(IllegalAgentTransition):
        eng.mark_ready(a, now=NOW, commit=True)


def test_track_unknown_agent(eng):
    with pytest.raises(UnknownEntityError):
        eng.track_state("ARNA:deadbeef", M.A_READY, now=NOW, commit=True)


def test_track_bad_state(eng):
    a = _agent(eng)
    with pytest.raises(ValueError):
        eng.track_state(a, "NONSENSE", now=NOW, commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (M.A_CREATED, M.A_READY, True),
    (M.A_CREATED, M.A_WORKING, False),
    (M.A_CREATED, M.A_ARCHIVED, False),
    (M.A_READY, M.A_WORKING, True),
    (M.A_READY, M.A_ARCHIVED, True),
    (M.A_READY, M.A_WAITING_REVIEW, False),
    (M.A_WORKING, M.A_WAITING_REVIEW, True),
    (M.A_WORKING, M.A_READY, False),
    (M.A_WORKING, M.A_ARCHIVED, False),
    (M.A_WAITING_REVIEW, M.A_READY, True),
    (M.A_WAITING_REVIEW, M.A_ARCHIVED, True),
    (M.A_WAITING_REVIEW, M.A_WORKING, False),
    (M.A_ARCHIVED, M.A_READY, False),
    (M.A_ARCHIVED, M.A_ARCHIVED, False),
])
def test_agent_transition_matrix(frm, to, ok):
    assert M.can_agent_transition(frm, to) is ok


@pytest.mark.parametrize("role", list(M.AGENT_ROLES))
def test_all_roles(eng, role):
    ev = eng.register_agent(f"agent-{role}", role, ["ANALYZE"], NOW, commit=True)
    assert ev.role == role


# ──────────────────────── 능력 허용목록(보안 핵심) ────────────────────────
@pytest.mark.parametrize("cap", list(M.ALLOWED_CAPABILITIES))
def test_allowed_capabilities(eng, cap):
    ev = eng.register_agent("a1", "ANALYST", [cap], NOW, commit=True)
    assert cap in ev.capabilities


@pytest.mark.parametrize("cap", ["TRADE", "EXECUTE", "DEPLOY", "ALLOCATE", "ALLOCATE_CAPITAL",
                                 "PLACE_ORDER", "BROKER", "WITHDRAW", "TRANSFER", "*", "ALL",
                                 "ANY", "ADMIN", "ROOT", "SHELL", "UNRESTRICTED"])
def test_forbidden_capabilities_rejected(eng, cap):
    with pytest.raises(ForbiddenCapabilityError):
        eng.register_agent("a1", "ANALYST", [cap], NOW, commit=True)


def test_unlisted_capability_rejected(eng):
    with pytest.raises(ForbiddenCapabilityError):
        eng.register_agent("a1", "ANALYST", ["SOME_RANDOM_TOOL"], NOW, commit=True)


def test_mixed_caps_one_forbidden_rejected(eng):
    with pytest.raises(ForbiddenCapabilityError):
        eng.register_agent("a1", "ANALYST", ["ANALYZE", "TRADE"], NOW, commit=True)


def test_no_agent_persisted_on_forbidden_cap(eng):
    with pytest.raises(ForbiddenCapabilityError):
        eng.register_agent("a1", "ANALYST", ["TRADE"], NOW, commit=True)
    assert ledger.agent_ids() == []


def test_wildcard_capability_rejected(eng):
    with pytest.raises(ForbiddenCapabilityError):
        eng.register_agent("a1", "RESEARCHER", ["*"], NOW, commit=True)


def test_empty_capabilities_ok(eng):
    ev = eng.register_agent("a1", "MONITOR", [], NOW, commit=True)
    assert ev.capabilities == []


def test_validate_capabilities_normalizes():
    assert M.validate_capabilities(["analyze", " Simulate "]) == ["ANALYZE", "SIMULATE"]


def test_validate_capabilities_dedup():
    assert M.validate_capabilities(["ANALYZE", "analyze"]) == ["ANALYZE"]


@pytest.mark.parametrize("cap", list(M.FORBIDDEN_CAPABILITIES))
def test_is_forbidden_capability(cap):
    assert M.is_forbidden_capability(cap)


def test_is_allowed_capability():
    assert M.is_allowed_capability("ANALYZE")
    assert not M.is_allowed_capability("TRADE")
    assert not M.is_allowed_capability("RANDOM")


def test_agent_capabilities_accessor(eng):
    a = _agent(eng, caps=("ANALYZE", "REPORT"))
    assert eng.agent_capabilities(a) == ["ANALYZE", "REPORT"]


def test_capability_integrity_clean(eng):
    _agent(eng, caps=("ANALYZE", "SIMULATE"))
    assert capability_integrity()["ok"]


# ──────────────────────── 태스크 배정 ────────────────────────
def test_assign_task(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "분석 태스크", "설명", NOW, commit=True)
    assert t.task_id.startswith("ARNT:")
    assert t.agent_id == a
    assert t.status == "ASSIGNED"
    assert t.is_binding is False


def test_assign_multiple_tasks(eng):
    a = _agent(eng)
    eng.assign_task(a, "t1", now=NOW, commit=True)
    eng.assign_task(a, "t2", now=NOW, commit=True)
    assert len(ledger.assignments_for(a)) == 2


def test_assign_unknown_agent(eng):
    with pytest.raises(UnknownEntityError):
        eng.assign_task("ARNA:deadbeef", "t", now=NOW, commit=True)


def test_assign_to_archived_blocked(eng):
    a = _agent(eng)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.archive_agent(a, now=NOW, commit=True)
    with pytest.raises(IllegalAgentTransition):
        eng.assign_task(a, "t", now=NOW, commit=True)


def test_assign_no_commit(eng):
    a = _agent(eng)
    eng.assign_task(a, "t", now=NOW, commit=False)
    assert ledger.assignments_for(a) == []


def test_list_tasks(eng):
    a = _agent(eng)
    eng.assign_task(a, "t1", now=NOW, commit=True)
    assert len(eng.list_tasks(a)) == 1


def test_task_artifact_parent_is_agent(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    arts = ledger.read_artifacts()
    task_art = next(x for x in arts if x["ref_id"] == t.task_id)
    assert task_art["parent_artifact"] == M.artifact_id(M.ART_AGENT, a)


# ──────────────────────── 산출물(안전) ────────────────────────
def test_record_output(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    o = eng.record_output(a, t.task_id, "ANALYSIS", {"x": 1}, "요약", NOW, commit=True)
    assert o.output_id.startswith("ARNO:")
    assert o.is_binding is False
    assert o.is_executed is False


def test_output_always_non_binding_non_executed(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    for k in M.OUTPUT_KINDS:
        o = eng.record_output(a, t.task_id, k, {"k": k}, "", NOW, commit=True)
        assert o.is_binding is False
        assert o.is_executed is False
    assert output_safety_integrity()["ok"]


def test_output_bad_kind(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    with pytest.raises(ValueError):
        eng.record_output(a, t.task_id, "NONSENSE", {}, "", NOW, commit=True)


def test_output_unknown_agent(eng):
    with pytest.raises(UnknownEntityError):
        eng.record_output("ARNA:deadbeef", "ARNT:x", "ANALYSIS", {}, "", NOW, commit=True)


def test_output_content_hash_deterministic(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    o1 = eng.record_output(a, t.task_id, "ANALYSIS", {"x": 1}, "", NOW, commit=False)
    o2 = eng.record_output(a, t.task_id, "ANALYSIS", {"x": 1}, "", NOW, commit=False)
    assert o1.content_hash == o2.content_hash


def test_multiple_outputs_same_task(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    o1 = eng.record_output(a, t.task_id, "ANALYSIS", {"x": 1}, "", NOW, commit=True)
    o2 = eng.record_output(a, t.task_id, "ANALYSIS", {"x": 2}, "", NOW, commit=True)
    assert o1.output_id != o2.output_id
    assert len(ledger.outputs_for(a)) == 2


# ──────────────────────── 메모리 참조(READ ONLY) ────────────────────────
def test_reference_memory(eng):
    a = _agent(eng)
    r = eng.reference_memory(a, "research_memory_intelligence", "KM:abc", "분석 근거", NOW, commit=True)
    assert r.memref_id.startswith("ARNM:")
    assert r.is_read_only is True


def test_memref_idempotent(eng):
    a = _agent(eng)
    r1 = eng.reference_memory(a, "model_management", "MMM:x", "p1", NOW, commit=True)
    r2 = eng.reference_memory(a, "model_management", "MMM:x", "p2", NOW, commit=True)
    assert r1.memref_id == r2.memref_id
    assert r1.purpose == r2.purpose == "p1"


def test_memref_unknown_agent(eng):
    with pytest.raises(UnknownEntityError):
        eng.reference_memory("ARNA:deadbeef", "x", "y", "", NOW, commit=True)


def test_memref_read_only_integrity(eng):
    a = _agent(eng)
    eng.reference_memory(a, "experiment_tracking", "XT:1", "", NOW, commit=True)
    assert memory_reference_integrity()["ok"]


def test_memory_layers_defined():
    assert "research_memory_intelligence" in M.MEMORY_LAYERS
    assert "model_management" in M.MEMORY_LAYERS


# ──────────────────────── 로그 ────────────────────────
def test_log_activity(eng):
    a = _agent(eng)
    lg = eng.log_activity(a, "INFO", "시작", NOW, commit=True)
    assert lg.log_id.startswith("ARNL:")
    assert lg.level == "INFO"


def test_log_bad_level(eng):
    a = _agent(eng)
    with pytest.raises(ValueError):
        eng.log_activity(a, "NONSENSE", "msg", NOW, commit=True)


def test_log_unknown_agent(eng):
    with pytest.raises(UnknownEntityError):
        eng.log_activity("ARNA:deadbeef", "INFO", "msg", NOW, commit=True)


@pytest.mark.parametrize("level", list(M.LOG_LEVELS))
def test_all_log_levels(eng, level):
    a = _agent(eng)
    lg = eng.log_activity(a, level, "m", NOW, commit=True)
    assert lg.level == level


def test_multiple_logs(eng):
    a = _agent(eng)
    for i in range(3):
        eng.log_activity(a, "INFO", f"m{i}", NOW, commit=True)
    assert len(ledger.logs_for(a)) == 3


# ──────────────────────── 리포트 ────────────────────────
def test_report_empty(eng):
    r = eng.generate_agent_report("SYSTEM", NOW, commit=True)
    assert r.agent_count == 0
    assert r.is_binding is False
    assert r.requires_human_review is True


def test_report_counts(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    eng.reference_memory(a, "model_management", "MMM:1", "", NOW, commit=True)
    eng.log_activity(a, "INFO", "m", NOW, commit=True)
    eng.mark_ready(a, now=NOW, commit=True)
    eng.start_work(a, now=NOW, commit=True)
    r = eng.generate_agent_report("SYSTEM", NOW, commit=True)
    assert r.agent_count == 1
    assert r.working_agent_count == 1
    assert r.assignment_count == 1
    assert r.output_count == 1
    assert r.memref_count == 1
    assert r.log_count == 1


def test_report_role_distribution(eng):
    eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    eng.register_agent("a2", "REVIEWER", ["REPORT"], NOW, commit=True)
    r = eng.generate_agent_report("SYSTEM", NOW, commit=True)
    assert r.role_distribution.get("ANALYST") == 1
    assert r.role_distribution.get("REVIEWER") == 1


def test_report_disclaimer(eng):
    r = eng.generate_agent_report("SYSTEM", NOW, commit=True)
    assert "AUTONOMOUS TRADING" in r.disclaimer


def test_report_deterministic(eng):
    _agent(eng)
    r1 = eng.generate_agent_report("SYSTEM", NOW, commit=False)
    r2 = eng.generate_agent_report("SYSTEM", NOW, commit=False)
    assert r1.to_dict() == r2.to_dict()


# ──────────────────────── 해시체인·검증 ────────────────────────
def test_verify_chain_clean(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    eng.reference_memory(a, "model_management", "MMM:1", "", NOW, commit=True)
    eng.log_activity(a, "INFO", "m", NOW, commit=True)
    eng.generate_agent_report("SYSTEM", NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] > 0


def test_verify_empty(eng):
    assert verify_chain()["ok"]


def test_hash_chain_links(eng):
    eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    eng.register_agent("a2", "ANALYST", ["ANALYZE"], NOW, commit=True)
    recs = ledger.read_agent_events()
    assert recs[0]["previous_hash"] == M.GENESIS
    assert recs[1]["previous_hash"] == recs[0]["record_hash"]


def test_tamper_detected(eng):
    _agent(eng)
    p = pathlib.Path(ledger.state_path("agrt_agents.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["name"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_broken_chain_detected(eng):
    eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    eng.register_agent("a2", "ANALYST", ["ANALYZE"], NOW, commit=True)
    p = pathlib.Path(ledger.state_path("agrt_agents.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeefdeadbeef"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_duplicate_agent_detected(eng):
    _agent(eng)
    p = pathlib.Path(ledger.state_path("agrt_agents.jsonl"))
    line = p.read_text().splitlines()[0]
    with p.open("a") as f:
        f.write(line + "\n")
    assert not duplicate_integrity()["ok"]


def test_bad_initial_state_detected(eng):
    _agent(eng)
    p = pathlib.Path(ledger.state_path("agrt_agents.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["to_state"] = M.A_WORKING
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not agent_lifecycle_integrity()["ok"]


def test_binding_output_detected(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("agrt_outputs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_binding"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not output_safety_integrity()["ok"]


def test_executed_output_detected(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("agrt_outputs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_executed"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not output_safety_integrity()["ok"]


def test_forbidden_capability_in_ledger_detected(eng):
    _agent(eng)
    p = pathlib.Path(ledger.state_path("agrt_agents.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["capabilities"] = ["TRADE"]
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not capability_integrity()["ok"]


def test_mutable_memref_detected(eng):
    a = _agent(eng)
    eng.reference_memory(a, "model_management", "MMM:1", "", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("agrt_memory_refs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_read_only"] = False
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not memory_reference_integrity()["ok"]


def test_assignment_integrity_ok(eng):
    a = _agent(eng)
    eng.assign_task(a, "t", now=NOW, commit=True)
    assert assignment_integrity()["ok"]


def test_lineage_integrity_ok(eng):
    a = _agent(eng)
    eng.assign_task(a, "t", now=NOW, commit=True)
    assert lineage_integrity()["ok"]


# ──────────────────────── 재현·요약 ────────────────────────
def test_replay_deterministic(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["agent_count"] == 1
    assert r["output_count"] == 1


def test_summary_counts(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    eng.record_output(a, t.task_id, "ANALYSIS", {}, "", NOW, commit=True)
    eng.reference_memory(a, "model_management", "MMM:1", "", NOW, commit=True)
    eng.log_activity(a, "INFO", "m", NOW, commit=True)
    eng.generate_agent_report("SYSTEM", NOW, commit=True)
    s = eng.summary(NOW)
    assert s.agent_count == 1
    assert s.assignment_count == 1
    assert s.output_count == 1
    assert s.memref_count == 1
    assert s.log_count == 1
    assert s.report_count == 1


def test_agents_in_state(eng):
    eng.register_agent("a1", "ANALYST", ["ANALYZE"], NOW, commit=True)
    eng.register_agent("a2", "ANALYST", ["ANALYZE"], NOW, commit=True)
    eng.mark_ready(M.agent_id("a1"), now=NOW, commit=True)
    assert eng.agents_in_state(M.A_READY) == [M.agent_id("a1")]
    assert len(eng.agents_in_state(M.A_CREATED)) == 1


# ──────────────────────── ID 접두사 ────────────────────────
@pytest.mark.parametrize("fn,args,prefix", [
    (M.agent_id, ("x",), "ARNA:"),
    (M.agent_event_id, ("x", "CREATED", 0), "ARNE:"),
    (M.task_id, ("a", "t", 0), "ARNT:"),
    (M.output_id, ("a", "t", 0), "ARNO:"),
    (M.memref_id, ("a", "L", "r"), "ARNM:"),
    (M.log_id, ("a", 0), "ARNL:"),
    (M.report_id, ("SYSTEM", NOW), "ARNR:"),
    (M.artifact_id, ("AGENT", "ref"), "ARNF:"),
])
def test_id_prefixes(fn, args, prefix):
    assert fn(*args).startswith(prefix)


def test_ids_deterministic():
    assert M.agent_id("a1") == M.agent_id("a1")
    assert M.agent_id("a1") != M.agent_id("a2")


# ──────────────────────── 안전(금지 동사/import/모델유출/메서드) ────────────────────────
@pytest.mark.parametrize("verb", [
    "EXECUTE_TRADE", "PLACE_ORDER", "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "ACTIVATE_LIVE",
    "BROKER_EXECUTION", "EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE", "AUTO_EXECUTE",
    "AUTO_TRADE", "SELF_EXECUTE", "SERVE_LIVE",
])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_forbidden_verb_case_insensitive():
    assert M.is_forbidden_verb("execute")
    assert M.is_forbidden_verb(" Trade ")


def test_not_forbidden_verbs():
    for v in ("analyze", "record", "simulate", "recommend", "assign", "report"):
        assert not M.is_forbidden_verb(v)


_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]
_FORBIDDEN_IMPORTS = (
    "jarvis.execution", "jarvis.broker", "jarvis.live_trading", "jarvis.portfolio_execution",
    "jarvis.live_portfolio", "jarvis.portfolio", "jarvis.order", "jarvis.deployment", "jarvis.live",
)


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(f) for f in _FORBIDDEN_IMPORTS), node.module
        if isinstance(node, ast.Import):
            for n in node.names:
                assert not any(n.name.startswith(f) for f in _FORBIDDEN_IMPORTS), n.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live",
           "auto_execute", "auto_trade", "self_execute", "serve_live")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name
        if isinstance(node, ast.FunctionDef):
            assert not node.name.startswith(("delete_", "overwrite_", "drop_", "truncate", "purge_"))


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve", "place_order", "activate_live"):
        assert not hasattr(eng, m)


# ──────────────────────── READ ONLY 소스 ────────────────────────
def test_source_layers_defined():
    assert "workflow_automation" in ledger.SOURCE_LAYERS
    assert "model_management" in ledger.SOURCE_LAYERS
    assert "experiment_tracking" in ledger.SOURCE_LAYERS


def test_source_count_absent(eng):
    assert ledger.source_count("workflow_automation") == 0
    assert ledger.source_present("workflow_automation") is False


def test_all_source_counts(eng):
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)
    assert all(v == 0 for v in counts.values())


def test_source_count_unknown(eng):
    assert ledger.source_count("nope") == 0


# ──────────────────────── 원장 접두사·격리 ────────────────────────
def test_all_ledger_files_agrt_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("agrt_")


def test_seven_ledgers():
    assert len(ledger.ALL_LEDGERS) == 7


def test_no_stray_state_files(eng):
    _agent(eng)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("agrt_") for w in written)


# ──────────────────────── CLI ────────────────────────
def _run_cli(argv, tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.agent_runtime import __main__ as cli
    return cli.main(argv)


def test_cli_agent(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
                  tmp_path, monkeypatch)
    assert rc == 0
    assert "ARNA:" in capsys.readouterr().out


def test_cli_state(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
             tmp_path, monkeypatch)
    a = M.agent_id("a1")
    rc = _run_cli(["state", "--agent", a, "--to", "READY", "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    assert "READY" in capsys.readouterr().out


def test_cli_assign_and_output(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
             tmp_path, monkeypatch)
    a = M.agent_id("a1")
    _run_cli(["assign", "--agent", a, "--title", "t", "--commit"], tmp_path, monkeypatch)
    tid = M.task_id(a, "t", 0)
    rc = _run_cli(["output", "--agent", a, "--task", tid, "--kind", "ANALYSIS", "--commit"],
                  tmp_path, monkeypatch)
    assert rc == 0
    out = capsys.readouterr().out
    assert "is_executed=False" in out


def test_cli_memref(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "QUERY_MEMORY", "--commit"],
             tmp_path, monkeypatch)
    a = M.agent_id("a1")
    rc = _run_cli(["memref", "--agent", a, "--layer", "model_management", "--ref", "MMM:1",
                   "--commit"], tmp_path, monkeypatch)
    assert rc == 0
    assert "is_read_only=True" in capsys.readouterr().out


def test_cli_log(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
             tmp_path, monkeypatch)
    a = M.agent_id("a1")
    rc = _run_cli(["log", "--agent", a, "--level", "INFO", "--message", "hi", "--commit"],
                  tmp_path, monkeypatch)
    assert rc == 0
    assert "ARNL:" in capsys.readouterr().out


def test_cli_report(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["report", "--scope", "SYSTEM"], tmp_path, monkeypatch)
    assert rc == 0
    assert "is_binding" in capsys.readouterr().out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
             tmp_path, monkeypatch)
    rc = _run_cli(["verify"], tmp_path, monkeypatch)
    assert rc == 0
    assert '"ok": true' in capsys.readouterr().out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc = _run_cli(["summary"], tmp_path, monkeypatch)
    assert rc == 0
    assert "agent_count" in capsys.readouterr().out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "ANALYZE", "--commit"],
             tmp_path, monkeypatch)
    rc = _run_cli(["replay"], tmp_path, monkeypatch)
    assert rc == 0
    assert "deterministic" in capsys.readouterr().out


def test_cli_agent_forbidden_cap_raises(tmp_path, monkeypatch):
    with pytest.raises(ForbiddenCapabilityError):
        _run_cli(["agent", "--name", "a1", "--role", "ANALYST", "--cap", "TRADE", "--commit"],
                 tmp_path, monkeypatch)


# ──────────────────────── 레코드/헬퍼 ────────────────────────
def test_records_to_dict(eng):
    a = _agent(eng)
    t = eng.assign_task(a, "t", now=NOW, commit=True)
    assert t.to_dict()["task_id"] == t.task_id
    r = eng.generate_agent_report("SYSTEM", NOW, commit=False)
    assert r.to_dict()["requires_human_review"] is True


def test_content_hash_excludes_meta():
    rec = {"a": 1, "previous_hash": "x", "record_hash": "y"}
    rec2 = {"a": 1, "previous_hash": "Z", "record_hash": "W"}
    assert M.content_hash(rec) == M.content_hash(rec2)


def test_clamp01():
    assert M.clamp01(2) == 1.0
    assert M.clamp01(-1) == 0.0
    assert M.clamp01("x") == 0.0


def test_detect_cycle():
    assert M.detect_cycle_check([("a", "b"), ("b", "a")])
    assert not M.detect_cycle_check([("a", "b"), ("b", "c")])


# ──────────────────────── 엔드투엔드 ────────────────────────
def test_end_to_end(eng):
    # 에이전트 등록(연구 능력만) → 준비 → 태스크 배정 → 작업 → 메모리 참조 → 산출물 → 검토 대기 → 리포트
    eng.register_agent("researcher-1", "RESEARCHER",
                       ["ANALYZE", "SIMULATE", "QUERY_MEMORY", "REPORT"], NOW, commit=True)
    a = M.agent_id("researcher-1")
    eng.mark_ready(a, now=NOW, commit=True)
    t = eng.assign_task(a, "팩터 분석", "모멘텀 팩터 연구", NOW, commit=True)
    eng.start_work(a, now=NOW, commit=True)
    eng.log_activity(a, "INFO", "작업 시작", NOW, commit=True)
    eng.reference_memory(a, "research_memory_intelligence", "KM:factor", "선행 연구 참조", NOW, commit=True)
    eng.reference_memory(a, "model_management", "MMM:model1", "모델 성능 참조", NOW, commit=True)
    o1 = eng.record_output(a, t.task_id, "ANALYSIS", {"factor": "momentum", "ic": 0.05},
                           "IC 0.05 관측", NOW, commit=True)
    eng.record_output(a, t.task_id, "RECOMMENDATION", {"action": "further_research"},
                      "추가 연구 권고(사람 검토용)", NOW, commit=True)
    eng.submit_for_review(a, now=NOW, commit=True)
    assert eng.agent_state(a) == M.A_WAITING_REVIEW
    # 산출물은 절대 자동 실행/구속력 없음
    assert o1.is_binding is False and o1.is_executed is False
    r = eng.generate_agent_report("SYSTEM", NOW, commit=True)
    assert r.agent_count == 1
    assert r.waiting_review_count == 1
    assert r.assignment_count == 1
    assert r.output_count == 2
    assert r.memref_count == 2
    assert r.log_count == 1
    assert r.requires_human_review is True
    res = verify_chain()
    assert res["ok"]
    assert res["agent_lifecycle"]["ok"]
    assert res["capability"]["ok"]
    assert res["output_safety"]["ok"]
    assert res["memory_reference"]["ok"]
    assert res["assignment"]["ok"]


def test_end_to_end_two_agents_isolated(eng):
    a1 = _agent(eng, name="a1")
    a2 = _agent(eng, name="a2", role="REVIEWER", caps=("REPORT",))
    eng.assign_task(a1, "x", now=NOW, commit=True)
    eng.assign_task(a2, "y", now=NOW, commit=True)
    assert len(ledger.assignments_for(a1)) == 1
    assert len(ledger.assignments_for(a2)) == 1
    assert verify_chain()["ok"]
