"""P1.5 Signal Provider 어댑터 테스트.

가드: 결정성 · no-lookahead(결과/미래데이터 미사용) · 결측 우아 · 타임스탬프 정합.
어댑터는 전략 로직 무수정 — 전략 자신의 함수/지속상태를 as_of 이하 정보로 번역만.
"""
from __future__ import annotations

from jarvis.fusion.adapters.buyback import BuybackPositionAdapter
from jarvis.fusion.adapters.tom import TurnOfMonthAdapter
from jarvis.fusion.adapters.tsmom import TsmomAdapter


# ── buyback (포지션 원장 기반) ────────────────────────────────
_ROWS = [
    # 진입 완료, 예정 exit 이후 — as_of=2026-06-10엔 보유중
    {"stock_code": "068270", "corp_name": "셀트리온", "entry_date": "2026-05-22",
     "exit_date": "2026-06-23", "pnl_pct": -0.176, "status": "closed"},
    # 진입이 as_of 이후 — 아직 신호 없어야(no-lookahead)
    {"stock_code": "000660", "corp_name": "SK하이닉스", "entry_date": "2026-06-20",
     "exit_date": "2026-07-18", "status": "open"},
    # exit 이미 지남 — 보유 종료
    {"stock_code": "005930", "corp_name": "삼성전자", "entry_date": "2026-04-01",
     "exit_date": "2026-04-29", "pnl_pct": 0.03, "status": "closed"},
]


def test_buyback_emits_long_while_in_window():
    a = BuybackPositionAdapter(rows=_ROWS)
    sigs = a.signals("2026-06-10")
    inst = {s.instrument: s.direction for s in sigs}
    assert inst == {"068270": 1}          # 오직 보유중인 것만
    assert sigs[0].strength == 1.0


def test_buyback_no_lookahead_before_entry():
    a = BuybackPositionAdapter(rows=_ROWS)
    # 진입 전날 — 어떤 신호도 없어야(미래 진입 못 봄)
    assert a.signals("2026-06-19") == [] or all(s.instrument != "000660"
                                                for s in a.signals("2026-06-19"))


def test_buyback_direction_independent_of_outcome():
    # pnl 음수여도 보유중이면 +1 — 방향이 결과데이터에 의존하지 않음(no-lookahead 증명)
    a = BuybackPositionAdapter(rows=[_ROWS[0]])
    sigs = a.signals("2026-06-10")
    assert sigs[0].direction == 1  # pnl=-0.176인데도 롱


def test_buyback_deterministic():
    a = BuybackPositionAdapter(rows=_ROWS)
    assert [s.to_dict() for s in a.signals("2026-06-10")] == \
           [s.to_dict() for s in a.signals("2026-06-10")]


def test_buyback_missing_ledger_graceful():
    a = BuybackPositionAdapter(rows=[])
    assert a.signals("2026-06-10") == []
    assert a.signals("") == []            # 잘못된 as_of도 크래시 없음


def test_buyback_timestamp_correct():
    a = BuybackPositionAdapter(rows=[_ROWS[0]])
    s = a.signals("2026-06-10")[0]
    assert s.as_of == "2026-06-10"
    assert s.timestamp == "2026-06-10"    # 인터페이스 별칭


# ── turn-of-month (캘린더 기반) ──────────────────────────────
def test_tom_long_on_month_end():
    from jarvis.fusion.adapters.base import last_business_day
    a = TurnOfMonthAdapter(hold_days=4)
    entry = last_business_day(2026, 1)    # 1월 마지막 평일
    sigs = a.signals(entry)
    assert len(sigs) == 1 and sigs[0].direction == 1
    assert sigs[0].instrument == "KR_TOM_BASKET"
    assert sigs[0].meta["entry"] == entry


def test_tom_flat_mid_month():
    a = TurnOfMonthAdapter(hold_days=4)
    assert a.signals("2026-01-15") == []  # 월 중순 = 창 밖


def test_tom_deterministic_and_timestamp():
    a = TurnOfMonthAdapter(hold_days=4)
    from jarvis.fusion.adapters.base import last_business_day
    entry = last_business_day(2026, 3)
    assert a.signals(entry) == a.signals(entry)
    assert a.signals(entry)[0].as_of == entry


# ── tsmom (전략 신호함수 호출) ───────────────────────────────
def _panel(symbol, dates, prices):
    return {"symbol": symbol, "dates": list(dates), "close": dict(zip(dates, prices))}


def _small_params():
    return {"lookback": 2, "vol_window": 2, "target_vol": 0.15, "cap": 3.0}


def test_tsmom_translates_direction():
    from research.hypotheses.tsmom import tsmom_weights
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04", "2026-01-05"]
    up = _panel("UP", dates, [100, 101, 102, 103, 104])     # 상승 → +1
    dn = _panel("DN", dates, [100, 99, 98, 97, 96])         # 하락 → -1
    a = TsmomAdapter("futures_tsmom", symbols=["UP", "DN"],
                     params=_small_params(),
                     panel_loader=lambda s: {"UP": up, "DN": dn}[s],
                     weights_fn=tsmom_weights)
    sigs = {s.instrument: s.direction for s in a.signals("2026-01-04")}
    assert sigs == {"UP": 1, "DN": -1}


def test_tsmom_no_lookahead_slice_invariant():
    """as_of=d4 신호가 미래봉(d5) 유무와 무관해야 = no-lookahead."""
    from research.hypotheses.tsmom import tsmom_weights
    base = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    with_future = base + ["2026-01-05"]
    up_short = _panel("UP", base, [100, 101, 102, 103])
    up_long = _panel("UP", with_future, [100, 101, 102, 103, 999])  # 미래봉 극단값

    def mk(panel):
        return TsmomAdapter("futures_tsmom", symbols=["UP"], params=_small_params(),
                            panel_loader=lambda s: panel, weights_fn=tsmom_weights)

    s1 = mk(up_short).signals("2026-01-04")
    s2 = mk(up_long).signals("2026-01-04")
    assert [x.to_dict() for x in s1] == [x.to_dict() for x in s2]


def test_tsmom_missing_data_graceful():
    a = TsmomAdapter("futures_tsmom", symbols=["X"],
                     panel_loader=lambda s: {"symbol": s, "dates": [], "close": {}})
    assert a.signals("2026-01-04") == []


def test_tsmom_timestamp_correct():
    from research.hypotheses.tsmom import tsmom_weights
    dates = ["2026-01-01", "2026-01-02", "2026-01-03", "2026-01-04"]
    up = _panel("UP", dates, [100, 101, 102, 103])
    a = TsmomAdapter("futures_tsmom", symbols=["UP"], params=_small_params(),
                     panel_loader=lambda s: up, weights_fn=tsmom_weights)
    s = a.signals("2026-01-04")[0]
    assert s.as_of == "2026-01-04" and s.timestamp == "2026-01-04"


# ── 등록 배선 ────────────────────────────────────────────────
def test_adapters_register_into_provider_registry():
    import jarvis.fusion.adapters  # noqa: F401  (자기등록)
    from jarvis.fusion.providers import PROVIDER_REGISTRY
    for sid in ("kr_dart_buyback_drift_v1", "kr_turn_of_month_v1_PORTFOLIO",
                "futures_tsmom", "futures_tsmom_32mkt"):
        assert sid in PROVIDER_REGISTRY
        assert callable(PROVIDER_REGISTRY[sid])
