"""KR Liquidity Wave detector synthetic 테스트 (데이터 무관)."""
from __future__ import annotations

from research.strategies.kr_liquidity_wave import generate_trades, liquidity_bucket


def _mk(rows):
    """rows=[(o,h,l,c,tv)] → bars."""
    return [{"date": f"2024-01-{i+1:02d}", "open": o, "high": h, "low": l, "close": c, "tval": tv}
            for i, (o, h, l, c, tv) in enumerate(rows)]


def _wave_series():
    rows = [(100, 100, 100, 100, 1000.0)] * 20           # 워밍업 flat
    rows.append((108, 114, 107, 112, 6000.0))            # 임펄스 +12%, tval 6x
    rows.append((111, 111, 108, 109, 700.0))             # 눌림(거래대금 수축)
    rows.append((109, 110, 108, 108, 600.0))             # 눌림
    rows.append((108, 114, 108, 113, 4000.0))            # 재돌파(>pb_high 111, tval>2*avg5)
    rows.append((113, 116, 112, 115, 2000.0))            # 진입일(다음날 시가=113)
    rows += [(115, 116, 114, 115, 1500.0)] * 12          # 보유~타임스탑
    return _mk(rows)


def test_wave_fires_one_trade():
    tr = generate_trades(_wave_series())
    assert len(tr) >= 1
    t = tr[0]
    assert t["entry_price"] == 113          # 재돌파 다음날 시가
    assert t["entry_idx"] == 24             # 재돌파(idx23) 다음날 진입
    assert t["reason"] in ("time_stop", "stop")


def test_flat_no_trade():
    bars = _mk([(100, 100, 100, 100, 1000.0)] * 40)
    assert generate_trades(bars) == []


def test_no_impulse_no_trade():
    # 큰 등락 없음(+5%만) → 임펄스 미충족
    rows = [(100, 100, 100, 100, 1000.0)] * 20
    rows += [(104, 106, 103, 105, 6000.0)]              # +5% (임계 10% 미만)
    rows += [(105, 106, 104, 105, 1000.0)] * 15
    assert generate_trades(_mk(rows)) == []


def test_pullback_break_invalidates():
    # 임펄스 후 저점 붕괴 → 진입 없음
    rows = [(100, 100, 100, 100, 1000.0)] * 20
    rows.append((108, 114, 107, 112, 6000.0))          # 임펄스
    rows.append((107, 108, 95, 96, 700.0))             # base_low(107) 하향 붕괴
    rows += [(96, 97, 95, 96, 500.0)] * 15
    assert generate_trades(_mk(rows)) == []


def test_liquidity_bucket():
    assert liquidity_bucket(6e10) == "high"
    assert liquidity_bucket(2e10) == "mid"
    assert liquidity_bucket(1e9) == "low"
