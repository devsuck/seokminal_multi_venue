"""Console API 자본 청구 엔드포인트 스모크 테스트.

test_console_api.py와 동일하게 함수 직접 호출(TestClient 불필요). state_path만
tmp_path로 격리(실 원장 오염 방지) — 나머지는 test_capital_claims.py의 fixture 그대로.

주의: 5개 신규 엔드포인트 모두 Principal을 요청에서 안 받고 내부 고정(HUMAN_ADMIN /
LIVE_PROPOSAL_AGENT) — 기존 세션/X-Api-Key 미들웨어가 이미 호출자를 게이트하므로
API 레벨에서 별도 권한거부 경로가 없다(설계상 도달 불가). 대신 비즈니스 레벨 거부
(미등록 전략, 존재하지 않는 claim_id)를 오류 경로 테스트로 검증한다.

설계: docs/superpowers/specs/2026-09-11-capital-claim-model-design.md
"""
from __future__ import annotations

import importlib
import os

import pytest

import api_server.ai_portfolio as ap
import api_server.console_api as c
from jarvis.registry import Status, StrategyRegistry


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    def sp(name):
        return os.path.join(tmp_path, name)
    for mod in ("jarvis.audit.log", "jarvis.registry.lifecycle", "jarvis.execution.arm",
                "jarvis.execution.capital_envelope", "jarvis.execution.capital_claims"):
        monkeypatch.setattr(importlib.import_module(mod), "state_path", sp)
    monkeypatch.setattr(ap, "_STATE_PATH", str(tmp_path / "ai_portfolio_recs.jsonl"))
    return tmp_path


def _paper_active(sid="S1"):
    reg = StrategyRegistry()
    reg.register(sid, name=sid, config={"x": 1})
    for s in (Status.DATA_AUDIT_PASSED, Status.BACKTESTED, Status.WATCHLIST,
              Status.PAPER_CANDIDATE, Status.PAPER_ACTIVE):
        reg.transition(sid, s, "t")
    return reg


def test_get_envelope_defaults_zero():
    env = c.get_capital_envelope()
    assert env["pool_limit"] == 0.0


def test_set_envelope_happy_path():
    row = c.set_capital_envelope(pool_limit=1000, default_paper_limit=200,
                                  per_strategy_paper_limit_json='{"S1": 500}')
    assert row["pool_limit"] == 1000
    assert row["per_strategy_paper_limit"] == {"S1": 500}
    assert c.get_capital_envelope()["pool_limit"] == 1000


def test_set_envelope_bad_json_returns_error():
    row = c.set_capital_envelope(pool_limit=1000, per_strategy_paper_limit_json="not json")
    assert row["error"] == "invalid_request"


def test_submit_claim_happy_path_auto_approved():
    _paper_active("S1")
    c.set_capital_envelope(pool_limit=1000, default_paper_limit=500)
    row = c.submit_capital_claim("S1", requested_amount=300)
    assert row["status"] == "approved"
    assert row["allocated_capital"] == 300
    assert row["moves_real_capital"] is False


def test_submit_claim_not_registered_is_business_rejection():
    row = c.submit_capital_claim("NOPE", requested_amount=100)
    assert row["status"] == "rejected"
    assert row["reason"] == "not_registered"


def test_queue_and_decide_happy_path():
    _paper_active("S1")
    c.set_capital_envelope(pool_limit=100, default_paper_limit=100)
    queued = c.submit_capital_claim("S1", requested_amount=500)
    assert queued["status"] == "queued"
    q = c.capital_claim_queue()
    assert q["count"] == 1
    decided = c.decide_capital_claim(queued["claim_id"], approve=True, note="ok")
    assert decided["status"] == "approved"
    assert decided["allocated_capital"] == 500
    assert c.capital_claim_queue()["count"] == 0


def test_decide_unknown_claim_id_returns_error():
    row = c.decide_capital_claim("does-not-exist", approve=True)
    assert row["error"] == "invalid_request"


def test_claim_history_happy_path():
    _paper_active("S1")
    c.set_capital_envelope(pool_limit=1000, default_paper_limit=500)
    c.submit_capital_claim("S1", requested_amount=300)
    hist = c.capital_claim_history(strategy_id="S1")
    assert hist["count"] == 1
    assert hist["records"][0]["strategy_id"] == "S1"
