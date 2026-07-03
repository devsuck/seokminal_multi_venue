"""Auto-Research 엔진 — latest_bh_survivor 리더 + classify 통합."""
from __future__ import annotations

import json

from research.autoresearch import engine


def test_latest_bh_survivor_reads_leaderboard(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({
        "leaderboard": [
            {"cid": "ev_buyback", "bh_survivor": True},
            {"cid": "ev_spinoff", "bh_survivor": False},
        ]
    }), encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is True
    assert engine.latest_bh_survivor("spinoff") is False


def test_latest_bh_survivor_missing_returns_none(tmp_path, monkeypatch):
    monkeypatch.setattr(engine, "STATUS", str(tmp_path / "nope.json"))
    assert engine.latest_bh_survivor("buyback") is None


def test_latest_bh_survivor_family_absent_returns_none(tmp_path, monkeypatch):
    status = tmp_path / "status.json"
    status.write_text(json.dumps({"leaderboard": [{"cid": "ev_other", "bh_survivor": True}]}),
                      encoding="utf-8")
    monkeypatch.setattr(engine, "STATUS", str(status))
    assert engine.latest_bh_survivor("buyback") is None


def test_run_batch_uses_classify_for_verdicts(monkeypatch, tmp_path):
    """run_batch가 classify 경유 — bh 생존+레드팀 CLEARED+robust면 CANDIDATE,
    wf 음수면 WATCHLIST로 강등(새 강건성 게이트)."""
    from research.scanner import verdict as V

    # 결정 로직만 검증: collect_candidates·permutation을 가짜로 대체
    class _C:
        cid = "ev_fake"; category = "event_family"; thesis = "t"; direction = "bullish"
        meta = {"fam_id": "fake", "n": 100}
        def run(self):
            return {"n": 100, "net": 5.0, "median": 0.1, "percentile": 99.0, "p": 0.001,
                    "wf_first": 1.0, "wf_second": -0.5,  # 후반 음수 → robust 실패
                    "top_tail_share": 0.2, "evidence": {}, "_spec": {"required": []}}

    monkeypatch.setattr(engine, "collect_candidates", lambda: ([_C()], {}))
    monkeypatch.setattr(engine, "benjamini_hochberg",
                        lambda pvals, alpha: {"survivors": [True], "threshold": 0.05, "n_survivors": 1})
    monkeypatch.setattr(engine, "review_strategy", lambda spec, ev: {"verdict": "CLEARED", "failed": [], "missing": []})
    monkeypatch.setattr(engine, "log_experiment", lambda rec: None)
    monkeypatch.setattr(engine, "STATUS", str(tmp_path / "s.json"))
    monkeypatch.setattr(engine, "RESULTS", str(tmp_path / "r.jsonl"))

    summary = engine.run_batch()
    entry = summary["leaderboard"][0]
    assert entry["verdict"] == "WATCHLIST"       # wf 음수라 강등
    assert entry["bh_survivor"] is True
