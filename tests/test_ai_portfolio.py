"""AI 포트폴리오 추천 코어 테스트. Claude CLI 실호출 절대 없음 — call_claude는 항상 monkeypatch."""
from __future__ import annotations

import json

import api_server.ai_portfolio as ap


CANDIDATES = [
    {"strategy_id": "s1", "status": "paper_active", "family": "momentum",
     "asset_class": "kr_equity", "evidence_grade": "STRONG"},
    {"strategy_id": "s2", "status": "paper_candidate", "family": "meanrev",
     "asset_class": "crypto", "evidence_grade": "MEDIUM"},
]


def _patch_consume(monkeypatch, candidates):
    monkeypatch.setattr(
        "jarvis.investment_os.consume_research",
        lambda **kw: {"candidates": candidates, "count": len(candidates)},
    )


def _patch_state_path(monkeypatch, tmp_path):
    monkeypatch.setattr(ap, "_STATE_PATH", str(tmp_path / "ai_portfolio_recs.jsonl"))


def test_generate_ai_recommendation_success(monkeypatch, tmp_path):
    # 캡(0.4)을 지키며 합=1.0을 만들려면 2개 전략으로는 수학적으로 불가능(둘 중 하나는 항상 >=0.5)
    # 이므로 성공 케이스는 전략 3개로 검증한다.
    candidates = CANDIDATES + [
        {"strategy_id": "s3", "status": "paper_active", "family": "carry",
         "asset_class": "us_equity", "evidence_grade": "STRONG"},
    ]
    _patch_consume(monkeypatch, candidates)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    raw = json.dumps({
        "weights": {"s1": 0.4, "s2": 0.3, "s3": 0.3},
        "per_strategy_note": {"s1": "강한 증거", "s2": "중간 증거", "s3": "분산"},
        "overall_rationale": "3개 전략으로 분산, 캡 준수",
    })
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: raw)

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is False
    assert abs(sum(rec["weights"].values()) - 1.0) < 1e-6
    assert max(rec["weights"].values()) <= 0.4 + 1e-6
    assert rec["is_advisory"] is True
    assert rec["is_decision"] is False
    assert rec["requires_human_review"] is True


def test_generate_ai_recommendation_parse_failure_falls_back(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: "not json at all")

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is True
    assert set(rec["weights"].keys()) <= {"s1", "s2"}


def test_generate_ai_recommendation_cap_violation_falls_back(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: "claude")
    raw = json.dumps({"weights": {"s1": 0.9, "s2": 0.1}})
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: raw)

    rec = ap.generate_ai_recommendation()

    assert rec["fallback_used"] is True


def test_generate_ai_recommendation_no_candidates(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, [])
    _patch_state_path(monkeypatch, tmp_path)

    rec = ap.generate_ai_recommendation()

    assert rec["candidates_count"] == 0
    assert rec["fallback_used"] is False
    assert rec["weights"] == {}


def test_generate_ai_recommendation_no_cli_skips_call(monkeypatch, tmp_path):
    _patch_consume(monkeypatch, CANDIDATES)
    _patch_state_path(monkeypatch, tmp_path)
    monkeypatch.setattr(ap, "claude_bin", lambda: None)
    called = []
    monkeypatch.setattr(ap, "call_claude", lambda *a, **kw: called.append(1) or "")

    rec = ap.generate_ai_recommendation()

    assert called == []
    assert rec["fallback_used"] is True


def test_history_and_latest_round_trip(monkeypatch, tmp_path):
    _patch_state_path(monkeypatch, tmp_path)
    ap._append({"timestamp": "t1", "weights": {"s1": 1.0}})
    ap._append({"timestamp": "t2", "weights": {"s2": 1.0}})

    assert ap.latest_recommendation()["timestamp"] == "t2"
    hist = ap.history(limit=10)
    assert [r["timestamp"] for r in hist] == ["t2", "t1"]
