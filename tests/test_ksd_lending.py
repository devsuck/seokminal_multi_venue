"""KSD 대차 배선 — ISIN 체크디짓 + PIT asof + tercile/부트스트랩 순수 로직."""
from ksd.client import isin_from_code
from research.data.ksd_lending import balance_asof
from research.run_buyback_x_lending import _boot_diff_p, _terciles


def test_isin_check_digit_varies():
    # 하드코딩 '3' 버그 회귀 방지: 실제 ISIN 체크디짓은 종목마다 다름
    assert isin_from_code("005930") == "KR7005930003"  # 삼성전자
    assert isin_from_code("138040") == "KR7138040001"  # 메리츠금융
    assert isin_from_code("016710") == "KR7016710006"
    assert isin_from_code("KR7005930003") == "KR7005930003"  # 12자리 통과


def test_balance_asof_strictly_before():
    lending = {"2026-07-01": 100.0, "2026-07-02": 200.0}
    # date 당일 값은 못 봄(PIT) — 이전 최근값
    assert balance_asof(lending, "2026-07-02") == 100.0
    assert balance_asof(lending, "2026-07-03") == 200.0
    # 공백 10일 초과 = None
    assert balance_asof(lending, "2026-07-20") is None


def test_terciles_split():
    vals = [(i, f"e{i}") for i in range(9)]
    top, bot = _terciles(vals)
    assert top == ["e6", "e7", "e8"] and bot == ["e0", "e1", "e2"]


def test_boot_diff_p_direction():
    a = [0.02] * 60
    c = [-0.02] * 60
    # a가 명확히 크면 direction=+1에서 p 작음, 반대 방향 검정이면 p 큼
    assert _boot_diff_p(a, c, +1) < 0.05
    assert _boot_diff_p(a, c, -1) > 0.5
