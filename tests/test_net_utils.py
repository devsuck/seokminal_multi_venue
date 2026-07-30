import time

import pytest

from research.net_utils import call_with_hard_timeout


def test_call_with_hard_timeout_returns_value_on_success():
    assert call_with_hard_timeout(lambda: 42, timeout_s=1.0) == 42


def test_call_with_hard_timeout_reraises_underlying_exception():
    def boom():
        raise ValueError("boom")

    with pytest.raises(ValueError, match="boom"):
        call_with_hard_timeout(boom, timeout_s=1.0)


def test_call_with_hard_timeout_raises_timeout_error_when_fn_hangs():
    def hang():
        time.sleep(10)
        return "should never get here"

    with pytest.raises(TimeoutError):
        call_with_hard_timeout(hang, timeout_s=0.1)
