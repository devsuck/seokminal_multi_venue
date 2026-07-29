"""Local Research Runtime(P42) 테스트 — 환경검증·모듈발견·헬스·start/restart/stop·상태·로그·검증·재현·안전.

**로컬 전용, 거래·집행 없음.** lrt_ 원장은 tmp 로 격리(state_path 몽키패치). boot()/status() 는 주입(격리·통합).
"""
from __future__ import annotations

import ast
import json
import pathlib

import pytest

from jarvis.local_runtime import ledger
from jarvis.local_runtime import models as M
from jarvis.local_runtime.engine import LocalRuntimeEngine
from jarvis.local_runtime.verify import event_integrity, replay, verify_chain

NOW = "2026-01-01T00:00:00Z"
SRC = pathlib.Path(__file__).resolve().parent.parent
MODEL_LEAK_TOKEN = "claude" + "-" + "opus"


def _fake_status():
    return {"system": "Jarvis Quant OS", "autonomy_level": 5,
            "autonomy_name": "Human-approved live proposal", "live_execution": "disabled"}


@pytest.fixture()
def eng(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    calls = []

    def fake_boot():
        calls.append(1)
        return {"lessons_seeded": 1, "strategies_seeded": 2, "auto_deployed": 0}

    e = LocalRuntimeEngine(boot_fn=fake_boot, status_fn=_fake_status)
    e._test_boot_calls = calls
    return e


# ──────────────────────── models 헬퍼 ────────────────────────
def test_worst_status_empty():
    assert M.worst_status([]) == M.OK


@pytest.mark.parametrize("statuses,expected", [
    ([M.OK, M.OK], M.OK),
    ([M.OK, M.WARN], M.WARN),
    ([M.WARN, M.FAIL], M.FAIL),
    ([M.OK, M.FAIL, M.WARN], M.FAIL),
    ([M.WARN], M.WARN),
])
def test_worst_status(statuses, expected):
    assert M.worst_status(statuses) == expected


def test_event_id_prefix():
    assert M.event_id("STARTUP", 0).startswith("LRTE:")


def test_log_id_prefix():
    assert M.log_id(0).startswith("LRTL:")


def test_ids_deterministic():
    assert M.event_id("STARTUP", 0) == M.event_id("STARTUP", 0)
    assert M.event_id("STARTUP", 0) != M.event_id("STARTUP", 1)


def test_content_hash_excludes_meta():
    a = {"x": 1, "previous_hash": "p", "record_hash": "r"}
    b = {"x": 1, "previous_hash": "Q", "record_hash": "Z"}
    assert M.content_hash(a) == M.content_hash(b)


@pytest.mark.parametrize("verb", ["EXECUTE", "DEPLOY", "TRADE", "ALLOCATE", "APPROVE",
                                  "PLACE_ORDER", "ACTIVATE_LIVE", "APPROVE_FOR_TRADING"])
def test_forbidden_verbs(verb):
    assert M.is_forbidden_verb(verb)


def test_not_forbidden_verbs():
    for v in ("analyze", "discover", "validate", "start", "status"):
        assert not M.is_forbidden_verb(v)


def test_runtime_states_defined():
    assert set(M.RUNTIME_STATES) == {"RUNNING", "STOPPED", "UNKNOWN"}


def test_event_kinds_defined():
    assert set(M.EVENT_KINDS) == {"STARTUP", "RESTART", "STOP", "HEALTH"}


# ──────────────────────── 환경 검증 ────────────────────────
def test_validate_environment(eng):
    checks = eng.validate_environment()
    names = {c.name for c in checks}
    assert {"python_version", "state_dir_writable", "autonomy_level",
            "live_execution_disabled"} <= names


def test_env_python_ok(eng):
    py = next(c for c in eng.validate_environment() if c.name == "python_version")
    assert py.status == M.OK


def test_env_state_dir_writable(eng):
    c = next(c for c in eng.validate_environment() if c.name == "state_dir_writable")
    assert c.status == M.OK


def test_env_autonomy_valid(eng):
    c = next(c for c in eng.validate_environment() if c.name == "autonomy_level")
    assert c.status == M.OK


def test_env_status_ok_or_warn(eng):
    assert eng.environment_status() in (M.OK, M.WARN)


def test_env_all_statuses_valid(eng):
    assert all(c.status in M.CHECK_STATES for c in eng.validate_environment())


# ──────────────────────── 모듈 발견(P41 통합) ────────────────────────
def test_discover_modules(eng):
    d = eng.discover_modules()
    assert d.module_count >= 100
    assert "Research" in d.category_counts


def test_discover_categories_nonempty(eng):
    d = eng.discover_modules()
    assert d.category_counts["Research"] > 0
    assert sum(d.category_counts.values()) == d.module_count


def test_discover_includes_new_packages(eng):
    d = eng.discover_modules()
    allmods = [m for members in d.categories.values() for m in members]
    assert "local_runtime" in allmods
    assert "integration_audit" in allmods


def test_discover_deterministic(eng):
    assert eng.discover_modules().to_dict() == eng.discover_modules().to_dict()


def test_discover_categories_sorted(eng):
    d = eng.discover_modules()
    for members in d.categories.values():
        assert members == sorted(members)


# ──────────────────────── 헬스 체크 ────────────────────────
def test_health_checks(eng):
    checks = eng.health_checks()
    names = {c.name for c in checks}
    assert {"state_dir", "config", "module_discovery", "live_execution_gate"} <= names


def test_health_module_discovery_ok(eng):
    c = next(c for c in eng.health_checks() if c.name == "module_discovery")
    assert c.status == M.OK


def test_health_status_ok_or_warn(eng):
    assert eng.health_status() in (M.OK, M.WARN)


def test_health_live_gate(eng):
    c = next(c for c in eng.health_checks() if c.name == "live_execution_gate")
    assert c.status in (M.OK, M.WARN)


def test_health_all_statuses_valid(eng):
    assert all(c.status in M.CHECK_STATES for c in eng.health_checks())


# ──────────────────────── start / restart / stop ────────────────────────
def test_start_no_boot_by_default(eng):
    st = eng.start(NOW, commit=True)
    assert st.boot_ran is False
    assert eng._test_boot_calls == []   # boot() 호출 안 함(기존 원장 불변)


def test_start_records_event(eng):
    eng.start(NOW, commit=True)
    evs = ledger.read_events()
    assert len(evs) == 1
    assert evs[0]["kind"] == M.EV_STARTUP


def test_start_records_log(eng):
    eng.start(NOW, commit=True)
    assert len(ledger.read_logs()) == 1


def test_start_no_commit_no_write(eng):
    eng.start(NOW, commit=False)
    assert ledger.read_events() == []
    assert ledger.read_logs() == []


def test_start_with_boot_calls_boot(eng):
    st = eng.start(NOW, run_boot=True, commit=True)
    assert st.boot_ran is True
    assert eng._test_boot_calls == [1]


def test_start_runtime_state_running(eng):
    eng.start(NOW, commit=True)
    assert eng.runtime_state() == M.RT_RUNNING


def test_restart_records_event(eng):
    eng.start(NOW, commit=True)
    eng.restart(NOW, commit=True)
    kinds = [e["kind"] for e in ledger.read_events()]
    assert M.EV_RESTART in kinds
    assert eng.runtime_state() == M.RT_RUNNING


def test_restart_with_boot(eng):
    eng.restart(NOW, run_boot=True, commit=True)
    assert eng._test_boot_calls == [1]


def test_stop_marker(eng):
    eng.start(NOW, commit=True)
    eng.stop(NOW, commit=True)
    assert eng.runtime_state() == M.RT_STOPPED


def test_start_after_stop_is_running(eng):
    eng.start(NOW, commit=True)
    eng.stop(NOW, commit=True)
    eng.restart(NOW, commit=True)
    assert eng.runtime_state() == M.RT_RUNNING


def test_runtime_state_unknown_initial(eng):
    assert eng.runtime_state() == M.RT_UNKNOWN


def test_record_health_event(eng):
    eng.record_health(NOW, commit=True)
    evs = ledger.read_events()
    assert evs[-1]["kind"] == M.EV_HEALTH


def test_health_event_preserves_life_state(eng):
    eng.start(NOW, commit=True)
    eng.record_health(NOW, commit=True)
    assert eng.runtime_state() == M.RT_RUNNING


def test_last_event(eng):
    eng.start(NOW, commit=True)
    assert eng.last_event()["kind"] == M.EV_STARTUP


def test_multiple_startups_unique_ids(eng):
    eng.start(NOW, commit=True)
    eng.start(NOW, commit=True)
    ids = [e["event_id"] for e in ledger.read_events() if e["kind"] == M.EV_STARTUP]
    assert len(ids) == len(set(ids)) == 2


# ──────────────────────── status ────────────────────────
def test_status_integrates_base(eng):
    st = eng.status(NOW)
    assert st.system == "Jarvis Quant OS"
    assert st.autonomy_level == 5
    assert st.live_execution == "disabled"


def test_status_module_count(eng):
    st = eng.status(NOW)
    assert st.module_count >= 100


def test_status_health_and_env(eng):
    st = eng.status(NOW)
    assert st.health_status in M.CHECK_STATES
    assert st.env_status in M.CHECK_STATES


def test_status_checks_populated(eng):
    st = eng.status(NOW)
    assert len(st.checks) > 0


def test_status_deterministic(eng):
    assert eng.status(NOW).to_dict() == eng.status(NOW).to_dict()


# ──────────────────────── 로그 ────────────────────────
def test_record_log(eng):
    lg = eng.record_log("INFO", "test", "hello", NOW, commit=True)
    assert lg.log_id.startswith("LRTL:")
    assert len(eng.logs()) == 1


def test_record_log_bad_level(eng):
    with pytest.raises(ValueError):
        eng.record_log("NONSENSE", "s", "m", NOW, commit=True)


@pytest.mark.parametrize("level", list(M.LOG_LEVELS))
def test_log_levels(eng, level):
    lg = eng.record_log(level, "s", "m", NOW, commit=True)
    assert lg.level == level


def test_logs_no_commit(eng):
    eng.record_log("INFO", "s", "m", NOW, commit=False)
    assert eng.logs() == []


# ──────────────────────── 해시체인·검증 ────────────────────────
def test_verify_chain_clean(eng):
    eng.start(NOW, commit=True)
    eng.record_health(NOW, commit=True)
    eng.stop(NOW, commit=True)
    res = verify_chain()
    assert res["ok"]
    assert res["n"] > 0


def test_verify_empty(eng):
    assert verify_chain()["ok"]


def test_hash_chain_links(eng):
    eng.start(NOW, commit=True)
    eng.restart(NOW, commit=True)
    evs = ledger.read_events()
    assert evs[0]["previous_hash"] == M.GENESIS
    assert evs[1]["previous_hash"] == evs[0]["record_hash"]


def test_tamper_detected(eng):
    eng.start(NOW, commit=True)
    p = pathlib.Path(ledger.state_path("lrt_events.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["summary"] = "TAMPERED"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_broken_chain_detected(eng):
    eng.start(NOW, commit=True)
    eng.restart(NOW, commit=True)
    p = pathlib.Path(ledger.state_path("lrt_events.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[1]["previous_hash"] = "sha256:deadbeefdeadbeef"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not verify_chain()["ok"]


def test_event_integrity_bad_kind(eng):
    eng.start(NOW, commit=True)
    p = pathlib.Path(ledger.state_path("lrt_events.jsonl"))
    rows = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
    rows[0]["kind"] = "NONSENSE"
    p.write_text("\n".join(json.dumps(r) for r in rows) + "\n")
    assert not event_integrity()["ok"]


def test_event_integrity_clean(eng):
    eng.start(NOW, commit=True)
    assert event_integrity()["ok"]


# ──────────────────────── 재현 ────────────────────────
def test_replay_deterministic(eng):
    eng.start(NOW, commit=True)
    r = replay(eng, NOW)
    assert r["deterministic"]
    assert r["module_count"] >= 100


def test_summary(eng):
    eng.start(NOW, commit=True)
    eng.record_log("INFO", "s", "m", NOW, commit=True)
    s = eng.summary(NOW)
    assert s.event_count == 1
    assert s.log_count >= 1
    assert s.last_event_kind == M.EV_STARTUP


# ──────────────────────── 원장 접두사·격리 ────────────────────────
def test_two_ledgers():
    assert len(ledger.ALL_LEDGERS) == 2


def test_ledger_prefix():
    for fname, _ in ledger.ALL_LEDGERS:
        assert fname.startswith("lrt_")


def test_no_stray_state_files(eng):
    eng.start(NOW, commit=True)
    written = {pathlib.Path(ledger.state_path(f)).name for f, _ in ledger.ALL_LEDGERS
               if pathlib.Path(ledger.state_path(f)).exists()}
    assert all(w.startswith("lrt_") for w in written)


# ──────────────────────── 안전 스캔 ────────────────────────
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
           "execute_trade", "allocate_capital", "deploy_strategy", "approve_for_trading")
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            assert node.name not in bad, node.name


@pytest.mark.parametrize("path", _SRC_FILES)
def test_no_model_id_leak(path):
    assert MODEL_LEAK_TOKEN not in open(path).read().lower()


def test_engine_no_execution_methods(eng):
    for m in ("execute", "trade", "deploy", "allocate", "approve"):
        assert not hasattr(eng, m)


def test_runtime_never_enables_live(eng):
    # 런타임은 live 실행을 켜지 않는다 — status 의 live_execution 은 주입된 base 를 그대로 반영
    assert eng.status(NOW).live_execution == "disabled"


# ──────────────────────── CLI ────────────────────────
def _cli(argv, tmp_path, monkeypatch, capsys):
    state = tmp_path / "_state"
    state.mkdir(exist_ok=True)
    monkeypatch.setattr(ledger, "state_path", lambda name: str(state / name))
    from jarvis.local_runtime import __main__ as cli
    rc = cli.main(argv)
    return rc, capsys.readouterr().out


def test_cli_start(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "runtime_state" in out


def test_cli_status(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["status"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "module_count" in out


def test_cli_health(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["health"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "checks" in out


def test_cli_validate(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["validate"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "python_version" in out


def test_cli_discover(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["discover"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "module_count" in out


def test_cli_restart(tmp_path, monkeypatch, capsys):
    _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["restart", "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0


def test_cli_stop(tmp_path, monkeypatch, capsys):
    _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["stop", "--commit"], tmp_path, monkeypatch, capsys)
    assert rc == 0


def test_cli_logs(tmp_path, monkeypatch, capsys):
    _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["logs"], tmp_path, monkeypatch, capsys)
    assert rc == 0


def test_cli_events(tmp_path, monkeypatch, capsys):
    _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["events"], tmp_path, monkeypatch, capsys)
    assert rc == 0


def test_cli_summary(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["summary"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "runtime_state" in out


def test_cli_verify(tmp_path, monkeypatch, capsys):
    _cli(["start", "--commit"], tmp_path, monkeypatch, capsys)
    rc, out = _cli(["verify"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert '"ok": true' in out


def test_cli_replay(tmp_path, monkeypatch, capsys):
    rc, out = _cli(["replay"], tmp_path, monkeypatch, capsys)
    assert rc == 0
    assert "deterministic" in out
