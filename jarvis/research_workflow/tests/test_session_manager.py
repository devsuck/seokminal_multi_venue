"""Research Session Manager(P66) 테스트 — 생성/재개/일시정지/보관·상태추적·"어제 연구 계속"·해시체인.
"""
from __future__ import annotations

import pytest

from jarvis.research_workflow import ledger
from jarvis.research_workflow.models import SESS_ACTIVE, SESS_ARCHIVED, SESS_PAUSED
from jarvis.research_workflow.session_manager import ResearchSessionManager
from jarvis.research_workflow.verify import verify_chain

NOW = "2026-01-01T00:00:00Z"


@pytest.fixture()
def mgr(tmp_path, monkeypatch):
    state = tmp_path / "_state"
    state.mkdir()
    monkeypatch.setattr(ledger, "state_path", lambda n: str(state / n))
    return ResearchSessionManager()


def test_create_session(mgr):
    st = mgr.create_session("momentum research", now=NOW, commit=True)
    assert st.state == SESS_ACTIVE
    assert "momentum research" in st.goals


def test_track_progress(mgr):
    st = mgr.create_session("momentum research", now=NOW, commit=True)
    sid = st.session_id
    mgr.update_progress(sid, progress=["ran ema backtest"], pending=["validate OOS"],
                        completed_experiments=["exp_ema_1"], lessons=["cost matters"],
                        open_questions=["does it hold in 2022 regime?"], now=NOW, commit=True)
    s = mgr.state(sid)
    assert "ran ema backtest" in s.progress
    assert "validate OOS" in s.pending_work
    assert "exp_ema_1" in s.completed_experiments
    assert "cost matters" in s.lessons_learned
    assert "does it hold in 2022 regime?" in s.open_questions


def test_completed_removed_from_pending(mgr):
    sid = mgr.create_session("g", now=NOW, commit=True).session_id
    mgr.update_progress(sid, pending=["exp_A"], now=NOW, commit=True)
    mgr.update_progress(sid, completed_experiments=["exp_A"], now=NOW, commit=True)
    s = mgr.state(sid)
    assert "exp_A" in s.completed_experiments
    assert "exp_A" not in s.pending_work


def test_resolved_questions_removed(mgr):
    sid = mgr.create_session("g", now=NOW, commit=True).session_id
    mgr.update_progress(sid, open_questions=["q1", "q2"], now=NOW, commit=True)
    mgr.update_progress(sid, resolved_questions=["q1"], now=NOW, commit=True)
    s = mgr.state(sid)
    assert "q1" not in s.open_questions and "q2" in s.open_questions


def test_pause_and_resume_continue_yesterday(mgr):
    sid = mgr.create_session("momentum research", now=NOW, commit=True).session_id
    mgr.update_progress(sid, pending=["validate OOS"], lessons=["cost matters"],
                        now=NOW, commit=True)
    mgr.pause_session(sid, now=NOW, commit=True)
    assert mgr.state(sid).state == SESS_PAUSED
    # "어제 하던 연구 계속" — 저장된 상태로 재개
    resumed = mgr.resume_session(sid, now=NOW, commit=True)
    assert resumed.state == SESS_ACTIVE
    assert "validate OOS" in resumed.pending_work     # 대기작업 보존
    assert "cost matters" in resumed.lessons_learned  # 교훈 보존


def test_archive(mgr):
    sid = mgr.create_session("g", now=NOW, commit=True).session_id
    mgr.archive_session(sid, now=NOW, commit=True)
    assert mgr.state(sid).state == SESS_ARCHIVED


def test_list_sessions(mgr):
    mgr.create_session("g1", now=NOW, commit=True)
    mgr.create_session("g2", now=NOW, commit=True)
    assert len(mgr.list_sessions()) == 2


def test_hash_chain_valid(mgr):
    sid = mgr.create_session("g", now=NOW, commit=True).session_id
    mgr.update_progress(sid, progress=["x"], now=NOW, commit=True)
    mgr.pause_session(sid, now=NOW, commit=True)
    assert verify_chain()["ok"]


def test_dry_run_no_write(mgr, tmp_path):
    mgr.create_session("g", now=NOW, commit=False)
    assert ledger.read_sessions() == []


def test_advisory(mgr):
    st = mgr.create_session("g", now=NOW, commit=True)
    assert st.is_advisory is True
