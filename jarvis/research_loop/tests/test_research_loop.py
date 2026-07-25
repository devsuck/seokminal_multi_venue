"""Research Loop(C5) 테스트 — 단계 생애주기·**사람 승인 게이트**·검토·리포트·검증·재현·안전.

핵심: 제안→실행 전이는 사람 APPROVED 검토 없이는 절대 통과 못 한다. la_ 격리(state_path 몽키패치).
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.research_loop import ledger
from jarvis.research_loop import models as M
from jarvis.research_loop.engine import ResearchLoopEngine
from jarvis.research_loop.models import (
    ApprovalRequiredError,
    IllegalStageTransition,
    UnknownEntityError,
)
from jarvis.research_loop.verify import (
    approval_gate_integrity,
    duplicate_integrity,
    replay,
    stage_lifecycle_integrity,
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
    return ResearchLoopEngine()


def _loop(eng, title="momentum-study"):
    eng.create_loop(title, "관측: 모멘텀 이상", NOW, commit=True)
    return M.loop_id(title)


# ── 생성/단계 ──
def test_create_loop(eng):
    ev = eng.create_loop("study", "obs", NOW, commit=True)
    assert ev.from_stage == M.GENESIS
    assert ev.to_stage == M.S_OBSERVATION
    assert ev.loop_id.startswith("RLPL:")


def test_create_idempotent(eng):
    a = eng.create_loop("study", "o", NOW, commit=True)
    b = eng.create_loop("study", "o", NOW, commit=True)
    assert a.loop_id == b.loop_id
    assert len(ledger.loop_ids()) == 1


def test_stage_progression_to_proposal(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    assert eng.stage(lp) == M.S_PROPOSAL


def test_illegal_skip(eng):
    lp = _loop(eng)
    with pytest.raises(IllegalStageTransition):
        eng.to_proposal(lp, now=NOW, commit=True)   # OBSERVATION→PROPOSAL 불가


def test_advance_unknown_loop(eng):
    with pytest.raises(UnknownEntityError):
        eng.to_hypothesis("RLPL:deadbeef", now=NOW, commit=True)


# ── ★ 사람 승인 게이트 (핵심) ──
def test_execution_blocked_without_approval(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    # 승인 없이 실행 진입 시도 → 차단
    with pytest.raises(ApprovalRequiredError):
        eng.to_execution(lp, now=NOW, commit=True)
    assert eng.stage(lp) == M.S_PROPOSAL   # 여전히 제안 단계


def test_execution_allowed_after_human_approval(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.record_human_review(lp, "APPROVED", "researcher-kim", "검토 완료", NOW, commit=True)
    ev = eng.to_execution(lp, now=NOW, commit=True)
    assert ev.to_stage == M.S_EXECUTION


def test_rejected_review_does_not_open_gate(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.record_human_review(lp, "REJECTED", "researcher-kim", "부적절", NOW, commit=True)
    with pytest.raises(ApprovalRequiredError):
        eng.to_execution(lp, now=NOW, commit=True)


def test_review_requires_reviewer(eng):
    lp = _loop(eng)
    with pytest.raises(ValueError):
        eng.record_human_review(lp, "APPROVED", "", "", NOW, commit=True)


def test_review_bad_decision(eng):
    lp = _loop(eng)
    with pytest.raises(ValueError):
        eng.record_human_review(lp, "MAYBE", "kim", "", NOW, commit=True)


def test_approval_status(eng):
    lp = _loop(eng)
    assert eng.approval_status(lp) == M.REVIEW_PENDING
    eng.record_human_review(lp, "APPROVED", "kim", "", NOW, commit=True)
    assert eng.approval_status(lp) == M.REVIEW_APPROVED
    assert eng.is_approved(lp) is True


def test_review_is_human_flag(eng):
    lp = _loop(eng)
    r = eng.record_human_review(lp, "APPROVED", "kim", "", NOW, commit=True)
    assert r.is_human is True


def test_reject_path(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.reject(lp, now=NOW, commit=True)
    assert eng.stage(lp) == M.S_REJECTED


# ── 전체 루프 ──
def test_full_loop_with_approval(eng):
    lp = _loop(eng, "full-study")
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.record_human_review(lp, "APPROVED", "researcher-lee", "승인", NOW, commit=True)
    eng.to_execution(lp, now=NOW, commit=True)
    eng.to_validation(lp, now=NOW, commit=True)
    eng.to_report(lp, now=NOW, commit=True)
    eng.to_knowledge(lp, now=NOW, commit=True)
    eng.to_memory(lp, now=NOW, commit=True)
    eng.archive(lp, now=NOW, commit=True)
    assert eng.stage(lp) == M.S_ARCHIVED


@pytest.mark.parametrize("frm,to,ok", [
    (M.S_OBSERVATION, M.S_HYPOTHESIS, True),
    (M.S_OBSERVATION, M.S_PROPOSAL, False),
    (M.S_HYPOTHESIS, M.S_PROPOSAL, True),
    (M.S_PROPOSAL, M.S_EXECUTION, True),
    (M.S_PROPOSAL, M.S_REJECTED, True),
    (M.S_EXECUTION, M.S_VALIDATION, True),
    (M.S_VALIDATION, M.S_REPORT, True),
    (M.S_REPORT, M.S_KNOWLEDGE, True),
    (M.S_KNOWLEDGE, M.S_MEMORY, True),
    (M.S_MEMORY, M.S_ARCHIVED, True),
    (M.S_ARCHIVED, M.S_OBSERVATION, False),
    (M.S_REJECTED, M.S_EXECUTION, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_stage_transition(frm, to) is ok


def test_requires_human_approval():
    assert M.requires_human_approval(M.S_EXECUTION) is True
    assert M.requires_human_approval(M.S_VALIDATION) is False


def test_loops_in_stage(eng):
    a = _loop(eng, "a")
    _loop(eng, "b")
    eng.to_hypothesis(a, now=NOW, commit=True)
    assert eng.loops_in_stage(M.S_HYPOTHESIS) == [a]
    assert len(eng.loops_in_stage(M.S_OBSERVATION)) == 1


# ── 검증 ──
def test_verify_chain_clean(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.record_human_review(lp, "APPROVED", "kim", "", NOW, commit=True)
    eng.to_execution(lp, now=NOW, commit=True)
    eng.generate_report("SYSTEM", NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["approval_gate"]["ok"]


def test_verify_empty(eng):
    assert verify_chain()["ok"]


def test_gate_integrity_detects_ungated_execution(eng):
    # 승인 없이 EXECUTION 이벤트를 원장에 직접 주입 → 게이트 위반 탐지
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    p = pathlib.Path(ledger.state_path("rloop_loops.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    last = dict(rows[-1])
    last["to_stage"] = M.S_EXECUTION
    last["from_stage"] = M.S_PROPOSAL
    with p.open("a") as f:
        f.write(json.dumps(last) + "\n")
    assert not approval_gate_integrity()["ok"]


def test_tamper_detected(eng):
    _loop(eng)
    p = pathlib.Path(ledger.state_path("rloop_loops.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["title"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_stage_lifecycle_bad_initial(eng):
    _loop(eng)
    p = pathlib.Path(ledger.state_path("rloop_loops.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["to_stage"] = M.S_EXECUTION
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not stage_lifecycle_integrity()["ok"]


def test_duplicate_detected(eng):
    _loop(eng)
    p = pathlib.Path(ledger.state_path("rloop_loops.jsonl"))
    line = p.read_text().splitlines()[0]
    with p.open("a") as f:
        f.write(line + "\n")
    assert not duplicate_integrity()["ok"]


def test_report_counts(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    eng.to_proposal(lp, now=NOW, commit=True)
    eng.record_human_review(lp, "APPROVED", "kim", "", NOW, commit=True)
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert r.loop_count == 1
    assert r.approved_count == 1
    assert r.requires_human_approval is True
    assert r.is_binding is False


def test_report_disclaimer(eng):
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert "Human approval" in r.disclaimer or "사람 승인" in r.disclaimer


def test_replay_deterministic(eng):
    lp = _loop(eng)
    eng.to_hypothesis(lp, now=NOW, commit=True)
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["loop_count"] == 1


def test_summary(eng):
    lp = _loop(eng)
    eng.record_human_review(lp, "APPROVED", "kim", "", NOW, commit=True)
    eng.generate_report("SYSTEM", NOW, commit=True)
    s = eng.summary(NOW)
    assert s.loop_count == 1
    assert s.review_count == 1
    assert s.report_count == 1


# ── 원장·격리 ──
def test_three_ledgers():
    assert len(ledger.ALL_LEDGERS) == 3


def test_ledger_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("rloop_")


def test_no_stray_state(eng):
    _loop(eng)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("rloop_") for w in written)


# ── 안전 스캔 ──
_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_forbidden_imports(path):
    tree = ast.parse(open(path).read())
    bad = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution", "jarvis.live_trading",
           "jarvis.portfolio_execution")
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            assert not any(node.module.startswith(b) for b in bad), node.module


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_dangerous_defs(path):
    tree = ast.parse(open(path).read())
    bad = ("execute", "trade", "deploy", "allocate", "approve", "auto_approve", "auto_execute",
           "place_order", "activate_live")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_approve_or_execute(eng):
    for m in ("approve", "execute", "trade", "deploy", "allocate", "auto_approve"):
        assert not hasattr(eng, m)


def test_human_review_is_not_named_approve(eng):
    # 사람 결정 기록 메서드는 approve 가 아니라 record_human_review 여야(엔진이 승인하지 않음)
    assert hasattr(eng, "record_human_review")
    assert not hasattr(eng, "approve")


# ── CLI ──
def _cli(argv, tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.research_loop import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_create_and_review(tmp_path, monkeypatch, capsys):
    _cli(["create", "--title", "s", "--commit"], tmp_path, monkeypatch, capsys)
    lp = M.loop_id("s")
    rc, out = _cli(["review", "--loop", lp, "--decision", "APPROVED", "--reviewer", "kim",
                    "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "APPROVED" in out


def test_cli_status(tmp_path, monkeypatch, capsys):
    _cli(["create", "--title", "s", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["status", "--loop", M.loop_id("s")], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "PENDING_HUMAN_REVIEW" in out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _cli(["create", "--title", "s", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["verify"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert '"ok": true' in out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["summary"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "loop_count" in out
