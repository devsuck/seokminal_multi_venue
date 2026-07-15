from research.papers.coverage_filter import is_covered, rejection_reason


def test_equity_intraday_is_covered():
    assert is_covered({"asset_class": "equity_intraday"}) is True
    assert rejection_reason({"asset_class": "equity_intraday"}) is None


def test_other_asset_classes_are_rejected():
    for ac in ["equity_daily", "crypto", "futures", "options", "fx", "other"]:
        spec = {"asset_class": ac}
        assert is_covered(spec) is False
        reason = rejection_reason(spec)
        assert reason is not None
        assert ac in reason


def test_missing_asset_class_is_rejected():
    assert is_covered({}) is False
    assert rejection_reason({}) is not None
