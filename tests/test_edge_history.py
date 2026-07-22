"""엣지 감쇠 추적 — 요약 추출 + 시계열 저장/로드 유닛테스트."""
from research.edge_history import (
    summarize_report,
    record,
    load_trajectory,
    trajectory_trend,
)


def test_summarize_groups_pools_shape():
    rep = {
        "hypothesis": "polymarket_sharp_wallet",
        "verdict": "ok",
        "groups": [
            {"group": "bucket0", "horizons": [
                {"horizon": "60s", "n_events": 12, "p_value": 0.30, "percentile": 70},
                {"horizon": "300s", "n_events": 8, "p_value": 0.04, "percentile": 96}]},
        ],
        "pools": [{"n_survivors": 1, "n_tested": 6}],
    }
    s = summarize_report(rep)
    assert s["hypothesis"] == "polymarket_sharp_wallet"
    assert s["min_p_value"] == 0.04           # 최소 p
    assert s["n_survivors"] == 1 and s["n_tested"] == 6
    assert s["n_events"] == 20                 # 12+8
    assert s["significant"] is True


def test_summarize_no_data():
    s = summarize_report({"hypothesis": "x", "verdict": "no_data", "groups": [], "pools": []})
    assert s["verdict"] == "no_data" and s["min_p_value"] is None
    assert s["significant"] is False


def test_summarize_error_report():
    s = summarize_report({"hypothesis": "x", "error": "boom"})
    assert s["verdict"] == "error" and s["significant"] is False


def test_summarize_infers_verdict_when_missing():
    # verdict 키 없고 p_value 있으면 ok로 추론
    s = summarize_report({"hypothesis": "x", "stuff": {"p_value": 0.5}})
    assert s["verdict"] == "ok" and s["min_p_value"] == 0.5


def test_record_and_load_roundtrip(tmp_path):
    for ts, p in [(1.0, 0.5), (2.0, 0.3), (3.0, 0.02)]:
        record("hyp1", {"verdict": "ok", "min_p_value": p, "n_survivors": 1,
                        "n_tested": 3, "n_events": 10, "significant": True},
               ts, history_dir=tmp_path)
    traj = load_trajectory("hyp1", history_dir=tmp_path)
    assert len(traj) == 3
    assert [r["min_p_value"] for r in traj] == [0.5, 0.3, 0.02]   # 시간순


def test_load_trajectory_missing_returns_empty(tmp_path):
    assert load_trajectory("nope", history_dir=tmp_path) == []


def test_trajectory_trend_direction():
    traj = [{"ts": 1.0, "min_p_value": 0.5}, {"ts": 2.0, "min_p_value": 0.02}]
    t = trajectory_trend(traj)
    assert t["direction"] == "improving" and t["latest_p"] == 0.02
    decay = [{"ts": 1.0, "min_p_value": 0.02}, {"ts": 2.0, "min_p_value": 0.4}]
    assert trajectory_trend(decay)["direction"] == "decaying"
    assert trajectory_trend([])["points"] == 0
