"""experiment_registry → critic metrics 정규화 회귀테스트.

배경(2026-08-27): `backtest.run()`이 experiment_registry 행을 `net_pnl`/`random_pct`로
읽고 있었는데 실제 스키마 키는 `net`/`percentile`이라 두 필드가 항상 None이었다.
critic의 검사는 전부 `is not None` 가드라 플래그는 0개인데, passes/weak가 non-None을
요구해서 결과만 rejected — "이유 없는 탈락"이 실데이터 전략 전건에 발생했다.
실제 피해: `auto_fac_kr_size_smb`/`auto_fac_kr_amihud_illiq`/`auto_fac_kr_turnover_neglect`
(p=0.0033, BH 생존, 레드팀 CLEARED, WF 양쪽 +) 3건이 2026-07-13에 오탈락.
"""
from __future__ import annotations

import pytest

from jarvis.agents.backtest import _metrics_from_experiment_row
from jarvis.agents.critic import review

# autoresearch 러너가 쓰는 현행 스키마(experiment_registry.jsonl 4415/4520행).
CURRENT_ROW = {
    "hypothesis_id": "auto_fac_kr_size_smb", "status": "candidate", "n": 82,
    "net": 0.042305, "percentile": 100.0, "p": 0.0033,
    "wf_first": 0.043223, "wf_second": 0.041387,
    "redteam": "CLEARED", "data_quality": "KRX PIT survivorship-free",
}
# 구형 러너 스키마(같은 파일에 6행 잔존) — 하위호환이 깨지면 안 된다.
LEGACY_ROW = {
    "hypothesis_id": "old_runner_v1", "status": "done",
    "net_pnl": 0.031, "random_pct": 97.0, "p": 0.01,
    "wf_first": 0.02, "wf_second": 0.03,
}


def test_current_schema_populates_every_decision_field():
    m = _metrics_from_experiment_row(CURRENT_ROW)
    assert m["net"] == pytest.approx(0.042305)
    assert m["random_percentile"] == pytest.approx(100.0)
    assert m["empirical_p"] == pytest.approx(0.0033)
    assert m["wf_first"] == pytest.approx(0.043223)
    assert m["wf_second"] == pytest.approx(0.041387)


def test_legacy_schema_still_reads():
    m = _metrics_from_experiment_row(LEGACY_ROW)
    assert m["net"] == pytest.approx(0.031)
    assert m["random_percentile"] == pytest.approx(97.0)


def test_mean_return_alias_used_when_net_absent():
    m = _metrics_from_experiment_row({"mean_return": 0.02, "percentile": 96.0,
                                      "p": 0.01, "wf_first": 0.01, "wf_second": 0.02})
    assert m["net"] == pytest.approx(0.02)


def test_qualified_row_reaches_paper_candidate():
    """이 테스트가 회귀의 핵심 — 예전 코드에선 rejected가 나왔다."""
    cr = review("auto_fac_kr_size_smb", _metrics_from_experiment_row(CURRENT_ROW))
    assert cr["recommendation"] == "paper_candidate"
    assert cr["critic_flags"] == []


def test_missing_metrics_flagged_never_silent():
    """지표가 비면 rejected는 맞되, 반드시 이유(플래그)가 남아야 한다."""
    cr = review("empty_v1", _metrics_from_experiment_row({"hypothesis_id": "empty_v1"}))
    assert cr["recommendation"] == "rejected"
    incomplete = [f for f in cr["critic_flags"] if f.startswith("metrics_incomplete:")]
    assert len(incomplete) == 1
    for field in ("net", "random_percentile", "empirical_p", "wf_first", "wf_second"):
        assert field in incomplete[0]


def test_no_reasonless_rejection_invariant():
    """불변식: rejected면 플래그가 최소 1개. 플래그 0개 + rejected 조합은 버그다."""
    rows = [
        {},                                                   # 전부 누락
        {"net": -0.01, "percentile": 10.0, "p": 0.9,
         "wf_first": -0.1, "wf_second": -0.2},                # 전부 실패
        {"net": 0.01, "percentile": 50.0, "p": 0.4,
         "wf_first": 0.01, "wf_second": -0.01},               # 부분 실패
        {"percentile": 100.0, "p": 0.001,
         "wf_first": 0.05, "wf_second": 0.04},                # net만 누락
    ]
    for row in rows:
        cr = review("inv_v1", _metrics_from_experiment_row(row))
        if cr["recommendation"] == "rejected":
            assert cr["critic_flags"], f"플래그 없는 rejected: {row}"


def test_walk_forward_break_blocks_paper_candidate():
    """가드가 느슨해진 게 아님을 확인 — WF 후반 음수면 승격 못 한다.

    net>0·pct>=95라 `weak` 경로로 watchlist까지는 가되 paper_candidate는 아니다.
    """
    row = dict(CURRENT_ROW, wf_second=-0.01)
    cr = review("decayed_v1", _metrics_from_experiment_row(row))
    assert cr["recommendation"] == "watchlist"
    assert "walk_forward_unstable" in cr["critic_flags"]


def test_weak_stats_still_rejected():
    """랜덤 대비 열위면 여전히 rejected — 별칭 수정이 기준을 완화하지 않는다."""
    row = dict(CURRENT_ROW, percentile=40.0, p=0.6)
    cr = review("weak_v1", _metrics_from_experiment_row(row))
    assert cr["recommendation"] == "rejected"
    assert "random_below_95pct" in cr["critic_flags"]
    assert "p_not_significant" in cr["critic_flags"]
