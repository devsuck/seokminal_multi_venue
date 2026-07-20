import os

from research.ict.paper.position_state import (
    PositionState,
    clear_position_state,
    load_position_state,
    save_position_state,
)


def test_save_and_load_roundtrip(tmp_path):
    path = str(tmp_path / "state.json")
    state = PositionState(
        side="bullish", entry_price=101.0, stop=99.0, target=105.0,
        zone_source="OB", of_trigger="absorption", entered_ts=180.0,
    )
    save_position_state(path, state)
    loaded = load_position_state(path)
    assert loaded == state


def test_load_missing_returns_none(tmp_path):
    assert load_position_state(str(tmp_path / "nope.json")) is None


def test_clear_removes_file(tmp_path):
    path = str(tmp_path / "state.json")
    save_position_state(
        path,
        PositionState(side="bullish", entry_price=101.0, stop=99.0, target=105.0,
                       zone_source="OB", of_trigger="absorption", entered_ts=180.0),
    )
    clear_position_state(path)
    assert not os.path.exists(path)


def test_clear_missing_file_does_not_raise(tmp_path):
    clear_position_state(str(tmp_path / "nope.json"))
