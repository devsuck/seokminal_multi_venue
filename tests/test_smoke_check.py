from research.papers.smoke_check import check

_GOOD_CODE = '''
NAME = "vwap_fade"
DESCRIPTION = "VWAP 이탈 평균회귀"

def signal_fn(ohlc, feat, aux, params):
    c = ohlc["close"]
    n = len(c)
    entry = [False] * n
    elig = list(range(n))
    for i in range(n):
        if i % 10 == 0:
            entry[i] = True
    return {"entry": entry, "eligible": elig}
'''

_CRASHING_CODE = '''
NAME = "broken"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    raise RuntimeError("boom")
'''

_ALL_FALSE_CODE = '''
NAME = "dead"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    n = len(ohlc["close"])
    return {"entry": [False] * n, "eligible": list(range(n))}
'''

_NAN_CODE = '''
NAME = "nan"
DESCRIPTION = "d"

def signal_fn(ohlc, feat, aux, params):
    n = len(ohlc["close"])
    return {"entry": [float("nan")] * n, "eligible": list(range(n))}
'''

_SYNTAX_ERROR_CODE = "def signal_fn(:::\n"

_MISSING_SYMBOLS_CODE = '''
X = 1
'''


def test_check_passes_valid_signal_fn():
    ok, reason = check(_GOOD_CODE)
    assert ok is True
    assert reason == ""


def test_check_rejects_syntax_error():
    ok, reason = check(_SYNTAX_ERROR_CODE)
    assert ok is False
    assert "exec" in reason.lower() or "syntax" in reason.lower()


def test_check_rejects_missing_required_symbols():
    ok, reason = check(_MISSING_SYMBOLS_CODE)
    assert ok is False
    assert "심볼" in reason


def test_check_rejects_crashing_signal_fn():
    ok, reason = check(_CRASHING_CODE)
    assert ok is False
    assert "boom" in reason


def test_check_rejects_all_false_entry():
    ok, reason = check(_ALL_FALSE_CODE)
    assert ok is False
    assert "False" in reason


def test_check_rejects_nan_entry():
    ok, reason = check(_NAN_CODE)
    assert ok is False
    assert "NaN" in reason
