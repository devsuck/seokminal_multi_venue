"""AI 업그레이드 5종 — 감시견·에이전트 게이트·코드 감사·pull 큐."""
import json

import pytest

from jarvis import watchdog
from jarvis.execution.agent_gate import enforce_paper, validation_of
from jarvis.redteam.code_audit import audit_file
from research.data import pull_queue


@pytest.fixture
def isolated_state(tmp_path, monkeypatch):
    """jarvis state 파일들을 tmp로 격리(실 상태 오염 방지)."""
    monkeypatch.setattr("jarvis.config.STATE_DIR", str(tmp_path))
    return tmp_path


# ── 감시견 ──────────────────────────────────────────────────────────────

def test_watchdog_first_observation_is_baseline_not_event(isolated_state):
    ev = watchdog.observe({"edge": "no_oos_yet", "arm": "WAIT", "oos_months": 0})
    assert ev == []  # 첫 관측 = baseline, 스팸 없음


def test_watchdog_change_emits_event_and_critical_kill(isolated_state):
    watchdog.observe({"arm": "WAIT"})
    ev = watchdog.observe({"arm": "KILL"})
    assert len(ev) == 1 and ev[0]["severity"] == "critical"
    assert watchdog.has_critical()


def test_watchdog_no_change_no_event(isolated_state):
    watchdog.observe({"edge": "accumulating"})
    assert watchdog.observe({"edge": "accumulating"}) == []


def test_watchdog_none_values_ignored(isolated_state):
    watchdog.observe({"edge": "accumulating"})
    # 워밍 전 None은 비교 제외 — 상태 잊지 않음
    assert watchdog.observe({"edge": None}) == []
    assert watchdog.observe({"edge": "accumulating"}) == []


def test_watchdog_oos_progress_event(isolated_state):
    watchdog.observe({"oos_months": 0})
    ev = watchdog.observe({"oos_months": 1})
    assert len(ev) == 1 and "카운트다운" in ev[0]["msg"]


# ── 에이전트 registry 게이트 ────────────────────────────────────────────

def test_gate_unvalidated_live_forced_to_paper():
    agent = {"paper": False, "profile": {"name": "hl_daytrade"}}
    paper, note = enforce_paper(agent)
    assert paper is True and note and "차단" in note


def test_gate_paper_agent_passes_silently():
    paper, note = enforce_paper({"paper": True, "profile": {"name": "swing"}})
    assert paper is True and note is None


def test_gate_validation_reason_exposed():
    v = validation_of({"profile": {"name": "daytrade"}})
    assert v["validated"] is False and "미등록" in v["reason"]


# ── 코드 감사 ───────────────────────────────────────────────────────────

def test_code_audit_catches_negative_shift(tmp_path):
    p = tmp_path / "run_leak.py"
    p.write_text("sig = px.pct_change().shift(-1)\n")
    f = audit_file(str(p))
    assert any(x["severity"] == "high" for x in f)


def test_code_audit_flags_missing_random_baseline(tmp_path):
    p = tmp_path / "run_nobaseline.py"
    p.write_text("print('study without baseline')\n")
    f = audit_file(str(p))
    assert any("베이스라인" in x["why"] for x in f)


def test_code_audit_clean_file_with_baseline(tmp_path):
    p = tmp_path / "run_clean.py"
    p.write_text("from research.validation.baselines import empirical_p_value\n")
    assert audit_file(str(p)) == []


# ── pull 큐 ─────────────────────────────────────────────────────────────

def test_pull_queue_enqueue_and_status(isolated_state):
    j = pull_queue.enqueue("ksd_lending", {"families": ["buyback"]}, follow_up="run_buyback_x_lending")
    s = pull_queue.status()
    assert s["pending"] == 1 and s["recent"][-1]["id"] == j["id"]


def test_pull_queue_unknown_kind_errors(isolated_state):
    pull_queue.enqueue("nope", {})
    job = pull_queue.tick()
    assert job is not None
    # worker 스레드 종료 대기
    t = pull_queue._running["thread"]
    t.join(timeout=10)
    rec = pull_queue.status()["recent"][-1]
    assert rec["status"] == "error" and "unknown" in json.dumps(rec["result"])
