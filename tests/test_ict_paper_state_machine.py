import csv
import os

import pytest

from research.ict.paper.state_machine import PaperEngine


@pytest.fixture
def engine_with_open_bullish_position(tmp_path):
    state_path = str(tmp_path / "state.json")
    journal_path = str(tmp_path / "journal.csv")
    engine = PaperEngine(symbol="BTC.HL", state_path=state_path, journal_path=journal_path)

    # HTF: bullish OB 존 [99, 101.5] 형성(봉0-1) + 진입가(101.0) 위쪽 swing high(110,
    # 봉2, k=2 기본값 — 5봉 있어야 idx2가 평가됨)를 다음 반대편 유동성 레벨로 잡는다.
    htf_bars = [
        {"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5},
        {"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105},
        {"ts": 1800, "open": 105, "high": 110, "low": 104, "close": 108},
        {"ts": 2700, "open": 103.5, "high": 104, "low": 100, "close": 103},
        {"ts": 3600, "open": 103, "high": 103, "low": 99.5, "close": 102},
    ]
    for bar in htf_bars:
        engine.on_htf_bar(bar)

    # LTF: 봉1~2 연속 하락 후 봉3에서 봉1 시가 위로 종가 관통 = 강세 CISD(min_run=2)
    ltf_bars = [
        {"ts": 0, "open": 100, "high": 100.6, "low": 99.9, "close": 100.5},
        {"ts": 60, "open": 100.5, "high": 100.6, "low": 99.3, "close": 99.5},
        {"ts": 120, "open": 99.5, "high": 99.6, "low": 98.3, "close": 98.5},
        {"ts": 180, "open": 98.5, "high": 101.2, "low": 98.4, "close": 101.0},
    ]
    for bar in ltf_bars[:-1]:
        engine.on_ltf_bar({"bar": bar, "of_trigger": None, "side": None})
    # 마지막 봉에서 CISD + 반전형 트리거(흡수) 동시 발생 → 진입
    engine.on_ltf_bar({"bar": ltf_bars[-1], "of_trigger": "absorption", "side": "buy"})

    assert engine.position is not None
    return engine, journal_path, state_path


def test_enters_position_on_zone_plus_cisd_plus_trigger_confluence(engine_with_open_bullish_position):
    engine, _, state_path = engine_with_open_bullish_position
    assert engine.position.side == "bullish"
    assert engine.position.entry_price == 101.0
    assert engine.position.stop == 99.0
    assert engine.position.target == 110.0  # 다음 반대편 유동성 레벨(HTF swing high)
    assert engine.position.zone_source == "OB"
    assert engine.position.of_trigger == "absorption"
    assert os.path.exists(state_path)


def test_exits_on_target_touch_and_writes_journal_row(engine_with_open_bullish_position):
    engine, journal_path, state_path = engine_with_open_bullish_position
    engine.on_price_tick(110.0)
    assert engine.position is None
    assert not os.path.exists(state_path)
    with open(journal_path) as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["direction"] == "long"
    assert rows[0]["of_trigger"] == "absorption"
    assert rows[0]["level_basis"] == "OB"
    assert float(rows[0]["result_r"]) == pytest.approx(4.5)  # (110-101)/2


def test_exits_on_stop_touch_result_r_negative(engine_with_open_bullish_position):
    engine, journal_path, _ = engine_with_open_bullish_position
    engine.on_price_tick(99.0)
    assert engine.position is None
    with open(journal_path) as f:
        rows = list(csv.DictReader(f))
    assert float(rows[0]["result_r"]) == pytest.approx(-1.0)


def test_no_reentry_on_same_zone_after_exit(engine_with_open_bullish_position):
    engine, _, _ = engine_with_open_bullish_position
    engine.on_price_tick(99.0)  # 청산(스탑) — 존 consumed 처리됨
    assert engine.position is None
    engine.on_ltf_bar({
        "bar": {"ts": 240, "open": 101.0, "high": 101.3, "low": 100.8, "close": 101.0},
        "of_trigger": "absorption", "side": "buy",
    })
    assert engine.position is None


def test_entry_stage_counts_track_successful_entry(engine_with_open_bullish_position):
    engine, _, _ = engine_with_open_bullish_position
    assert engine._entry_stage_counts["entered"] == 1


def test_skips_entry_when_no_opposing_swing_level_yet(tmp_path):
    state_path = str(tmp_path / "state.json")
    journal_path = str(tmp_path / "journal.csv")
    engine = PaperEngine(symbol="BTC.HL", state_path=state_path, journal_path=journal_path)

    # HTF: OB 존만 형성(봉 2개) — swing 평가엔 최소 5봉 필요하므로 next_opposing_level은 None
    engine.on_htf_bar({"ts": 0, "open": 100, "high": 101.5, "low": 99, "close": 99.5})
    engine.on_htf_bar({"ts": 900, "open": 99.5, "high": 106, "low": 99, "close": 105})

    ltf_bars = [
        {"ts": 0, "open": 100, "high": 100.6, "low": 99.9, "close": 100.5},
        {"ts": 60, "open": 100.5, "high": 100.6, "low": 99.3, "close": 99.5},
        {"ts": 120, "open": 99.5, "high": 99.6, "low": 98.3, "close": 98.5},
        {"ts": 180, "open": 98.5, "high": 101.2, "low": 98.4, "close": 101.0},
    ]
    for bar in ltf_bars[:-1]:
        engine.on_ltf_bar({"bar": bar, "of_trigger": None, "side": None})
    engine.on_ltf_bar({"bar": ltf_bars[-1], "of_trigger": "absorption", "side": "buy"})

    assert engine.position is None
    assert not os.path.exists(state_path)
    assert engine._entry_stage_counts["target_none"] == 1
    assert engine._entry_stage_counts["entered"] == 0
