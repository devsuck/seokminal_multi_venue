"""파이프라인 층간 불일치 감시 테스트.

이 감시가 2026-07-13에 있었다면 auto_fac_* 3건 오탈락을 당일 잡았다.
핵심 요구사항 두 가지: (1) 진짜 불일치를 잡을 것, (2) 정상 rejected를 오탐하지
말 것 — 오탐이 쌓이면 감시가 무시되고, 그게 이 버그가 5주간 숨은 이유다.
"""
from __future__ import annotations

import json

import pytest

import research.check_pipeline_consistency as cpc
from jarvis.registry import Status, StrategyRegistry
from tests.jarvis_state_isolation import isolate_jarvis_state

QUALIFIED = {"hypothesis_id": "auto_fac_demo", "status": "candidate", "n": 82,
             "net": 0.042, "percentile": 100.0, "p": 0.0033,
             "wf_first": 0.043, "wf_second": 0.041, "redteam": "CLEARED"}


@pytest.fixture
def _isolate(tmp_path, monkeypatch):
    """registry만 돌리면 `require()`가 실제 감사원장에 쓴다 — 전면 격리."""
    return isolate_jarvis_state(monkeypatch, tmp_path)


def _stub_experiments(monkeypatch, rows):
    monkeypatch.setattr(cpc, "load_all", lambda: rows)


def _promote_then(reg, sid, final_status, reason, evidence=None):
    """draft→…→final_status 경로를 밟아 원장에 이벤트를 남긴다."""
    reg.register(sid, sid, {"k": 1})
    for status in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED):
        reg.transition(sid, status, "setup")
    reg.transition(sid, final_status, reason, evidence=evidence or {})


def test_flags_candidate_rejected_by_registry(_isolate, monkeypatch):
    _stub_experiments(monkeypatch, [QUALIFIED])
    reg = StrategyRegistry()
    _promote_then(reg, "auto_fac_demo", Status.REJECTED, "critic: rejected",
                  {"critic_flags": []})

    issues = cpc.find_inconsistencies()
    kinds = {i["kind"] for i in issues}
    assert "verdict_conflict" in kinds
    assert "reasonless_rejection" in kinds


def test_no_false_positive_on_seeded_rejection(_isolate, monkeypatch):
    """`seed:` 전이는 reason 문자열이 사유 — 근거 없음으로 신고하면 안 된다."""
    _stub_experiments(monkeypatch, [])
    reg = StrategyRegistry()
    _promote_then(reg, "old_reject_v1", Status.REJECTED,
                  "seed: REJECT — net 음수(비용 후 사망)")

    assert cpc.find_inconsistencies() == []


def test_no_false_positive_when_flags_present(_isolate, monkeypatch):
    _stub_experiments(monkeypatch, [])
    reg = StrategyRegistry()
    _promote_then(reg, "flagged_v1", Status.REJECTED, "critic: rejected",
                  {"critic_flags": ["net_non_positive"]})

    assert cpc.find_inconsistencies() == []


def test_candidate_agreeing_with_registry_is_clean(_isolate, monkeypatch):
    _stub_experiments(monkeypatch, [QUALIFIED])
    reg = StrategyRegistry()
    _promote_then(reg, "auto_fac_demo", Status.WATCHLIST, "critic: watchlist")

    assert cpc.find_inconsistencies() == []


def test_candidate_missing_from_registry_is_stale(_isolate, monkeypatch):
    _stub_experiments(monkeypatch, [QUALIFIED])

    issues = cpc.find_inconsistencies()
    assert [i["kind"] for i in issues] == ["stale_candidate"]


def test_non_candidate_rows_ignored(_isolate, monkeypatch):
    _stub_experiments(monkeypatch, [dict(QUALIFIED, status="rejected", verdict="REJECT_BH")])

    assert cpc.find_inconsistencies() == []


def test_exit_code_signals_inconsistency(_isolate, monkeypatch, capsys):
    """크론/CI가 알람 걸 수 있게 종료코드가 1이어야 한다."""
    _stub_experiments(monkeypatch, [QUALIFIED])
    assert cpc.main([]) == 1
    _stub_experiments(monkeypatch, [])
    assert cpc.main([]) == 0
    assert "불일치 없음" in capsys.readouterr().out


def test_json_output_is_parseable(_isolate, monkeypatch, capsys):
    _stub_experiments(monkeypatch, [QUALIFIED])
    cpc.main(["--json"])
    parsed = json.loads(capsys.readouterr().out)
    assert parsed and parsed[0]["hypothesis_id"] == "auto_fac_demo"
