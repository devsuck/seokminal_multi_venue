"""엣지 졸업 스코어카드 판정 유닛테스트."""
from research.edge_graduation import GradeCriteria, grade_edge


def _summary(n_events=100, min_p=0.02, n_survivors=1):
    return {"hypothesis": "h", "verdict": "ok", "min_p_value": min_p,
            "n_survivors": n_survivors, "n_tested": 6, "n_events": n_events, "significant": n_survivors > 0}


def _traj(sig_seq):
    return [{"ts": float(i), "min_p_value": 0.03, "significant": s} for i, s in enumerate(sig_seq)]


def test_pending_when_no_summary():
    g = grade_edge(None, [])
    assert g["status"] == "accumulating" and g["readiness"] == 0.0


def test_graduated_all_pass():
    traj = _traj([True] * 12)               # 이력 충분 + 전부 유의
    g = grade_edge(_summary(), traj)
    assert g["status"] == "graduated" and g["readiness"] == 1.0
    assert all(c["pass"] for c in g["checks"].values())


def test_failed_when_powered_but_not_significant():
    # 표본 충분(120)한데 FDR 생존 0 + p 약함 → 진짜 음성
    g = grade_edge(_summary(n_events=120, min_p=0.4, n_survivors=0), _traj([False] * 12))
    assert g["status"] == "failed"


def test_accumulating_when_underpowered():
    g = grade_edge(_summary(n_events=10), _traj([True] * 12))   # 표본<30
    assert g["status"] == "accumulating"
    assert g["checks"]["powered"]["pass"] is False


def test_accumulating_when_significant_but_no_oos_history():
    # 유의하지만 궤적 이력 부족(3회 < 10) → forward 지속성 미확보
    g = grade_edge(_summary(), _traj([True] * 3))
    assert g["status"] == "accumulating"
    assert g["checks"]["oos_persistence"]["pass"] is False


def test_oos_ratio_threshold():
    # 이력 10회지만 유의 비율 50% < 60% → oos 미통과 → accumulating
    g = grade_edge(_summary(), _traj([True, False] * 5))
    assert g["checks"]["oos_persistence"]["pass"] is False
    assert g["status"] == "accumulating"


def test_readiness_fraction():
    g = grade_edge(_summary(n_events=10), _traj([True] * 12))   # powered만 실패 → 3/4
    assert g["readiness"] == 0.75


def test_custom_criteria_stricter_alpha():
    # α=0.01인데 p=0.02 → p_strong 실패
    g = grade_edge(_summary(min_p=0.02), _traj([True] * 12), GradeCriteria(alpha=0.01))
    assert g["checks"]["p_strong"]["pass"] is False
