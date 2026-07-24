"""Local Research Automation(P45) 테스트 — 잡 생애주기·스케줄·실행·파이프라인·로그·검증·재현·안전.

**워크플로 보조, 거래·배포·배분 없음.** la_ 원장은 tmp 로 격리(state_path 몽키패치).
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.local_automation import ledger
from jarvis.local_automation import models as M
from jarvis.local_automation.engine import LocalAutomationEngine
from jarvis.local_automation.models import (
    ForbiddenJobKindError,
    IllegalJobTransition,
    UnknownEntityError,
)
from jarvis.local_automation.verify import (
    duplicate_integrity,
    job_kind_integrity,
    job_lifecycle_integrity,
    replay,
    run_safety_integrity,
    schedule_integrity,
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
    return LocalAutomationEngine()


def _job(eng, name="daily-refresh", kind="DATA_REFRESH"):
    eng.register_job(name, kind, NOW, commit=True)
    return M.job_id(name)


# ──────────────────────── 잡 등록/생애주기 ────────────────────────
def test_register_job(eng):
    ev = eng.register_job("daily-refresh", "DATA_REFRESH", NOW, commit=True)
    assert ev.from_state == M.GENESIS
    assert ev.to_state == M.J_REGISTERED
    assert ev.job_id.startswith("LAJ:")
    assert ev.kind == "DATA_REFRESH"


def test_register_idempotent(eng):
    a = eng.register_job("j", "HEALTH_CHECK", NOW, commit=True)
    b = eng.register_job("j", "HEALTH_CHECK", NOW, commit=True)
    assert a.job_id == b.job_id
    assert len(ledger.job_ids()) == 1


def test_register_no_commit(eng):
    eng.register_job("j", "HEALTH_CHECK", NOW, commit=False)
    assert ledger.job_ids() == []


@pytest.mark.parametrize("kind", list(M.JOB_KINDS))
def test_all_job_kinds(eng, kind):
    ev = eng.register_job(f"job-{kind}", kind, NOW, commit=True)
    assert ev.kind == kind


@pytest.mark.parametrize("kind", ["TRADE", "DEPLOY", "ALLOCATE", "EXECUTE_TRADE", "PLACE_ORDER",
                                  "ALLOCATE_CAPITAL", "DEPLOY_STRATEGY", "LIVE_EXECUTION",
                                  "AUTO_TRADE", "AUTO_DEPLOY", "AUTO_ALLOCATE"])
def test_forbidden_job_kinds_rejected(eng, kind):
    with pytest.raises(ForbiddenJobKindError):
        eng.register_job("bad", kind, NOW, commit=True)


def test_forbidden_kind_not_persisted(eng):
    with pytest.raises(ForbiddenJobKindError):
        eng.register_job("bad", "TRADE", NOW, commit=True)
    assert ledger.job_ids() == []


def test_unknown_kind_rejected(eng):
    with pytest.raises(ValueError):
        eng.register_job("j", "NONSENSE", NOW, commit=True)


def test_job_lifecycle(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    assert eng.job_state(j) == M.J_ENABLED
    eng.disable_job(j, now=NOW, commit=True)
    assert eng.job_state(j) == M.J_DISABLED
    eng.enable_job(j, now=NOW, commit=True)
    assert eng.job_state(j) == M.J_ENABLED
    eng.archive_job(j, now=NOW, commit=True)
    assert eng.job_state(j) == M.J_ARCHIVED


def test_illegal_transition_from_registered(eng):
    j = _job(eng)
    with pytest.raises(IllegalJobTransition):
        eng.disable_job(j, now=NOW, commit=True)   # REGISTERED -> DISABLED illegal


def test_archived_terminal(eng):
    j = _job(eng)
    eng.archive_job(j, now=NOW, commit=True)
    with pytest.raises(IllegalJobTransition):
        eng.enable_job(j, now=NOW, commit=True)


def test_transition_unknown_job(eng):
    with pytest.raises(UnknownEntityError):
        eng.enable_job("LAJ:deadbeef", now=NOW, commit=True)


@pytest.mark.parametrize("frm,to,ok", [
    (M.J_REGISTERED, M.J_ENABLED, True),
    (M.J_REGISTERED, M.J_ARCHIVED, True),
    (M.J_REGISTERED, M.J_DISABLED, False),
    (M.J_ENABLED, M.J_DISABLED, True),
    (M.J_ENABLED, M.J_ARCHIVED, True),
    (M.J_ENABLED, M.J_REGISTERED, False),
    (M.J_DISABLED, M.J_ENABLED, True),
    (M.J_DISABLED, M.J_ARCHIVED, True),
    (M.J_ARCHIVED, M.J_ENABLED, False),
    (M.J_ARCHIVED, M.J_ARCHIVED, False),
])
def test_transition_matrix(frm, to, ok):
    assert M.can_job_transition(frm, to) is ok


def test_jobs_in_state(eng):
    eng.register_job("a", "DATA_REFRESH", NOW, commit=True)
    eng.register_job("b", "HEALTH_CHECK", NOW, commit=True)
    eng.enable_job(M.job_id("a"), now=NOW, commit=True)
    assert eng.jobs_in_state(M.J_ENABLED) == [M.job_id("a")]
    assert len(eng.jobs_in_state(M.J_REGISTERED)) == 1


# ──────────────────────── 스케줄 ────────────────────────
def test_set_schedule(eng):
    j = _job(eng)
    s = eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    assert s.schedule_id.startswith("LAS:")
    assert s.cadence == "DAILY"
    assert s.enabled is True


def test_schedule_lowercase_normalized(eng):
    j = _job(eng)
    s = eng.set_schedule(j, "daily", True, NOW, commit=True)
    assert s.cadence == "DAILY"


def test_schedule_bad_cadence(eng):
    j = _job(eng)
    with pytest.raises(ValueError):
        eng.set_schedule(j, "YEARLY", True, NOW, commit=True)


def test_schedule_unknown_job(eng):
    with pytest.raises(UnknownEntityError):
        eng.set_schedule("LAJ:deadbeef", "DAILY", True, NOW, commit=True)


@pytest.mark.parametrize("cadence,tick,expected", [
    ("HOURLY", 0, True),
    ("HOURLY", 1, True),
    ("HOURLY", 5, True),
    ("DAILY", 0, True),
    ("DAILY", 24, True),
    ("DAILY", 25, False),
    ("DAILY", 12, False),
    ("WEEKLY", 168, True),
    ("WEEKLY", 100, False),
    ("MANUAL", 0, False),
    ("MANUAL", 24, False),
])
def test_is_due(cadence, tick, expected):
    assert M.is_due(cadence, tick) is expected


def test_is_due_bad_tick():
    assert M.is_due("DAILY", "x") is False
    assert M.is_due("DAILY", -1) is False


def test_due_jobs(eng):
    j1 = _job(eng, "hourly-job", "HEALTH_CHECK")
    j2 = _job(eng, "daily-job", "DATA_REFRESH")
    eng.set_schedule(j1, "HOURLY", True, NOW, commit=True)
    eng.set_schedule(j2, "DAILY", True, NOW, commit=True)
    # tick=1: hourly due (1%1==0), daily not (1%24!=0)
    assert eng.due_jobs(1) == [j1]
    # tick=24: both due
    assert set(eng.due_jobs(24)) == {j1, j2}


def test_due_jobs_disabled_schedule(eng):
    j = _job(eng)
    eng.set_schedule(j, "HOURLY", False, NOW, commit=True)
    assert eng.due_jobs(1) == []


def test_manual_never_due(eng):
    j = _job(eng)
    eng.set_schedule(j, "MANUAL", True, NOW, commit=True)
    assert eng.due_jobs(0) == []
    assert eng.due_jobs(24) == []


# ──────────────────────── 실행(run_job) ────────────────────────
def test_run_job_default_success(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    r = eng.run_job(j, None, NOW, commit=True)
    assert r.status == M.RUN_SUCCESS
    assert r.is_binding is False
    assert r.run_id.startswith("LAR:")


def test_run_job_with_action_ok(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    r = eng.run_job(j, lambda: {"ok": True, "summary": "refreshed 3 datasets"}, NOW, commit=True)
    assert r.status == M.RUN_SUCCESS
    assert r.summary == "refreshed 3 datasets"


def test_run_job_with_action_fail(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    r = eng.run_job(j, lambda: {"ok": False, "summary": "source unreachable"}, NOW, commit=True)
    assert r.status == M.RUN_FAILED


def test_run_job_action_exception(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)

    def boom():
        raise RuntimeError("kaboom")

    r = eng.run_job(j, boom, NOW, commit=True)
    assert r.status == M.RUN_FAILED
    assert "kaboom" in r.summary


def test_run_disabled_job_skipped(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.disable_job(j, now=NOW, commit=True)
    r = eng.run_job(j, None, NOW, commit=True)
    assert r.status == M.RUN_SKIPPED


def test_run_archived_job_skipped(eng):
    j = _job(eng)
    eng.archive_job(j, now=NOW, commit=True)
    r = eng.run_job(j, None, NOW, commit=True)
    assert r.status == M.RUN_SKIPPED


def test_run_unknown_job(eng):
    with pytest.raises(UnknownEntityError):
        eng.run_job("LAJ:deadbeef", None, NOW, commit=True)


def test_run_history(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    assert len(eng.run_history(j)) == 2


def test_run_ids_unique(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    ids = [r["run_id"] for r in ledger.runs_for(j)]
    assert len(ids) == len(set(ids)) == 2


def test_run_no_commit(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=False)
    assert ledger.runs_for(j) == []


def test_run_result_deterministic(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    r1 = eng.run_job(j, lambda: {"ok": True, "summary": "x"}, NOW, commit=False)
    r2 = eng.run_job(j, lambda: {"ok": True, "summary": "x"}, NOW, commit=False)
    assert r1.result_digest == r2.result_digest


# ──────────────────────── 파이프라인·due 실행 ────────────────────────
def test_run_pipeline(eng):
    # 예시 일일 워크플로: 데이터확인 → 품질검사 → 기록 → 요약 → 통지
    names = ["check-data", "validate-quality", "update-records", "gen-summary", "notify"]
    kinds = ["DATA_REFRESH", "DATA_QUALITY_CHECK", "MEMORY_UPDATE", "REPORT_GENERATION", "NOTIFY"]
    jobs = []
    for n, k in zip(names, kinds):
        j = _job(eng, n, k)
        eng.enable_job(j, now=NOW, commit=True)
        jobs.append(j)
    runs = eng.run_pipeline(jobs, None, NOW, commit=True)
    assert len(runs) == 5
    assert all(r.status == M.RUN_SUCCESS for r in runs)


def test_run_pipeline_with_actions(eng):
    j = _job(eng, "j", "DATA_REFRESH")
    eng.enable_job(j, now=NOW, commit=True)
    runs = eng.run_pipeline([j], {j: lambda: {"ok": True, "summary": "done"}}, NOW, commit=True)
    assert runs[0].summary == "done"


def test_run_due(eng):
    j = _job(eng, "hourly", "HEALTH_CHECK")
    eng.enable_job(j, now=NOW, commit=True)
    eng.set_schedule(j, "HOURLY", True, NOW, commit=True)
    runs = eng.run_due(1, None, NOW, commit=True)
    assert len(runs) == 1
    assert runs[0].job_id == j


def test_run_due_none(eng):
    j = _job(eng, "daily", "DATA_REFRESH")
    eng.enable_job(j, now=NOW, commit=True)
    eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    assert eng.run_due(1, None, NOW, commit=True) == []


# ──────────────────────── 로그 ────────────────────────
def test_log_activity(eng):
    j = _job(eng)
    lg = eng.log_activity(j, "INFO", "started", NOW, commit=True)
    assert lg.log_id.startswith("LAL:")
    assert lg.level == "INFO"


def test_log_bad_level(eng):
    j = _job(eng)
    with pytest.raises(ValueError):
        eng.log_activity(j, "NONSENSE", "m", NOW, commit=True)


@pytest.mark.parametrize("level", list(M.LOG_LEVELS))
def test_log_levels(eng, level):
    j = _job(eng)
    lg = eng.log_activity(j, level, "m", NOW, commit=True)
    assert lg.level == level


# ──────────────────────── 리포트 ────────────────────────
def test_report_empty(eng):
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert r.job_count == 0
    assert r.is_binding is False


def test_report_counts(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    eng.run_job(j, lambda: {"ok": False, "summary": "x"}, NOW, commit=True)
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert r.job_count == 1
    assert r.enabled_job_count == 1
    assert r.run_count == 2
    assert r.success_count == 1
    assert r.failed_count == 1
    assert r.schedule_count == 1


def test_report_distributions(eng):
    _job(eng, "a", "DATA_REFRESH")
    _job(eng, "b", "HEALTH_CHECK")
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert r.kind_distribution.get("DATA_REFRESH") == 1
    assert r.kind_distribution.get("HEALTH_CHECK") == 1


def test_report_disclaimer(eng):
    r = eng.generate_report("SYSTEM", NOW, commit=True)
    assert "WORKFLOW ASSISTANCE" in r.disclaimer


def test_report_deterministic(eng):
    _job(eng)
    r1 = eng.generate_report("SYSTEM", NOW, commit=False)
    r2 = eng.generate_report("SYSTEM", NOW, commit=False)
    assert r1.to_dict() == r2.to_dict()


# ──────────────────────── 검증·재현 ────────────────────────
def test_verify_chain_clean(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    eng.log_activity(j, "INFO", "m", NOW, commit=True)
    eng.generate_report("SYSTEM", NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] > 0


def test_verify_empty(eng):
    assert verify_chain()["ok"]


def test_hash_chain_links(eng):
    eng.register_job("a", "DATA_REFRESH", NOW, commit=True)
    eng.register_job("b", "HEALTH_CHECK", NOW, commit=True)
    recs = ledger.read_job_events()
    assert recs[0]["previous_hash"] == M.GENESIS
    assert recs[1]["previous_hash"] == recs[0]["record_hash"]


def test_tamper_detected(eng):
    _job(eng)
    p = pathlib.Path(ledger.state_path("la_jobs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["name"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_broken_chain_detected(eng):
    eng.register_job("a", "DATA_REFRESH", NOW, commit=True)
    eng.register_job("b", "HEALTH_CHECK", NOW, commit=True)
    p = pathlib.Path(ledger.state_path("la_jobs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeefdeadbeef"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_forbidden_kind_in_ledger_detected(eng):
    _job(eng)
    p = pathlib.Path(ledger.state_path("la_jobs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["kind"] = "TRADE"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not job_kind_integrity()["ok"]


def test_binding_run_detected(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    p = pathlib.Path(ledger.state_path("la_runs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["is_binding"] = True
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not run_safety_integrity()["ok"]


def test_bad_initial_state_detected(eng):
    _job(eng)
    p = pathlib.Path(ledger.state_path("la_jobs.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["to_state"] = M.J_ENABLED
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not job_lifecycle_integrity()["ok"]


def test_duplicate_job_detected(eng):
    _job(eng)
    p = pathlib.Path(ledger.state_path("la_jobs.jsonl"))
    line = p.read_text().splitlines()[0]
    with p.open("a") as f:
        f.write(line + "\n")
    assert not duplicate_integrity()["ok"]


def test_schedule_integrity_clean(eng):
    j = _job(eng)
    eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    assert schedule_integrity()["ok"]


def test_run_safety_clean(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    assert run_safety_integrity()["ok"]


def test_replay_deterministic(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["job_count"] == 1


def test_summary(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.set_schedule(j, "DAILY", True, NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    eng.log_activity(j, "INFO", "m", NOW, commit=True)
    eng.generate_report("SYSTEM", NOW, commit=True)
    s = eng.summary(NOW)
    assert s.job_count == 1
    assert s.schedule_count == 1
    assert s.run_count == 1
    assert s.log_count == 1
    assert s.report_count == 1


# ──────────────────────── READ ONLY 소스 ────────────────────────
def test_source_layers_defined():
    assert "experiment_tracking" in ledger.SOURCE_LAYERS


def test_source_count_absent(eng):
    assert ledger.source_count("experiment_tracking") == 0


def test_all_source_counts(eng):
    counts = ledger.all_source_counts()
    assert set(counts) == set(ledger.SOURCE_LAYERS)
    assert all(v == 0 for v in counts.values())


# ──────────────────────── 원장 접두사·격리 ────────────────────────
def test_five_ledgers():
    assert len(ledger.ALL_LEDGERS) == 5


def test_ledger_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("la_")


def test_no_stray_state_files(eng):
    j = _job(eng)
    eng.enable_job(j, now=NOW, commit=True)
    eng.run_job(j, None, NOW, commit=True)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("la_") for w in written)


# ──────────────────────── 안전 스캔 ────────────────────────
@pytest.mark.parametrize("verb", ["EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
                                  "AUTO_TRADE", "AUTO_DEPLOY", "AUTO_ALLOCATE",
                                  "APPROVE_FOR_TRADING", "PLACE_ORDER"])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_not_forbidden_verbs():
    for v in ("refresh", "check", "generate", "update", "notify"):
        assert not M.is_forbidden_verb(v)


_SRC_FILES = [str(SRC / f) for f in ("engine.py", "ledger.py", "models.py", "verify.py",
                                     "__main__.py", "__init__.py")]
_FORBIDDEN_IMPORTS = ("jarvis.execution", "jarvis.broker", "jarvis.live_execution",
                      "jarvis.live_trading", "jarvis.portfolio_execution", "jarvis.order")


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
           "auto_trade", "auto_deploy", "auto_allocate")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(eng, m)


# ──────────────────────── CLI ────────────────────────
def _cli(argv, tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.local_automation import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_job(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["job", "--name", "j", "--kind", "DATA_REFRESH", "--commit"], tmp_path,
                   monkeypatch, capsys)
    assert rc == 0
    assert "LAJ:" in out


def test_cli_forbidden_kind_raises(tmp_path, monkeypatch, capsys):
    with pytest.raises(ForbiddenJobKindError):
        _cli(["job", "--name", "j", "--kind", "TRADE", "--commit"], tmp_path, monkeypatch, capsys)


def test_cli_enable_and_run(tmp_path, monkeypatch, capsys):
    _cli(["job", "--name", "j", "--kind", "HEALTH_CHECK", "--commit"], tmp_path, monkeypatch, capsys)
    j = M.job_id("j")
    _cli(["enable", "--job", j, "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["run", "--job", j, "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "SUCCESS" in out


def test_cli_schedule_and_due(tmp_path, monkeypatch, capsys):
    _cli(["job", "--name", "j", "--kind", "HEALTH_CHECK", "--commit"], tmp_path, monkeypatch, capsys)
    j = M.job_id("j")
    _cli(["schedule", "--job", j, "--cadence", "HOURLY", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["due", "--tick", "1"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert j in out


def test_cli_disable(tmp_path, monkeypatch, capsys):
    _cli(["job", "--name", "j", "--kind", "HEALTH_CHECK", "--commit"], tmp_path, monkeypatch, capsys)
    j = M.job_id("j")
    _cli(["enable", "--job", j, "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["disable", "--job", j, "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0


def test_cli_log(tmp_path, monkeypatch, capsys):
    _cli(["job", "--name", "j", "--kind", "HEALTH_CHECK", "--commit"], tmp_path, monkeypatch, capsys)
    j = M.job_id("j")
    rc, out = _cli(["log", "--job", j, "--level", "INFO", "--message", "hi", "--commit"],
                   tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "LAL:" in out


def test_cli_report(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["report"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "job_count" in out


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["summary"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "run_count" in out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _cli(["job", "--name", "j", "--kind", "HEALTH_CHECK", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["verify"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert '"ok": true' in out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["replay"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "deterministic" in out
