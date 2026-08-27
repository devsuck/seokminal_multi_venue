"""Lv5 Claude CLI 호출 잠금 + 리뷰 실패 관측 회귀 테스트.

배경: 3-Phase 리뷰 프롬프트에는 시장 컨텍스트·종목명·과거 메모 등 외부에서 흘러든
문자열이 그대로 삽입된다. 과거엔 이 호출이
`--dangerously-skip-permissions --permission-mode bypassPermissions`로 나갔는데,
그러면 그 문자열이 브로커 자격증명을 들고 있는 트레이딩 호스트에서 임의 명령을
실행시키는 주입 경로가 된다. `--permission-mode`만으로는 못 막는다(print 모드에서도
Bash가 실제 실행되는 걸 확인함) — 도구 자체를 빼야 한다.
"""
from __future__ import annotations

import subprocess

import pytest

from api_server import lv5_agent


class _Proc:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout, self.stderr, self.returncode = stdout, stderr, returncode


@pytest.fixture
def captured(monkeypatch):
    calls: list[list[str]] = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return _Proc(stdout="응답")

    monkeypatch.setattr(subprocess, "run", fake_run)
    return calls


# ── CLI 잠금 ────────────────────────────────────────────────────────────────

def test_never_passes_permission_bypass_flags(captured):
    lv5_agent._call_claude("/bin/claude", "분석해줘")
    argv = captured[0]

    assert "--dangerously-skip-permissions" not in argv
    assert "bypassPermissions" not in argv
    assert "--permission-mode" not in argv


def test_disallows_every_tool_that_can_touch_the_host(captured):
    lv5_agent._call_claude("/bin/claude", "분석해줘")
    argv = captured[0]

    assert "--disallowed-tools" in argv
    for tool in ("Bash", "Edit", "Write", "Read", "WebFetch"):
        assert tool in argv


def test_prompt_survives_the_variadic_tool_list(captured):
    """`--`가 없으면 가변인자 목록이 프롬프트를 삼켜 CLI가 입력 없음으로 죽는다."""
    lv5_agent._call_claude("/bin/claude", "분석해줘")
    argv = captured[0]

    assert argv[-1] == "분석해줘"
    assert argv[-2] == "--"


def test_returns_stdout_on_success(captured):
    assert lv5_agent._call_claude("/bin/claude", "분석해줘") == "응답"


# ── 호출 실패 관측 ──────────────────────────────────────────────────────────

def test_nonzero_exit_returns_empty_not_partial_stdout(monkeypatch):
    """종료코드를 안 보면 CLI가 죽어도 부분 출력이 정상 응답처럼 흘러간다."""
    monkeypatch.setattr(subprocess, "run",
                        lambda argv, **kw: _Proc(stdout="쓰레기", stderr="boom", returncode=1))
    assert lv5_agent._call_claude("/bin/claude", "분석해줘") == ""


def test_exception_returns_empty(monkeypatch):
    def boom(argv, **kw):
        raise subprocess.TimeoutExpired(cmd="claude", timeout=90)

    monkeypatch.setattr(subprocess, "run", boom)
    assert lv5_agent._call_claude("/bin/claude", "분석해줘") == ""


# ── 리뷰 실패 관측 ──────────────────────────────────────────────────────────

def test_failed_review_is_visible_in_status_note():
    """데몬 스레드 예외를 로그로만 흘리면 '리뷰 안 돌았음'과 구분이 안 된다."""
    agent = "test_failed_review"
    lv5_agent._set_cache(agent, {
        "strategy_note": "노트",
        "last_review_ok": False,
        "last_review_error": "ZeroDivisionError: division by zero",
    })

    *_, note = lv5_agent.apply_cached_strategy(agent, 60, 0.1, [])
    assert "직전 리뷰 실패" in note
    assert "ZeroDivisionError" in note


def test_failed_review_exposed_to_frontend():
    agent = "test_failed_review_api"
    lv5_agent._set_cache(agent, {"last_review_ok": False, "last_review_error": "boom"})

    status = lv5_agent.get_review_status(agent)
    assert status["last_review_ok"] is False
    assert status["last_review_error"] == "boom"


def test_successful_review_shows_timestamp_not_error():
    agent = "test_ok_review"
    lv5_agent._set_cache(agent, {
        "strategy_note": "노트", "last_review_ok": True,
        "last_review_error": None, "review_ts": "2026-08-27T10:00:00Z",
    })

    *_, note = lv5_agent.apply_cached_strategy(agent, 60, 0.1, [])
    assert "리뷰 실패" not in note
    assert "2026-08-27T10:00:00Z" in note
