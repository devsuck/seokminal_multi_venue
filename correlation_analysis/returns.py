from nautilus_trader.model.data import Bar


def compute_returns(bars: list[Bar]) -> dict[int, float]:
    returns: dict[int, float] = {}
    for i in range(1, len(bars)):
        prior_close = bars[i - 1].close.as_double()
        close = bars[i].close.as_double()
        returns[bars[i].ts_event] = (close / prior_close) - 1.0
    return returns
